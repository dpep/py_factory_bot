import collections
import copy
import difflib
import functools
import inspect
import itertools
import os
import re
import sys
import types
import weakref
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar, overload

if sys.version_info >= (3, 14):
    import annotationlib

_registry: dict[str, "_Definition"] = {}
_sequences: weakref.WeakSet["_Sequence"] = weakref.WeakSet()
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
        for case in [(), *((t,) for t in d.visible_traits())]
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


# Markers are typed `object`: opaque, good only for handing back to factory_bot.
# The first overload keeps `lambda n:` inferred as `n: int`.
@overload
def sequence(fn: Callable[[int], Any], /) -> object: ...
@overload
def sequence(fn: Callable[..., Any], /) -> object: ...
def sequence(fn: Callable[..., Any], /) -> object:
    """A value built from a counter that starts at 1, e.g. sequence(lambda n: f"user{n}").

    The counter comes first; other parameters are attributes, injected by name.
    """
    if not _takes_leading_argument(fn):
        raise FactoryError(
            f'sequence() takes a function of the counter, e.g. sequence(lambda n: f"user{{n}}"), not {fn!r}'
        )
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

    def resolve(self, trait_names, overrides, declarations=None):
        """The lineage, then the named traits, then the declarations, then the overrides: later layers win.

        Declarations are an association's overrides written in a body: evaluated like the
        factory's own attributes, where overrides are used as given.
        """
        lineage = self.lineage()
        layers = [*lineage, *self._find_traits(trait_names)]
        declarations = declarations or {}
        values = [*(layer.attributes for layer in layers), declarations, overrides]
        given = {n: _Given(v) for n, v in overrides.items()}
        definitions = {
            n: v for layer in [*values[:-1], given] for n, v in layer.items()
        }
        passed = {**declarations, **overrides}
        return _Plan(
            factory=self.name,
            definitions=definitions,
            transients={
                n
                for layer in values
                for n, v in layer.items()
                if isinstance(v, _Transient)
            },
            declared={n for layer in layers for n in layer.attributes},
            associations={
                n
                for n, v in definitions.items()
                if isinstance(v, _Association) and n not in overrides
            },
            replaced={
                key[:-3]: key
                for key in passed
                if key.endswith("_id")
                and key[:-3] not in passed
                and isinstance(_unwrap(definitions.get(key[:-3])), _Association)
            },
            model=next(d.model for d in reversed(lineage) if d.model is not None),
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
    # In declaration order. Overrides are wrapped in _Given.
    definitions: dict[str, Any]
    # Transient in any layer stays transient, whatever a later layer assigns.
    transients: set[str]
    # What the factory and its traits declare, overrides aside.
    declared: set[str]
    # Associations declared and not passed: attributes_for leaves them out.
    associations: set[str]
    # Associations not made because an override gave their `<name>_id`: name -> that key.
    replaced: dict[str, str]
    model: Callable[..., Any]
    # By kind, in layer order.
    callbacks: dict[str, list[Callable[..., Any]]]


def _register(definition):
    """Register a top-level factory and its children, all or none."""
    seen = {}
    for d in definition.tree():
        existing = _registry.get(d.name) or seen.get(d.name)
        if existing:
            first, again = existing.body, d.body
            same_line = _where(first, full=True) == _where(again, full=True)
            if same_line and first.__module__ != again.__module__:
                fix = (
                    f": the same file was imported twice, as {first.__module__!r}"
                    f" and as {again.__module__!r}. Import it under one name."
                )
            else:
                fix = ". To redefine it, e.g. in a REPL or after a reload, call clear_factories() first."
            raise FactoryError(
                f"Factory {d.name!r} is already defined{_where(first, full=True)}{fix}"
            )
        seen[d.name] = d
    _registry.update(seen)


class _Marker:
    """A declaration evaluated at build time, rather than a value used as given."""


class _Sequence(_Marker):
    def __init__(self, fn):
        self.fn = fn
        self.reset()
        _sequences.add(self)

    def reset(self):
        self.counter = itertools.count(1)

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
    """A value passed at build time: never copied, and never called unless it is a marker."""

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
        if name in self.plan.transients or name in self.plan.replaced:
            return False
        return not (
            self.strategy == "attributes_for" and name in self.plan.associations
        )

    def get(self, name):
        if name in self.values:
            return self.values[name]
        if name in self.resolving:
            if self.resolving[-1] == name:
                raise self.error(
                    f"{name!r} takes itself as a parameter."
                    " To adjust a value once it's worked out, use @after_build."
                )
            cycle = " -> ".join([*self.resolving[self.resolving.index(name) :], name])
            raise self.error(f"circular dependency: {cycle}")
        self.resolving.append(name)
        try:
            value = self.evaluate(name, self.plan.definitions[name])
            if marker := _marker_in(value):
                raise FactoryError(_never_evaluated(name, marker, value))
            self.values[name] = value
        except Exception as e:
            self.note(
                e, f", attribute {name!r}{_where(_source(self.plan.definitions[name]))}"
            )
            raise
        finally:
            self.resolving.pop()
        return self.values[name]

    def evaluate(self, name, value, given=False):
        if isinstance(value, _Given):
            if not isinstance(value.value, _Marker):
                return value.value
            value, given = value.value, True
        if isinstance(value, _Transient):
            return self.evaluate(name, value.value, given)
        if isinstance(value, _Sequence):
            return self.call(name, value.fn, next(value.counter))
        if isinstance(value, _Association):
            return self.associate(value, name, given)
        if _is_lazy(value):
            return self.call(name, value)
        return value if given else _fresh(value)

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
        if _is_async(fn):
            raise self.error(
                f"{name!r} is an async def, so calling it gives a coroutine, not a value."
                f" Use a plain def, or await it outside the build and pass the result.{_where(fn)}"
            )
        if _code_is(fn, inspect.isgeneratorfunction):
            raise self.error(
                f"{name!r} is a generator function, so calling it gives a generator, not a value."
                f" Return a list instead, or wrap it in a lambda to store the generator.{_where(fn)}"
            )
        positional, keyword = _dependencies(fn, len(leading))
        for dep in [*positional, *keyword]:
            if dep in self.plan.replaced:
                raise self.error(
                    f"{name!r} depends on {dep!r}, which isn't made because {self.plan.replaced[dep]}= was given."
                    f" Pass {dep}= as well, or drop {self.plan.replaced[dep]}=."
                )
            if dep not in self.plan.definitions:
                raise self.error(
                    f"{name!r} depends on {dep!r}, which is not defined."
                    f"{_suggest(dep, self.plan.definitions)}{_where(fn)}"
                )
        args = [self.get(dep) for dep in positional]
        result = fn(*leading, *args, **{dep: self.get(dep) for dep in keyword})
        if inspect.iscoroutine(result):
            result.close()  # else Python warns it was never awaited
            raise self.error(
                f"{name!r} returned a coroutine, not a value."
                f" Await it outside the build and pass the result.{_where(fn)}"
            )
        return result

    def associate(self, assoc, name=None, given=True):
        name = name or (self.resolving[-1] if self.resolving else None)
        if assoc.name not in _registry:
            what = f"{name!r} is an association" if name else "an association"
            raise self.error(
                f"{what} to {assoc.name!r}, which is not a factory."
                f"{_suggest(assoc.name, _registry)}"
            )
        # attributes_for omits associations, but a dependent attribute may still need the object.
        strategy = "create" if self.strategy == "create" else "build"
        # The same association with the same overrides, inside itself, never ends. The
        # key is the marker's own overrides: a per-build copy would never repeat.
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
        overrides, declarations = (
            (assoc.overrides, None) if given else ({}, assoc.overrides)
        )
        return _run(
            strategy, assoc.name, assoc.traits, overrides, (label, key), declarations
        )


def _run(strategy, factory, traits, overrides, via=None, declarations=None):
    name = _name_of(factory)
    if _defining_factory() is not None:
        raise FactoryError(
            f"{strategy}({name!r}) ran while a factory was being defined, so it would run once, at import."
            f" Use association({name!r}), which builds or creates to match the parent, or make it lazy: lambda: {strategy}({name!r})"
        )
    # Outside the frame below: an unknown factory or trait is the caller's mistake.
    plan = _lookup(name).resolve(traits, overrides, declarations)
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


class _Session(Protocol):
    """A SQLAlchemy Session or scoped_session, duck-typed so factory_bot never imports SQLAlchemy."""

    def add(self, instance: Any, /) -> object: ...
    def flush(self) -> object: ...


S = TypeVar("S", bound=_Session)
Fn = TypeVar("Fn", bound=Callable[..., Any])


# A session before a function: scoped_session is callable too.
@overload
def persist_with(hook: None, /) -> None: ...
@overload
def persist_with(hook: S, /) -> S: ...
@overload
def persist_with(hook: Fn, /) -> Fn: ...
def persist_with(hook, /):
    """Save every created object with hook(obj), or session.add(obj) + flush(), instead of obj.save().

    The session is never committed, so the test's transaction still decides. persist_with(None)
    restores obj.save().
    """
    if _defining_factory() is not None:
        raise FactoryError(
            "persist_with() sets the save hook, so call it outside any factory body, e.g. in a fixture."
        )
    maker = getattr(hook, "class_", None)
    if _is_session(hook):
        if _is_async(hook.flush):
            raise FactoryError(
                f"persist_with() can't await an AsyncSession's flush(). {_ASYNC_FIX}"
            )
        _set_persist_hook(lambda obj: _add_and_flush(hook, obj))
    elif _is_session(maker):  # callable, so it would pass as a hook
        fix = (
            _ASYNC_FIX
            if _is_async(getattr(maker, "flush", None))
            else "Pass the test's session, e.g. persist_with(session)."
        )
        raise FactoryError(f"persist_with() takes a session, not a sessionmaker. {fix}")
    elif hook is None or callable(hook):
        _set_persist_hook(hook)
    else:
        raise FactoryError(
            "persist_with() takes a function, a SQLAlchemy session, or None to restore obj.save();"
            f" got {hook!r}."
        )
    return hook


# Its sync session alone fails outside run_sync: the async driver needs SQLAlchemy's greenlet.
_ASYNC_FIX = (
    "Pass the sync session behind the test's AsyncSession, persist_with(session.sync_session),"
    " and call create() inside await session.run_sync(...)."
)


# Each persist_with call belongs to its owner, the test or fixture the pytest plugin says is
# running, else the permanent base owner. The most recent call of a live owner decides; an
# owner's later call replaces its earlier one, which could only matter once both were gone.
_BASE = object()
_owners: list[object] = []  # innermost last
_hooks: dict[object, Callable[[Any], object] | None] = {}  # by owner, most recent last


def _set_persist_hook(fn):
    owner = _owners[-1] if _owners else _BASE
    _hooks.pop(owner, None)
    _hooks[owner] = fn


def _enter_owner(owner):
    _owners.append(owner)


def _leave_owner(owner):
    if owner in _owners:
        _owners.remove(owner)


def _end_owner(owner):
    _leave_owner(owner)
    _hooks.pop(owner, None)


def _is_session(obj):
    return hasattr(obj, "add") and hasattr(obj, "flush")


def _add_and_flush(session, obj):
    session.add(obj)
    session.flush()


def _persist(evaluator, obj):
    hook = next(reversed(_hooks.values()), None)
    if hook is not None:
        hook(obj)
        return
    if not hasattr(obj, "save"):
        raise evaluator.error(
            f"can't create a {type(obj).__name__}: it has no save()."
            " Give it a save() method, or call persist_with() with a function or a SQLAlchemy session"
            " (in a test with a database, the fixture that calls it didn't run)."
        )
    obj.save()


# By subclass, not duck type: a MutableMapping like os.environ must not be cloned.
_CONTAINERS = (dict, list, tuple, set, frozenset, collections.deque)


def _fresh(value, memo=None):
    """Copy through containers so builds never share them, keeping each one's type.

    Other objects are used as-is: sessions, models and clients must not be cloned.
    """
    if not isinstance(value, (*_CONTAINERS, bytearray)):
        return value
    memo = (
        {} if memo is None else memo
    )  # id -> copy: keeps shared and cyclic references
    if id(value) in memo:
        return memo[id(value)]
    if isinstance(value, tuple):
        items = [_fresh(v, memo) for v in value]
        if id(value) in memo:  # a cycle through a mutable item copied it already
            return memo[id(value)]
        if all(new is old for new, old in zip(items, value, strict=True)):
            copied = value
        elif make := getattr(value, "_make", None):  # a namedtuple takes fields
            copied = make(items)
        else:
            copied = type(value)(items)
        memo[id(value)] = copied
        return copied
    # copy.copy keeps a subclass's type and state: default_factory, order, maxlen.
    if isinstance(value, dict):
        copied = memo[id(value)] = copy.copy(value)
        for k, v in value.items():
            copied[k] = _fresh(v, memo)
        return copied
    if isinstance(value, (list, collections.deque)):
        copied = memo[id(value)] = copy.copy(value)
        copied.clear()
        copied.extend(_fresh(v, memo) for v in value)
        return copied
    # A set holds only hashables, a bytearray only ints: nothing inside to copy.
    memo[id(value)] = copy.copy(value)
    return memo[id(value)]


def _marker_in(value, seen=None):
    """The first marker in value or the containers in it, without copying anything."""
    if isinstance(value, _Marker):
        return value
    if not isinstance(value, _CONTAINERS):
        return None
    seen = set() if seen is None else seen
    if id(value) in seen:
        return None
    seen.add(id(value))
    items = (
        itertools.chain.from_iterable(value.items())
        if isinstance(value, dict)
        else value
    )
    return next((m for item in items if (m := _marker_in(item, seen))), None)


def _never_evaluated(name, marker, value):
    if marker is value:
        kind = type(marker).__name__.lstrip("_").lower()
        return (
            f"{marker!r} was returned by a function, which never evaluates it:"
            f" assign it as the attribute's whole value instead, f.{name} = {kind}(...)."
        )
    if isinstance(marker, _Association):
        fix = (
            "build the container in a function, where association() builds right away:"
            f" lambda: [association({marker.name!r})]"
        )
    else:
        fix = (
            "declare it as an attribute of its own, transient() if the model shouldn't get it,"
            " and take that attribute as a parameter"
        )
    return f"{marker!r} is inside a container, which never evaluates it: {fix}."


def _is_lazy(value):
    """Functions are called per build; every other object, callable or not, is stored."""
    # partial is named: it counts as a routine only from 3.14, where it gained __get__.
    # callable: isroutine also counts descriptors, like a cached_property, that can't be called.
    return callable(value) and (
        inspect.isroutine(value) or isinstance(value, functools.partial)
    )


def _code_is(fn, *checks):
    """Whether any of inspect's code checks holds; a Mock(spec=func) fakes the __code__ they read."""
    try:
        return any(check(fn) for check in checks)
    except Exception:  # noqa: BLE001
        return False


def _is_async(fn):
    return _code_is(fn, inspect.iscoroutinefunction, inspect.isasyncgenfunction)


def _unwrap(value):
    return value.value if isinstance(value, _Transient) else value


def _source(value):
    """The function behind a definition, to point at its line."""
    if isinstance(value, (_Given, _Transient)):
        return _source(value.value)
    return value.fn if isinstance(value, _Sequence) else value


# Reading a signature costs more than the rest of a build, and a callable's never changes.
_dependency_cache: weakref.WeakKeyDictionary[Any, dict[int, Any]] = (
    weakref.WeakKeyDictionary()
)


def _dependencies(fn, skip):
    """Names of fn's required parameters: (positional-only, the rest)."""
    try:
        by_skip = _dependency_cache.setdefault(fn, {})
    except TypeError:  # unhashable, or no weak reference (most builtins)
        return _read_dependencies(fn, skip)
    if skip not in by_skip:
        by_skip[skip] = _read_dependencies(fn, skip)
    return by_skip[skip]


def _signature(fn):
    """fn's parameters, its annotations unevaluated: from 3.14 they may name a TYPE_CHECKING import."""
    if sys.version_info >= (3, 14):
        return inspect.signature(fn, annotation_format=annotationlib.Format.FORWARDREF)
    return inspect.signature(fn)


def _read_dependencies(fn, skip):
    # Only required params: fake.paragraph(nb_sentences=3) must not be injected.
    try:
        params = list(_signature(fn).parameters.values())[skip:]
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


def _takes_leading_argument(fn):
    """Whether fn takes a first positional argument, ahead of the dependencies injected by name:
    a callback's instance, a sequence's counter."""
    if not callable(fn):
        return False
    try:
        params = _signature(fn).parameters.values()
    except ValueError:  # no inspectable signature; trust it
        return True
    first = next(iter(params), None)
    return first is not None and first.kind in (
        first.POSITIONAL_ONLY,
        first.POSITIONAL_OR_KEYWORD,
        first.VAR_POSITIONAL,
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
    if not isinstance(code, types.CodeType):  # a Mock(spec=func) has a fake one
        return ""
    path = code.co_filename if full else os.path.basename(code.co_filename)
    return f" ({path}:{code.co_firstlineno})"
