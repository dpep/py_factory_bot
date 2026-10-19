import difflib
import inspect
import itertools
import os
import re
import weakref
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

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
    pass


def build(name: str, /, *traits: str, **overrides: Any) -> Any:
    return _run("build", name, traits, overrides)


def create(name: str, /, *traits: str, **overrides: Any) -> Any:
    return _run("create", name, traits, overrides)


def attributes_for(name: str, /, *traits: str, **overrides: Any) -> dict[str, Any]:
    return _run("attributes_for", name, traits, overrides)


def build_list(name: str, count: int, /, *traits: str, **overrides: Any) -> list[Any]:
    return [build(name, *traits, **overrides) for _ in range(count)]


def create_list(name: str, count: int, /, *traits: str, **overrides: Any) -> list[Any]:
    return [create(name, *traits, **overrides) for _ in range(count)]


def build_pair(name: str, /, *traits: str, **overrides: Any) -> list[Any]:
    return build_list(name, 2, *traits, **overrides)


def create_pair(name: str, /, *traits: str, **overrides: Any) -> list[Any]:
    return create_list(name, 2, *traits, **overrides)


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


def association(name: str, /, *traits: str, **overrides: Any) -> Any:
    """Another factory's object, built or created along with this one.

    Called while a build is running (from a lazy attribute or callback), it builds now.
    """
    marker = _Association(name, traits, overrides)
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
        self.to_create = None

    # Walked at build time, not definition time: a child is defined while its
    # parent's body is still running, so later parent attributes must still reach it.
    def lineage(self):
        return [*(self.parent.lineage() if self.parent else []), self]

    def find_model(self):
        return next(d.model for d in reversed(self.lineage()) if d.model)

    def layers(self, trait_names):
        """The lineage then the named traits: later layers win, callbacks run in this order."""
        return [*self.lineage(), *self._find_traits(trait_names)]

    def _find_traits(self, names):
        traits = {name: t for d in self.lineage() for name, t in d.traits.items()}
        for name in names:
            if name not in traits:
                raise FactoryError(
                    f"Factory {self.name!r} has no trait {name!r}.{_suggest(name, traits)}"
                    f" Traits: {', '.join(traits) or '(none)'}"
                )
        return [traits[name] for name in dict.fromkeys(names)]  # each applies once

    def tree(self):
        return [self, *(d for child in self.children for d in child.tree())]


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


class _Sequence:
    def __init__(self, fn):
        self.fn = fn
        self.reset()
        _sequences.add(self)

    def reset(self):
        self.counter = itertools.count(1)

    def next(self):
        return self.fn(next(self.counter))


class _Association:
    def __init__(self, name, traits, overrides):
        self.name, self.traits, self.overrides = name, traits, overrides


class _Transient:
    def __init__(self, value):
        self.value = value


class _Given:
    """An override's plain value: used as given, even when callable."""

    def __init__(self, value):
        self.value = value


_Marker = (_Sequence, _Association, _Transient)


class _Evaluator:
    """Resolves one build's attributes, each at most once, in dependency order."""

    def __init__(self, strategy, factory_name, layers, overrides, via=None):
        self.strategy = strategy
        self.factory_name = factory_name
        self.via = via  # (label, key) of the association that started this build
        # Overrides are the last layer. A marker in one evaluates like a definition;
        # anything else is a plain value, never called.
        given = {
            n: v if isinstance(v, _Marker) else _Given(v) for n, v in overrides.items()
        }
        self.declared = {n for layer in layers for n in layer.attributes}
        layers = [*(layer.attributes for layer in layers), given]
        self.definitions = {n: v for layer in layers for n, v in layer.items()}
        # Transient in any layer stays transient, whatever a later layer assigns.
        self.transients = {
            n for layer in layers for n, v in layer.items() if isinstance(v, _Transient)
        }
        self.values = {}
        self.resolving = []
        self.noted = None  # the exception this build last annotated

    def attributes(self):
        names = self.definitions.keys()  # declaration order
        return {name: self.get(name) for name in names if self.exposes(name)}

    def exposes(self, name):
        if name in self.transients:
            return False
        return not (
            self.strategy == "attributes_for"
            and isinstance(self.definitions.get(name), _Association)
        )

    def get(self, name):
        if name in self.values:
            return self.values[name]
        if name in self.resolving:
            cycle = " -> ".join([*self.resolving[self.resolving.index(name) :], name])
            raise FactoryError(
                f"Factory {self.factory_name!r}: circular dependency: {cycle}"
            )
        self.resolving.append(name)
        try:
            self.values[name] = self.evaluate(name, self.definitions[name])
        except Exception as e:
            self.note(
                e, f", attribute {name!r}{_where(_source(self.definitions[name]))}"
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
        if callable(value):
            return self.call(name, value)
        return _fresh(value)

    def note(self, e, detail="", verb="building"):
        # Ours already name the factory; a dependency's failure is noted where it happened.
        if not isinstance(e, FactoryError) and e is not self.noted:
            e.add_note(f"while {verb} factory {self.factory_name!r}{detail}")
            self.noted = e

    def call(self, name, fn, *leading):
        positional, keyword = _dependencies(fn, skip=len(leading))
        for dep in [*positional, *keyword]:
            if dep not in self.definitions:
                raise FactoryError(
                    f"Factory {self.factory_name!r}: {name!r} depends on {dep!r}, which is not defined."
                    f"{_suggest(dep, self.definitions)}{_where(fn)}"
                )
        args = [self.get(dep) for dep in positional]
        return fn(*leading, *args, **{dep: self.get(dep) for dep in keyword})

    def associate(self, assoc, name=None):
        name = name or (self.resolving[-1] if self.resolving else None)
        if assoc.name not in _registry:
            what = f"{name!r} is an association" if name else "an association"
            raise FactoryError(
                f"Factory {self.factory_name!r}: {what} to {assoc.name!r},"
                f" which is not a factory.{_suggest(assoc.name, _registry)}"
            )
        # attributes_for omits associations, but a dependent attribute may still need the object.
        strategy = "create" if self.strategy == "create" else "build"
        # The same association with the same overrides, inside itself, never ends.
        key = (
            assoc.name,
            assoc.traits,
            [(k, id(v)) for k, v in assoc.overrides.items()],
        )
        label = f"{self.factory_name}.{name}" if name else self.factory_name
        building = _building.get()
        for i, outer in enumerate(building):
            if outer.via and outer.via[1] == key:
                chain = [e.via[0] for e in building[i:] if e.via]
                raise FactoryError(
                    f"Factory {self.factory_name!r}: circular association: {' -> '.join([*chain, label])}"
                )
        return _run(strategy, assoc.name, assoc.traits, assoc.overrides, (label, key))


def _run(strategy, name, traits, overrides, via=None):
    if (defining := _defining_factory()) is not None:
        raise FactoryError(
            f"Factory {defining!r}: {strategy}({name!r}) ran while a factory was being defined, so it would run once, at import."
            f" Make it lazy: lambda: {strategy}({name!r}), or use association({name!r})"
        )
    fac = _lookup(name)
    layers = fac.layers(traits)
    evaluator = _Evaluator(strategy, fac.name, layers, overrides, via)
    token = _building.set((*_building.get(), evaluator))
    try:
        return _construct(strategy, fac, layers, evaluator)
    finally:
        _building.reset(token)


def _construct(strategy, fac, layers, evaluator):
    attributes = evaluator.attributes()
    if strategy == "attributes_for":
        return attributes
    try:
        obj = fac.find_model()(**attributes)
    except Exception as e:
        evaluator.note(e)
        if isinstance(e, TypeError):
            _note_unknown_keywords(e, evaluator, attributes)
        raise
    _run_callbacks(evaluator, layers, "after_build", obj)
    if strategy == "create":
        try:
            _persist(fac, obj)
        except Exception as e:
            evaluator.note(e, verb="saving")
            raise
        _run_callbacks(evaluator, layers, "after_create", obj)
    return obj


def _run_callbacks(evaluator, layers, kind, obj):
    for layer in layers:
        for callback in layer.callbacks[kind]:
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
        if name not in evaluator.declared and (
            hint := _suggest(name, evaluator.declared)
        ):
            e.add_note(
                f"{name!r} is not an attribute of factory {evaluator.factory_name!r}.{hint}"
            )
    for name in attributes:
        if "__" in name:
            head, _, rest = name.partition("__")
            target = evaluator.definitions.get(head)
            target = target.name if isinstance(target, _Association) else head
            e.add_note(
                f"{name!r}: deep overrides aren't supported."
                f' Override the association instead: {head}=association("{target}", {rest}=...)'
            )


def _persist(fac, obj):
    hook = next(
        (d.to_create for d in reversed(fac.lineage()) if d.to_create), _to_create
    )
    if hook:
        hook(obj)
        return
    if not hasattr(obj, "save"):
        raise FactoryError(
            f"Factory {fac.name!r}: can't create a {type(obj).__name__}: it has no save()."
            " Give it a save() method, or set a hook with to_create(fn), at top level or inside the factory."
        )
    obj.save()


def _fresh(value):
    """Copy through builtin containers so builds never share them.

    Other objects are used as-is: sessions, models and clients must not be cloned.
    """
    kind = type(value)  # exact: a subclass may not rebuild from an iterable
    if kind is dict:
        return {k: _fresh(v) for k, v in value.items()}
    if kind in (list, set, tuple):
        return kind(_fresh(v) for v in value)
    return value


def _source(value):
    """The function behind a definition, to point at its line."""
    if isinstance(value, _Transient):
        return _source(value.value)
    return value.fn if isinstance(value, _Sequence) else value


def _dependencies(fn, skip=0):
    """Names of fn's required parameters: (positional-only, the rest)."""
    # Only required params: fake.paragraph(nb_sentences=3) must not be injected.
    try:
        params = list(inspect.signature(fn).parameters.values())[skip:]
    except (TypeError, ValueError):  # some builtins (dict, str) have no signature
        return [], []
    required = [p for p in params if p.default is p.empty]
    keyword = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    return (
        [p.name for p in required if p.kind is inspect.Parameter.POSITIONAL_ONLY],
        [p.name for p in required if p.kind in keyword],
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
