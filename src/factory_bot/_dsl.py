"""The definition DSL: `f`, `@factory` and `@trait` act on the body executing right now."""

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, overload

from ._core import (
    Factory,
    FactoryError,
    _defining_factory,
    _Definition,
    _register,
    _stack,
    _takes_leading_argument,
    _where,
)

Body = TypeVar("Body", bound=Callable[[], object])
T = TypeVar("T")
Fn = TypeVar("Fn", bound=Callable[..., Any])


# A zero-argument function is a body, never a model: a model takes keyword arguments.
@overload
def factory(body: Callable[[], None], /) -> Factory[Any]: ...  # pyright: ignore[reportOverlappingOverload]
@overload
def factory(
    model: type[dict[Any, Any]], /
) -> Callable[[Callable[[], object]], Factory[dict[str, Any]]]: ...
@overload
def factory(
    model: Callable[..., T], /
) -> Callable[[Callable[[], object]], Factory[T]]: ...
def factory(model: Any, /) -> Any:
    """@factory(User) registers a factory; nested in one, bare @factory declares a child."""
    if _is_body(model):
        _check_body(model, "factory")
        if not _stack.get():
            raise FactoryError(
                f"@factory needs a model: write @factory(User) or @factory(dict) above def {model.__name__}"
            )
        return _define(model, None)
    return lambda body: _define(body, model)


def _define(body, model):
    _check_body(body, "factory")
    name = body.__name__
    if model is not None and not callable(model):
        raise FactoryError(f"model {model!r} is not callable", factory=name)
    parent = _current(f"@factory def {name}") if _stack.get() else None
    definition = _Definition(name, model, body, parent=parent)
    _run_body(
        definition, body
    )  # a body that raises registers nothing, children included
    if parent:
        parent.children.append(definition)
    else:
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
        _current(f"f.{name} = ...", kinds=("factory", "trait")).attributes[name] = value

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
    if params := inspect.signature(body).parameters:
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
    params = list(inspect.signature(obj).parameters)
    return params in ([], ["f"])


def _callback(kind: str) -> Callable[[Fn], Fn]:
    def decorate(fn: Fn) -> Fn:
        name = getattr(fn, "__name__", None)  # a partial or callable object has none
        what = f"@{kind} def {name}" if name else f"@{kind} {fn!r}"
        owner = _current(what, kinds=("factory", "trait"))
        if not _takes_leading_argument(fn):
            factory_name = _defining_factory()
            shown = f"{what}{inspect.signature(fn)}" if name and callable(fn) else what
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
