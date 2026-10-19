"""The definition DSL: `f`, `@factory` and `@trait` act on the body executing right now."""

import inspect
from collections.abc import Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypeVar

from ._core import FactoryError, _Definition, _register

Body = TypeVar("Body", bound=Callable[[], object])

# An immutable tuple: a thread or task that copied the context must never see another's pushes.
_stack: ContextVar[tuple[_Definition, ...]] = ContextVar(
    "factory_bot_stack", default=()
)


def factory(model: Callable[..., Any], /) -> Any:
    """@factory(User) registers a factory; nested in one, bare @factory declares a child."""
    if _is_body(model):
        if not _stack.get():
            raise FactoryError(
                f"@factory needs a model: write @factory(User) or @factory(dict) above def {model.__name__}"
            )
        return _define(model, None)
    return lambda body: _define(body, model)


def _define(body, model):
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
    owner = _current(f"@trait def {body.__name__}")
    definition = _Definition(body.__name__, None, body, kind="trait")
    _run_body(definition, body)
    owner.traits[body.__name__] = definition
    return body


class _F:
    """`f`: assigning `f.name = value` declares an attribute on the body executing right now."""

    __slots__ = ()

    def __setattr__(self, name: str, value: object) -> None:
        _current(f"f.{name} = ...", kinds=("factory", "trait")).attributes[name] = value

    if not TYPE_CHECKING:  # reads stay a type error rather than Any

        def __getattr__(self, name):
            stack = _stack.get()
            owner = f"Factory {_factory_name(stack)!r}: " if stack else ""
            raise FactoryError(
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


def _run_body(definition, body):
    name = body.__name__
    if inspect.isgeneratorfunction(body) or inspect.iscoroutinefunction(body):
        raise FactoryError(
            f"def {name} must be a plain function: its body runs once, now"
        )
    if params := inspect.signature(body).parameters:
        raise FactoryError(
            f"def {name}({', '.join(params)}) takes no parameters: drop the parameter and import f"
            " (from factory_bot import f), and write @trait instead of @f.trait"
        )
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
    # A model must accept kwargs, so a zero-argument function can only be a body.
    return inspect.isfunction(obj) and not inspect.signature(obj).parameters
