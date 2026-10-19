"""The definition DSL: `f`, `@factory` and `@trait` act on the body executing right now."""

import inspect
from collections.abc import Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypeVar, overload

from ._core import FactoryError, _Definition, _register, _set_to_create, _where

Body = TypeVar("Body", bound=Callable[[], object])
Fn = TypeVar("Fn", bound=Callable[..., Any])

# An immutable tuple: a thread or task that copied the context must never see another's pushes.
_stack: ContextVar[tuple[_Definition, ...]] = ContextVar(
    "factory_bot_stack", default=()
)


def _defining() -> bool:
    """Whether a factory or trait body is executing right now, in this context."""
    return bool(_stack.get())


def _defining_name() -> str | None:
    """The innermost factory whose body is executing right now, if any."""
    stack = _stack.get()
    return _factory_name(stack) if stack else None


def factory(model: Callable[..., Any], /) -> Callable[[Body], Body]:
    """@factory(User) registers a factory; nested in one, bare @factory declares a child."""
    if _is_body(model):
        _check_body(model, "factory")
        if not _stack.get():
            raise FactoryError(
                f"@factory needs a model: write @factory(User) or @factory(dict) above def {model.__name__}"
            )
        # Typed for @factory(Model); the bare nested form's return value is never used.
        return _define(model, None)
    return lambda body: _define(body, model)


def _define(body, model):
    _check_body(body, "factory")
    name = body.__name__
    if model is not None and not callable(model):
        raise FactoryError(f"Factory {name!r}: model {model!r} is not callable")
    parent = _current(f"@factory def {name}") if _stack.get() else None
    definition = _Definition(name, model, body, parent=parent)
    _run_body(
        definition, body
    )  # a body that raises registers nothing, children included
    if parent:
        parent.children.append(definition)
    else:
        _register(definition)
    return body


def trait(body: Body) -> Body:
    """Declare a named set of attributes inside a factory, applied with build("user", "admin")."""
    _check_body(body, "trait")
    owner = _current(f"@trait def {body.__name__}")
    if existing := owner.traits.get(body.__name__):
        raise FactoryError(
            f"Factory {owner.name!r}: trait {body.__name__!r} is already defined{_where(existing.body)}"
        )
    definition = _Definition(body.__name__, None, body, kind="trait")
    _run_body(definition, body)
    owner.traits[body.__name__] = definition
    return body


@overload
def to_create(fn: None, /) -> None: ...
@overload
def to_create(fn: Fn, /) -> Fn: ...
def to_create(fn, /):
    """Persist created objects with fn(obj) instead of obj.save().

    Inside a factory body it sets that factory's hook (children inherit it); at top level
    it sets the global one, and to_create(None) restores obj.save().
    """
    if _stack.get():
        _current("to_create").to_create = fn
    else:
        _set_to_create(fn)
    return fn


class _ReadError(FactoryError, AttributeError):
    """An AttributeError too, so hasattr(f, ...), inspect.unwrap and doctest see a missing attribute."""


class _F:
    """`f`: assigning `f.name = value` declares an attribute on the body executing right now."""

    __slots__ = ()

    def __setattr__(self, name: str, value: object) -> None:
        _current(f"f.{name} = ...", kinds=("factory", "trait")).attributes[name] = value

    if not TYPE_CHECKING:  # reads stay a type error rather than Any

        def __getattr__(self, name):
            stack = _stack.get()
            owner = f"Factory {_factory_name(stack)!r}: " if stack else ""
            raise _ReadError(
                f"{owner}can't read f.{name} in a definition."
                f" To use another attribute, take it as a parameter: lambda {name}: ..."
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
    finally:
        _stack.reset(token)


def _current(what, kinds=("factory",)):
    stack = _stack.get()
    if not stack:
        raise FactoryError(f"{what} only works inside a @factory body")
    if stack[-1].kind not in kinds:
        raise FactoryError(
            f"Factory {_factory_name(stack)!r}: {what} must be directly inside the factory,"
            f" not inside {stack[-1].kind} {stack[-1].name!r}"
        )
    return stack[-1]


def _factory_name(stack):
    return next(d.name for d in reversed(stack) if d.kind == "factory")


def _is_body(obj):
    # A model must accept kwargs, so a zero-argument function can only be a body. One
    # required positional parameter is the pre-0.0.2 `def user(f)` body, as 0.0.1 read it.
    if not inspect.isfunction(obj):
        return False
    params = list(inspect.signature(obj).parameters.values())
    return not params or (
        len(params) == 1
        and params[0].kind is params[0].POSITIONAL_OR_KEYWORD
        and params[0].default is params[0].empty
    )


def _callback(kind: str) -> Callable[[Fn], Fn]:
    def decorate(fn: Fn) -> Fn:
        name = getattr(fn, "__name__", None)  # a partial or callable object has none
        what = f"@{kind} def {name}" if name else f"@{kind} {fn!r}"
        owner = _current(what, kinds=("factory", "trait"))
        if not _takes_instance_first(fn):
            factory_name = _factory_name(_stack.get())
            shown = f"{what}{inspect.signature(fn)}" if name and callable(fn) else what
            raise FactoryError(
                f"Factory {factory_name!r}: {shown} must take the instance first,"
                f" then other attributes by name: def {name or 'callback'}({factory_name}, ...)"
            )
        owner.callbacks[kind].append(fn)
        return fn

    decorate.__name__ = decorate.__qualname__ = kind
    decorate.__doc__ = f"Run fn(instance, **dependencies) {kind.replace('_', ' ')}; dependencies are injected by name."
    return decorate


def _takes_instance_first(fn):
    if not callable(fn):
        return False
    try:
        params = inspect.signature(fn).parameters.values()
    except ValueError:  # no inspectable signature; trust it
        return True
    first = next(iter(params), None)
    return first is not None and first.kind in (
        first.POSITIONAL_ONLY,
        first.POSITIONAL_OR_KEYWORD,
        first.VAR_POSITIONAL,
    )


after_build = _callback("after_build")
after_create = _callback("after_create")
