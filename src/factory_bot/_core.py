import copy
import difflib
import inspect
import os

_registry: dict[str, "_Factory"] = {}


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
    return _lookup(name).build(overrides)


def clear_factories():
    _registry.clear()


class _Factory:
    def __init__(self, name, model, body):
        self.name, self.model, self.body = name, model, body
        self.attributes = {}
        body(_Definition(self))

    def build(self, overrides):
        return self.model(**self.attributes_for(overrides))

    def attributes_for(self, overrides):
        values = {name: _evaluate(value) for name, value in self.attributes.items()}
        return values | overrides


class _Definition:
    """The `f` in `def user(f):`. Assigning to it declares an attribute."""

    def __init__(self, factory):
        object.__setattr__(self, "_factory", factory)

    def __setattr__(self, name, value):
        self._factory.attributes[name] = value


def _evaluate(value):
    if isinstance(value, (list, dict, set)):
        return copy.copy(value)
    return value


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
