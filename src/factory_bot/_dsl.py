"""The definition DSL: `f`, `@factory` and `@trait` act on the body executing right now."""

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, overload

from ._core import (
    Factory,
    FactoryError,
    _defining_factory,
    _Definition,
    _lookup,
    _name_of,
    _register,
    _signature,
    _stack,
    _takes_leading_argument,
    _where,
)

Body = TypeVar("Body", bound=Callable[[], object])
T = TypeVar("T")
Fn = TypeVar("Fn", bound=Callable[..., Any])


@overload
def factory(*, parent: Factory[T]) -> Callable[[Callable[[], object]], Factory[T]]: ...
@overload
def factory(*, parent: str) -> Callable[[Callable[[], object]], Factory[Any]]: ...
@overload
def factory(
    model: type[dict[Any, Any]], /, *, parent: str | Factory[Any] | None = None
) -> Callable[[Callable[[], object]], Factory[dict[str, Any]]]: ...
@overload
def factory(
    model: Callable[..., T], /, *, parent: str | Factory[Any] | None = None
) -> Callable[[Callable[[], object]], Factory[T]]: ...
def factory(model: Any = None, /, *, parent: Any = None) -> Any:
    """@factory(User) registers a factory; @factory(parent=user) a child of user."""
    if _is_body(model):
        return _define(model, None, None)
    return lambda body: _define(body, model, parent)


def _define(body, model, parent):
    _check_body(body, "factory")
    name = body.__name__
    if outer := _defining_factory():
        raise FactoryError(
            f"@factory def {name} is inside factory {outer!r}; define a child"
            f" after its parent, at the top level: @factory(parent={outer}) def {name}"
        )
    if parent is not None:
        parent_name = _name_of(parent)
        try:
            parent = _lookup(parent_name)
        except FactoryError as e:
            raise FactoryError(
                f"{e} @factory(parent={parent_name!r}) def {name}:"
                " a parent must be defined or imported before its child."
            ) from None
    elif model is None:
        # @factory(make_thing) with a zero-argument make_thing lands here too: same call.
        raise FactoryError(
            f"@factory needs a model or a parent: write @factory(User), @factory(dict)"
            f" or @factory(parent=user) above def {name}."
            f" If {name} is the model, it must take the attributes as keyword arguments."
        )
    if model is not None and not callable(model):
        raise FactoryError(f"model {model!r} is not callable", factory=name)
    definition = _Definition(name, model, body, parent=parent)
    _run_body(definition, body)  # a body that raises registers nothing
    _register(definition)
    return Factory(name)


def trait(body: Body) -> Body:
    """Declare a named set of attributes inside a factory, applied with build("user", "admin")."""
    _check_body(body, "trait")
    owner = _current(f"@trait def {body.__name__}")
    if existing := owner.traits.get(body.__name__):
        raise FactoryError(
            f"trait {body.__name__!r} is already defined{_where(existing.body)}",
        )
    definition = _Definition(body.__name__, None, body, kind="trait")
    _run_body(definition, body)
    owner.traits[body.__name__] = definition
    return body


class _ReadError(FactoryError, AttributeError):
    """An AttributeError too, so hasattr(f, ...), inspect.unwrap and doctest see a missing attribute."""


class _F:
    """`f`: assigning `f.name = value` declares an attribute on the body executing right now."""

    __slots__ = ()

    def __setattr__(self, name: str, value: object) -> None:
        owner = _current(f"f.{name} = ...", kinds=("factory", "trait"))
        if isinstance(value, Factory):
            raise FactoryError(
                f"f.{name} = {value.name} stores the factory itself, not an object it makes."
                f" Did you mean f.{name} = association({value.name})?"
            )
        owner.attributes[name] = value

    if not TYPE_CHECKING:  # reads stay a type error rather than Any

        def __getattr__(self, name):
            raise _ReadError(
                f"can't read f.{name}: f only declares attributes."
                f" To use another attribute, take it as a parameter: lambda {name}: ...",
            )

    def __repr__(self) -> str:
        stack = _stack.get()
        return (
            f"<f: {stack[-1].kind} {stack[-1].name!r}>"
            if stack
            else "<f: outside any factory>"
        )


f = _F()


def _check_body(body, kind):
    """A body is a plain def with no parameters: it runs once, now, and its name names it."""
    if not inspect.isfunction(body) or body.__name__ == "<lambda>":
        what = "a lambda" if inspect.isfunction(body) else repr(body)
        raise FactoryError(
            f"@{kind} takes a def, not {what}: the function's name names the {kind}"
        )
    name = body.__name__
    if (
        inspect.isgeneratorfunction(body)
        or inspect.iscoroutinefunction(body)
        or inspect.isasyncgenfunction(body)
    ):
        raise FactoryError(
            f"def {name} must be a plain function: its body runs once, now"
        )
    if params := _signature(body).parameters:
        raise FactoryError(
            f"def {name}({', '.join(params)}) takes no parameters: drop the parameter and import f"
            " (from factory_bot import f), and write @trait instead of @f.trait"
        )


def _run_body(definition, body):
    token = _stack.set((*_stack.get(), definition))
    try:
        body()
    except FactoryError as e:
        e.factory = e.factory or _defining_factory()  # the innermost frame wins
        raise
    finally:
        _stack.reset(token)


def _current(what, kinds=("factory",)):
    stack = _stack.get()
    if not stack:
        raise FactoryError(f"{what} only works inside a @factory body")
    if stack[-1].kind not in kinds:
        raise FactoryError(
            f"{what} must be directly inside the factory,"
            f" not inside {stack[-1].kind} {stack[-1].name!r}",
        )
    return stack[-1]


def _is_body(obj):
    # A model must accept kwargs, so a zero-argument function can only be a body. A lone
    # parameter named f is the pre-0.0.2 `def user(f)` body; `def make_point(x)` is a model.
    if not inspect.isfunction(obj):
        return False
    params = list(_signature(obj).parameters)
    return params in ([], ["f"])


def _callback(kind: str) -> Callable[[Fn], Fn]:
    def decorate(fn: Fn) -> Fn:
        name = getattr(fn, "__name__", None)  # a partial or callable object has none
        what = f"@{kind} def {name}" if name else f"@{kind} {fn!r}"
        owner = _current(what, kinds=("factory", "trait"))
        if not _takes_leading_argument(fn):
            factory_name = _defining_factory()
            shown = f"{what}{_signature(fn)}" if name and callable(fn) else what
            raise FactoryError(
                f"{shown} must take the instance first,"
                f" then other attributes by name: def {name or 'callback'}({factory_name}, ...)",
            )
        owner.callbacks[kind].append(fn)
        return fn

    decorate.__name__ = decorate.__qualname__ = kind
    decorate.__doc__ = f"Run fn(instance, **dependencies) {kind.replace('_', ' ')}; dependencies are injected by name."
    return decorate


after_build = _callback("after_build")
after_create = _callback("after_create")
