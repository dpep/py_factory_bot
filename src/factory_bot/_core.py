import copy
import difflib
import inspect
import itertools
import os
import weakref

_registry: dict[str, "_Definition"] = {}
_sequences: weakref.WeakSet["_Sequence"] = weakref.WeakSet()
_to_create = None


class FactoryError(Exception):
    pass


def build(name, /, *traits, **overrides):
    return _run("build", name, traits, overrides)


def create(name, /, *traits, **overrides):
    return _run("create", name, traits, overrides)


def attributes_for(name, /, *traits, **overrides):
    return _run("attributes_for", name, traits, overrides)


def build_list(name, count, /, *traits, **overrides):
    return [build(name, *traits, **overrides) for _ in range(count)]


def create_list(name, count, /, *traits, **overrides):
    return [create(name, *traits, **overrides) for _ in range(count)]


def build_pair(name, /, *traits, **overrides):
    return build_list(name, 2, *traits, **overrides)


def create_pair(name, /, *traits, **overrides):
    return create_list(name, 2, *traits, **overrides)


def to_create(fn):
    """Persist every created object with fn(obj) instead of obj.save(); None restores the default."""
    global _to_create
    _to_create = fn
    return fn


def sequence(fn):
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


def association(name, /, *traits, **overrides):
    """Another factory's object, built or created along with this one."""
    return _Association(name, traits, overrides)


def transient(value):
    """An attribute other attributes can depend on that never reaches the model."""
    return _Transient(value)


def clear_factories():
    _registry.clear()


def reset_sequences():
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
        return [traits[name] for name in names]

    def tree(self):
        return [self, *(d for child in self.children for d in child.tree())]


def _register(definition):
    """Register a top-level factory and its children, all or none."""
    seen = {}
    for d in definition.tree():
        existing = _registry.get(d.name) or seen.get(d.name)
        if existing:
            raise FactoryError(
                f"Factory {d.name!r} is already defined{_where(existing.body)}"
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


class _Evaluator:
    """Resolves one build's attributes, each at most once, in dependency order."""

    def __init__(self, strategy, factory_name, definitions, overrides):
        self.strategy = strategy
        self.factory_name = factory_name
        self.definitions = definitions
        self.values = dict(overrides)  # overrides are plain values, never called
        self.resolving = []

    def attributes(self):
        names = (self.definitions | self.values).keys()  # declaration order
        return {name: self.get(name) for name in names if self.exposes(name)}

    def exposes(self, name):
        value = self.definitions.get(name)
        if isinstance(value, _Transient):
            return False
        return not (
            self.strategy == "attributes_for" and isinstance(value, _Association)
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
        finally:
            self.resolving.pop()
        return self.values[name]

    def evaluate(self, name, value):
        if isinstance(value, _Transient):
            return self.evaluate(name, value.value)
        if isinstance(value, _Sequence):
            return value.next()
        if isinstance(value, _Association):
            return self.associate(name, value)
        if callable(value):
            return self.call(name, value)
        if isinstance(value, (list, dict, set)):
            return copy.copy(value)
        return value

    def call(self, name, fn, *leading):
        deps = _dependencies(fn, skip=len(leading))
        for dep in deps:
            if dep not in self.values and dep not in self.definitions:
                raise FactoryError(
                    f"Factory {self.factory_name!r}: {name!r} depends on {dep!r}, which is not defined."
                    f"{_suggest(dep, self.definitions)}{_where(fn)}"
                )
        return fn(*leading, **{dep: self.get(dep) for dep in deps})

    def associate(self, name, assoc):
        if assoc.name not in _registry:
            raise FactoryError(
                f"Factory {self.factory_name!r}: {name!r} is an association to {assoc.name!r},"
                f" which is not a factory.{_suggest(assoc.name, _registry)}"
            )
        # attributes_for omits associations, but a dependent attribute may still need the object.
        strategy = "create" if self.strategy == "create" else "build"
        return _run(strategy, assoc.name, assoc.traits, assoc.overrides)


def _run(strategy, name, traits, overrides):
    fac = _lookup(name)
    layers = fac.layers(traits)
    definitions = {name: v for layer in layers for name, v in layer.attributes.items()}
    evaluator = _Evaluator(strategy, fac.name, definitions, overrides)
    attributes = evaluator.attributes()
    if strategy == "attributes_for":
        return attributes
    obj = fac.find_model()(**attributes)
    _run_callbacks(evaluator, layers, "after_build", obj)
    if strategy == "create":
        _persist(fac.name, obj)
        _run_callbacks(evaluator, layers, "after_create", obj)
    return obj


def _run_callbacks(evaluator, layers, kind, obj):
    for layer in layers:
        for callback in layer.callbacks[kind]:
            evaluator.call(callback.__name__, callback, obj)


def _persist(factory_name, obj):
    if _to_create:
        _to_create(obj)
        return
    if not hasattr(obj, "save"):
        raise FactoryError(
            f"Factory {factory_name!r}: can't create a {type(obj).__name__}: it has no save()."
            " Give it a save() method, or set a hook with factory_bot.to_create(fn)."
        )
    obj.save()


def _dependencies(fn, skip=0):
    # Only required params: fake.paragraph(nb_sentences=3) must not be injected.
    try:
        params = list(inspect.signature(fn).parameters.values())[skip:]
    except (TypeError, ValueError):  # some builtins (dict, str) have no signature
        return []
    keyword = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    return [p.name for p in params if p.kind in keyword and p.default is p.empty]


def _lookup(name):
    if name not in _registry:
        raise FactoryError(f"No factory named {name!r}.{_suggest(name, _registry)}")
    return _registry[name]


def _suggest(name, options):
    close = difflib.get_close_matches(name, list(options), n=1)
    return f" Did you mean {close[0]!r}?" if close else ""


def _where(fn):
    code = getattr(fn, "__code__", None)
    return (
        f" ({os.path.basename(code.co_filename)}:{code.co_firstlineno})" if code else ""
    )
