import copy
import difflib
import inspect
import itertools
import os
import weakref

_registry: dict[str, "_Factory"] = {}
_sequences: weakref.WeakSet["_Sequence"] = weakref.WeakSet()
_to_create = None


class FactoryError(Exception):
    pass


def factory(model):
    """Register the decorated function as a factory for `model`, e.g. @factory(User)."""
    if _is_body(model):
        raise FactoryError(
            f"@factory needs a model: write @factory(User) or @factory(dict) above def {model.__name__}"
        )

    def register(body):
        name = body.__name__
        if not callable(model):
            raise FactoryError(f"Factory {name!r}: model {model!r} is not callable")
        if name in _registry:
            raise FactoryError(
                f"Factory {name!r} is already defined{_where(_registry[name].body)}"
            )
        _registry[name] = _Factory(name, model, body)
        return body

    return register


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


def clear_factories():
    _registry.clear()


def reset_sequences():
    for seq in _sequences:
        seq.reset()


class _Factory:
    def __init__(self, name, model, body):
        self.name, self.model, self.body = name, model, body
        self.attributes = {}
        self.traits = {}
        body(_Definition(self, self.attributes))

    def definitions(self, traits):
        definitions = dict(self.attributes)
        for trait in traits:
            if trait not in self.traits:
                raise FactoryError(
                    f"Factory {self.name!r} has no trait {trait!r}.{_suggest(trait, self.traits)}"
                    f" Traits: {', '.join(self.traits) or '(none)'}"
                )
            definitions |= self.traits[trait]
        return definitions


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


class _Definition:
    """The `f` in `def user(f):`. Assigning to it declares an attribute."""

    def __init__(self, factory, attributes):
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_attributes", attributes)

    def __setattr__(self, name, value):
        self._attributes[name] = value

    def trait(self, body):
        # Run the body now, once: re-running it per build would restart its sequences.
        attributes = {}
        body(_Definition(self._factory, attributes))
        self._factory.traits[body.__name__] = attributes
        return body

    def __getattr__(self, name):
        raise FactoryError(
            f"Factory {self._factory.name!r}: can't read f.{name} in a definition."
            f" To use another attribute, take it as a parameter: lambda {name}: ..."
        )


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
        return not (
            self.strategy == "attributes_for" and isinstance(value, _Association)
        )

    def get(self, name, needed_by=None):
        if name in self.values:
            return self.values[name]
        definitions = self.definitions
        if name not in definitions:
            raise FactoryError(
                f"Factory {self.factory_name!r}: {needed_by!r} depends on {name!r}, which is not defined."
                f"{_suggest(name, definitions)}{_where(definitions[needed_by])}"
            )
        if name in self.resolving:
            cycle = " -> ".join([*self.resolving[self.resolving.index(name) :], name])
            raise FactoryError(
                f"Factory {self.factory_name!r}: circular dependency: {cycle}"
            )
        self.resolving.append(name)
        try:
            self.values[name] = self.evaluate(name, definitions[name])
        finally:
            self.resolving.pop()
        return self.values[name]

    def evaluate(self, name, value):
        if isinstance(value, _Sequence):
            return value.next()
        if isinstance(value, _Association):
            return self.associate(name, value)
        if callable(value):
            return value(
                **{dep: self.get(dep, needed_by=name) for dep in _dependencies(value)}
            )
        if isinstance(value, (list, dict, set)):
            return copy.copy(value)
        return value

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
    attributes = _Evaluator(
        strategy, fac.name, fac.definitions(traits), overrides
    ).attributes()
    if strategy == "attributes_for":
        return attributes
    obj = fac.model(**attributes)
    if strategy == "create":
        _persist(fac.name, obj)
    return obj


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


def _dependencies(fn):
    # Only required params: fake.paragraph(nb_sentences=3) must not be injected.
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):  # some builtins (dict, str) have no signature
        return []
    keyword = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    return [p.name for p in params if p.kind in keyword and p.default is p.empty]


def _lookup(name):
    if name not in _registry:
        raise FactoryError(f"No factory named {name!r}.{_suggest(name, _registry)}")
    return _registry[name]


def _is_body(model):
    # Bare @factory hands us the body itself: a function of exactly one required argument.
    if not inspect.isfunction(model):
        return False
    params = list(inspect.signature(model).parameters.values())
    return (
        len(params) == 1
        and params[0].kind is params[0].POSITIONAL_OR_KEYWORD
        and params[0].default is params[0].empty
    )


def _suggest(name, options):
    close = difflib.get_close_matches(name, list(options), n=1)
    return f" Did you mean {close[0]!r}?" if close else ""


def _where(fn):
    code = getattr(fn, "__code__", None)
    return (
        f" ({os.path.basename(code.co_filename)}:{code.co_firstlineno})" if code else ""
    )
