import difflib
import inspect
import itertools
import os
import re
import weakref
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar, overload

_registry: dict[str, "_Definition"] = {}
_sequences: weakref.WeakSet["_Sequence"] = weakref.WeakSet()
_to_create = None
# What is running right now, innermost last: factory and trait bodies (definition time), and
# builds. Immutable tuples, so a thread or task that copied the context never sees another's pushes.
_stack: ContextVar[tuple["_Definition", ...]] = ContextVar(
    "factory_bot_stack", default=()
)
_building: ContextVar[tuple["_Evaluator", ...]] = ContextVar(
    "factory_bot_building", default=()
)


def _defining_factory() -> str | None:
    """The innermost factory whose body is running right now, if any."""
    return next((d.name for d in reversed(_stack.get()) if d.kind == "factory"), None)


class FactoryError(Exception):
    """factory_bot's error. `factory` names the factory it happened in, and prefixes the message."""

    def __init__(self, message: str = "", *, factory: str | None = None):
        super().__init__(message)
        self.factory = factory

    def __str__(self) -> str:
        message = super().__str__()
        return f"Factory {self.factory!r}: {message}" if self.factory else message


T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


class Factory(Generic[T_co]):
    """What @factory returns: pass it wherever a factory's name goes, and get its model's type back."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"<Factory {self.name!r}>"


@overload
def build(factory: str, /, *traits: str, **overrides: Any) -> Any: ...
@overload
def build(factory: Factory[T], /, *traits: str, **overrides: Any) -> T: ...
def build(factory: Any, /, *traits: str, **overrides: Any) -> Any:
    return _run("build", factory, traits, overrides)


@overload
def create(factory: str, /, *traits: str, **overrides: Any) -> Any: ...
@overload
def create(factory: Factory[T], /, *traits: str, **overrides: Any) -> T: ...
def create(factory: Any, /, *traits: str, **overrides: Any) -> Any:
    return _run("create", factory, traits, overrides)


def attributes_for(
    factory: str | Factory[Any], /, *traits: str, **overrides: Any
) -> dict[str, Any]:
    return _run("attributes_for", factory, traits, overrides)


@overload
def build_list(
    factory: str, count: int, /, *traits: str, **overrides: Any
) -> list[Any]: ...
@overload
def build_list(
    factory: Factory[T], count: int, /, *traits: str, **overrides: Any
) -> list[T]: ...
def build_list(factory: Any, count: int, /, *traits: str, **overrides: Any) -> Any:
    return [build(factory, *traits, **overrides) for _ in range(count)]


@overload
def create_list(
    factory: str, count: int, /, *traits: str, **overrides: Any
) -> list[Any]: ...
@overload
def create_list(
    factory: Factory[T], count: int, /, *traits: str, **overrides: Any
) -> list[T]: ...
def create_list(factory: Any, count: int, /, *traits: str, **overrides: Any) -> Any:
    return [create(factory, *traits, **overrides) for _ in range(count)]


def lint(
    *factories: str | Factory[Any],
    strategy: Literal["build", "create"] = "build",
    traits: bool = True,
) -> None:
    """Build every factory (or those given) once, then once with each trait; raise one error listing every failure.

    Its builds are real ones: they use up sequence numbers and fake.unique values, and
    strategy="create" saves rows, so run it inside a test, whose transaction cleans up.
    """
    if strategy not in ("build", "create"):
        raise FactoryError(
            f"lint() takes strategy='build' or 'create', not {strategy!r}"
        )
    definitions = [_lookup(_name_of(fac)) for fac in factories] or list(
        _registry.values()
    )
    calls = [
        (d.name, case)
        for d in definitions
        for case in [(), *((t,) for t in d.visible_traits() if traits)]
    ]
    failures = []
    for name, case in calls:
        try:
            _run(strategy, name, case, {})
        except Exception as e:  # noqa: BLE001  # reporting every failure is the point
            call = f"{strategy}({', '.join(map(repr, (name, *case)))})"
            e.add_note(f"factory_bot.lint: {call}")
            failures.append((call, e))
    if failures:
        lines = "".join(f"\n  {call}: {type(e).__name__}: {e}" for call, e in failures)
        raise FactoryError(
            f"lint: {len(failures)} of {len(calls)} builds failed:{lines}"
        ) from ExceptionGroup("lint failures", [e for _, e in failures])


def _set_to_create(fn):
    global _to_create
    _to_create = fn
    return fn


# Markers are typed `object`: opaque, good only for handing back to factory_bot.
def sequence(fn: Callable[[int], Any]) -> object:
    """A value built from a counter that starts at 1, e.g. sequence(lambda n: f"user{n}")."""
    try:
        inspect.signature(fn).bind(1)
    except TypeError:
        raise FactoryError(
            f'sequence() takes a function of the counter, e.g. sequence(lambda n: f"user{{n}}"), not {fn!r}'
        ) from None
    except ValueError:  # no inspectable signature; trust it
        pass
    return _Sequence(fn)


def association(factory: str | Factory[Any], /, *traits: str, **overrides: Any) -> Any:
    """Another factory's object, built or created along with this one.

    Called while a build is running (from a lazy attribute or callback), it builds now.
    """
    marker = _Association(_name_of(factory), traits, overrides)
    if building := _building.get():
        return building[-1].associate(marker)
    return marker


def transient(value: object) -> object:
    """An attribute other attributes can depend on that never reaches the model."""
    return _Transient(value)


def clear_factories() -> None:
    _registry.clear()


def reset_sequences() -> None:
    for seq in _sequences:
        seq.reset()


class _Definition:
    """A factory or a trait: what its body declared, recorded once at definition time."""

    def __init__(self, name, model, body, kind="factory", parent=None):
        self.name, self.model, self.body, self.kind = name, model, body, kind
        self.parent = parent
        self.attributes = {}
        self.traits: dict[str, _Definition] = {}
        self.children: list[_Definition] = []
        self.callbacks = {"after_build": [], "after_create": []}

    # Walked at build time, not definition time: a child is defined while its
    # parent's body is still running, so later parent attributes must still reach it.
    def lineage(self):
        return [*(self.parent.lineage() if self.parent else []), self]

    def visible_traits(self):
        """Every trait this factory can apply, its own winning over a parent's of the same name."""
        return {name: t for d in self.lineage() for name, t in d.traits.items()}

    def _find_traits(self, names):
        traits = self.visible_traits()
        for name in names:
            if name not in traits:
                raise FactoryError(
                    f"Factory {self.name!r} has no trait {name!r}.{_suggest(name, traits)}"
                    f" Traits: {', '.join(traits) or '(none)'}"
                )
        return [traits[name] for name in dict.fromkeys(names)]  # each applies once

    def resolve(self, trait_names, overrides):
        """The lineage, then the named traits, then the overrides: later layers win."""
        lineage = self.lineage()
        layers = [*lineage, *self._find_traits(trait_names)]
        # A marker in an override evaluates like a definition; anything else is a plain value.
        given = {
            n: v if isinstance(v, _Marker) else _Given(v) for n, v in overrides.items()
        }
        values = [*(layer.attributes for layer in layers), given]
        return _Plan(
            factory=self.name,
            definitions={n: v for layer in values for n, v in layer.items()},
            transients={
                n
                for layer in values
                for n, v in layer.items()
                if isinstance(v, _Transient)
            },
            declared={n for layer in layers for n in layer.attributes},
            model=next(d.model for d in reversed(lineage) if d.model),
            callbacks={
                kind: [cb for layer in layers for cb in layer.callbacks[kind]]
                for kind in self.callbacks
            },
        )

    def tree(self):
        return [self, *(d for child in self.children for d in child.tree())]


@dataclass
class _Plan:
    """One build's declarations, every layer applied: which value wins for each name, and its kind."""

    factory: str
    # In declaration order. Overrides are wrapped in _Given, unless a marker.
    definitions: dict[str, Any]
    # Transient in any layer stays transient, whatever a later layer assigns.
    transients: set[str]
    # What the factory and its traits declare, overrides aside.
    declared: set[str]
    model: Callable[..., Any]
    # By kind, in layer order.
    callbacks: dict[str, list[Callable[..., Any]]]


def _register(definition):
    """Register a top-level factory and its children, all or none."""
    seen = {}
    for d in definition.tree():
        existing = _registry.get(d.name) or seen.get(d.name)
        if existing:
            raise FactoryError(
                f"Factory {d.name!r} is already defined{_where(existing.body, full=True)}."
                " To redefine it, e.g. in a REPL or after a reload, call clear_factories() first."
            )
        seen[d.name] = d
    _registry.update(seen)


class _Marker:
    """A declaration evaluated at build time, rather than a value used as given."""


_MARKER_RULE = (
    "a sequence(), association() or transient() works only as an attribute's whole value,"
    " never returned from a function or inside a container."
)


class _Sequence(_Marker):
    def __init__(self, fn):
        self.fn = fn
        self.reset()
        _sequences.add(self)

    def reset(self):
        self.counter = itertools.count(1)

    def next(self):
        return self.fn(next(self.counter))

    def __repr__(self):
        return f"<sequence{_where(self.fn)}>"


class _Association(_Marker):
    def __init__(self, name, traits, overrides):
        self.name, self.traits, self.overrides = name, traits, overrides

    def __repr__(self):
        return f"<association {self.name!r}>"


class _Transient(_Marker):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"<transient {self.value!r}>"


class _Given:
    """An override's plain value: used as given, even when callable."""

    def __init__(self, value):
        self.value = value


class _Evaluator:
    """Resolves one build's attributes, each at most once, in dependency order."""

    def __init__(self, strategy, plan, via=None):
        self.strategy = strategy
        self.plan = plan
        self.via = via  # (label, key) of the association that started this build
        self.values = {}
        self.resolving = []
        self.noted = None  # the exception this build last annotated

    def attributes(self):
        names = self.plan.definitions.keys()  # declaration order
        return {name: self.get(name) for name in names if self.exposes(name)}

    def exposes(self, name):
        if name in self.plan.transients:
            return False
        return not (
            self.strategy == "attributes_for"
            and isinstance(self.plan.definitions.get(name), _Association)
        )

    def get(self, name):
        if name in self.values:
            return self.values[name]
        if name in self.resolving:
            cycle = " -> ".join([*self.resolving[self.resolving.index(name) :], name])
            raise self.error(f"circular dependency: {cycle}")
        self.resolving.append(name)
        try:
            value = self.evaluate(name, self.plan.definitions[name])
            if isinstance(value, _Marker):  # only a function's result can be one
                raise FactoryError(
                    f"{value!r} was returned from a function, so it was never evaluated: {_MARKER_RULE}"
                )
            self.values[name] = value
        except Exception as e:
            self.note(
                e, f", attribute {name!r}{_where(_source(self.plan.definitions[name]))}"
            )
            raise
        finally:
            self.resolving.pop()
        return self.values[name]

    def evaluate(self, name, value):
        if isinstance(value, _Given):
            return _fresh(value.value)
        if isinstance(value, _Transient):
            return self.evaluate(name, value.value)
        if isinstance(value, _Sequence):
            return value.next()
        if isinstance(value, _Association):
            return self.associate(value, name)
        # A class is stored, not called: f.status = Status means the Enum itself.
        if callable(value) and not isinstance(value, type):
            return self.call(name, value)
        return _fresh(value)

    def error(self, message):
        """A FactoryError raised by this build: its message says where, so it needs no note here."""
        self.noted = FactoryError(message)
        return self.noted

    def note(self, e, detail="", verb="building"):
        # A dependency's failure is noted where it happened, not again by each dependent.
        if e is not self.noted:
            e.add_note(f"while {verb} factory {self.plan.factory!r}{detail}")
            self.noted = e

    def call(self, name, fn, *leading):
        positional, keyword = _dependencies(fn, skip=len(leading))
        for dep in [*positional, *keyword]:
            if dep not in self.plan.definitions:
                raise self.error(
                    f"{name!r} depends on {dep!r}, which is not defined."
                    f"{_suggest(dep, self.plan.definitions)}{_where(fn)}"
                )
        args = [self.get(dep) for dep in positional]
        return fn(*leading, *args, **{dep: self.get(dep) for dep in keyword})

    def associate(self, assoc, name=None):
        name = name or (self.resolving[-1] if self.resolving else None)
        if assoc.name not in _registry:
            what = f"{name!r} is an association" if name else "an association"
            raise self.error(
                f"{what} to {assoc.name!r}, which is not a factory."
                f"{_suggest(assoc.name, _registry)}"
            )
        # attributes_for omits associations, but a dependent attribute may still need the object.
        strategy = "create" if self.strategy == "create" else "build"
        # The same association with the same overrides, inside itself, never ends.
        key = (
            assoc.name,
            assoc.traits,
            [(k, id(v)) for k, v in assoc.overrides.items()],
        )
        label = f"{self.plan.factory}.{name}" if name else self.plan.factory
        building = _building.get()
        for i, outer in enumerate(building):
            if outer.via and outer.via[1] == key:
                chain = [e.via[0] for e in building[i:] if e.via]
                raise self.error(
                    f"circular association: {' -> '.join([*chain, label])}"
                )
        return _run(strategy, assoc.name, assoc.traits, assoc.overrides, (label, key))


def _run(strategy, factory, traits, overrides, via=None):
    name = _name_of(factory)
    if _defining_factory() is not None:
        raise FactoryError(
            f"{strategy}({name!r}) ran while a factory was being defined, so it would run once, at import."
            f" Use association({name!r}), which builds or creates to match the parent, or make it lazy: lambda: {strategy}({name!r})"
        )
    # Outside the frame below: an unknown factory or trait is the caller's mistake.
    plan = _lookup(name).resolve(traits, overrides)
    evaluator = _Evaluator(strategy, plan, via)
    token = _building.set((*_building.get(), evaluator))
    try:
        return _construct(strategy, plan, evaluator)
    except FactoryError as e:
        e.factory = e.factory or plan.factory  # the innermost frame wins
        raise
    finally:
        _building.reset(token)


def _construct(strategy, plan, evaluator):
    attributes = evaluator.attributes()
    if strategy == "attributes_for":
        return attributes
    try:
        obj = plan.model(**attributes)
    except Exception as e:
        evaluator.note(e)
        if isinstance(e, TypeError):
            _note_unknown_keywords(e, evaluator, attributes)
        raise
    _run_callbacks(evaluator, plan.callbacks["after_build"], obj)
    if strategy == "create":
        try:
            _persist(evaluator, obj)
        except Exception as e:
            evaluator.note(e, verb="saving")
            raise
        _run_callbacks(evaluator, plan.callbacks["after_create"], obj)
    return obj


def _run_callbacks(evaluator, callbacks, obj):
    for callback in callbacks:
        name = getattr(callback, "__name__", repr(callback))
        try:
            evaluator.call(name, callback, obj)
        except Exception as e:
            evaluator.note(e, f", callback {name!r}{_where(callback)}")
            raise


def _note_unknown_keywords(e, evaluator, attributes):
    # Models word it differently (dataclass, Django, SQLAlchemy), but all quote the name.
    rejected = [n for n in re.findall(r"'(\w+)'", str(e)) if n in attributes]
    for name in dict.fromkeys(rejected):
        if name not in evaluator.plan.declared and (
            hint := _suggest(name, evaluator.plan.declared)
        ):
            e.add_note(
                f"{name!r} is not an attribute of factory {evaluator.plan.factory!r}.{hint}"
            )
    for name in attributes:
        if "__" in name:
            head, _, rest = name.partition("__")
            target = evaluator.plan.definitions.get(head)
            target = target.name if isinstance(target, _Association) else head
            e.add_note(
                f"{name!r}: deep overrides aren't supported."
                f' Override the association instead: {head}=association("{target}", {rest}=...)'
            )


def _persist(evaluator, obj):
    if _to_create:
        _to_create(obj)
        return
    if not hasattr(obj, "save"):
        raise evaluator.error(
            f"can't create a {type(obj).__name__}: it has no save()."
            " Give it a save() method, or set a global hook with to_create(fn)."
        )
    obj.save()


def _fresh(value, container: type | None = None):
    """Copy through builtin containers so builds never share them.

    Other objects are used as-is: sessions, models and clients must not be cloned.
    """
    kind = type(value)  # exact: a subclass may not rebuild from an iterable
    if kind is dict:
        return {k: _fresh(v, kind) for k, v in value.items()}
    if kind in (list, set, tuple):
        return kind(_fresh(v, kind) for v in value)
    # A whole value is never a marker here: evaluate takes those first.
    if container and isinstance(value, _Marker):
        raise FactoryError(
            f"{value!r} is inside a {container.__name__}, so it was never evaluated: {_MARKER_RULE}"
        )
    return value


def _source(value):
    """The function behind a definition, to point at its line."""
    if isinstance(value, _Transient):
        return _source(value.value)
    return value.fn if isinstance(value, _Sequence) else value


# Reading a signature costs more than the rest of a build, and a callable's never changes.
_dependency_cache: weakref.WeakKeyDictionary[Any, dict[int, Any]] = (
    weakref.WeakKeyDictionary()
)


def _dependencies(fn, skip=0):
    """Names of fn's required parameters: (positional-only, the rest)."""
    try:
        by_skip = _dependency_cache.setdefault(fn, {})
    except TypeError:  # unhashable, or no weak reference (most builtins)
        return _read_dependencies(fn, skip)
    if skip not in by_skip:
        by_skip[skip] = _read_dependencies(fn, skip)
    return by_skip[skip]


def _read_dependencies(fn, skip):
    # Only required params: fake.paragraph(nb_sentences=3) must not be injected.
    try:
        params = list(inspect.signature(fn).parameters.values())[skip:]
    except (TypeError, ValueError):  # some builtins (dict, str) have no signature
        return (), ()
    required = [p for p in params if p.default is p.empty]
    keyword = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    return (
        tuple(p.name for p in required if p.kind is inspect.Parameter.POSITIONAL_ONLY),
        tuple(p.name for p in required if p.kind in keyword),
    )


def _name_of(factory):
    if isinstance(factory, Factory):
        return factory.name
    if isinstance(factory, str):
        return factory
    raise FactoryError(
        f"Expected a factory or a factory's name, not {factory!r}."
        " If a fixture or variable shadows the factory, use its name or its module: factories.user"
    )


def _lookup(name):
    if name not in _registry:
        raise FactoryError(f"No factory named {name!r}.{_suggest(name, _registry)}")
    return _registry[name]


def _suggest(name, options):
    close = difflib.get_close_matches(name, list(options), n=1)
    return f" Did you mean {close[0]!r}?" if close else ""


def _where(fn, full=False):
    code = getattr(fn, "__code__", None)
    if not code:
        return ""
    path = code.co_filename if full else os.path.basename(code.co_filename)
    return f" ({path}:{code.co_firstlineno})"
