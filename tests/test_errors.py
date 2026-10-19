"""Errors raised by models and user code keep their type and gain a note naming the factory."""

import re
from dataclasses import dataclass

import pytest
from support.models import Post, User

from factory_bot import (
    FactoryError,
    after_build,
    association,
    build,
    create,
    f,
    factory,
    sequence,
    transient,
)


@dataclass
class Strict:
    title: str = ""

    def __post_init__(self):
        if not self.title:
            raise ValueError("title is required")


def notes(excinfo):
    return getattr(excinfo.value, "__notes__", [])


def test_a_model_error_names_the_factory():
    @factory(Strict)
    def untitled():
        pass

    with pytest.raises(ValueError, match="title is required") as excinfo:
        build("untitled")
    assert notes(excinfo) == ["while building factory 'untitled'"]


def test_an_unknown_keyword_suggests_an_attribute_of_the_factory():
    def post(**kwargs):  # Django's wording
        names = ", ".join(repr(k) for k in kwargs if k != "title")
        raise TypeError(f"Post() got unexpected keyword arguments: {names}")

    @factory(post)
    def post():
        f.title = "Hi"

    with pytest.raises(TypeError) as excinfo:
        build("post", titel="x")
    assert notes(excinfo) == [
        "while building factory 'post'",
        "'titel' is not an attribute of factory 'post'. Did you mean 'title'?",
    ]


def test_a_double_underscore_override_says_deep_overrides_are_not_supported():
    @factory(User)
    def author():
        pass

    @factory(Post)
    def post():
        f.author = association("author")

    with pytest.raises(TypeError) as excinfo:
        build("post", author__first_name="Bea")
    assert notes(excinfo)[-1] == (
        "'author__first_name': deep overrides aren't supported."
        ' Override the association instead: author=association("author", first_name=...)'
    )


def test_an_error_in_a_lazy_attribute_names_the_factory_attribute_and_line():
    @factory(dict)
    def user():
        f.first_name = "Ann"
        f.email = lambda first_name: first_name.nope

    with pytest.raises(AttributeError) as excinfo:
        build("user")
    assert len(notes(excinfo)) == 1
    assert re.fullmatch(
        r"while building factory 'user', attribute 'email' \(test_errors\.py:\d+\)",
        notes(excinfo)[0],
    )


def test_an_error_in_a_dependency_is_noted_once_per_build():
    @factory(dict)
    def user():
        f.first_name = lambda: 1 / 0
        f.email = lambda first_name: first_name

    with pytest.raises(ZeroDivisionError) as excinfo:
        build("user")
    assert [n.split(" (")[0] for n in notes(excinfo)] == [
        "while building factory 'user', attribute 'first_name'"
    ]


def test_an_error_in_an_association_leaves_a_trail():
    @factory(Strict)
    def untitled():
        pass

    @factory(dict)
    def post():
        f.thing = association("untitled")

    with pytest.raises(ValueError) as excinfo:
        build("post")
    assert notes(excinfo) == [
        "while building factory 'untitled'",
        "while building factory 'post', attribute 'thing'",
    ]


def test_a_failing_save_names_the_factory():
    class Unsaveable:
        def __init__(self, **kwargs):
            pass

        def save(self):
            raise RuntimeError("database is down")

    @factory(Unsaveable)
    def thing():
        pass

    with pytest.raises(RuntimeError) as excinfo:
        create("thing")
    assert notes(excinfo) == ["while saving factory 'thing'"]


def test_an_error_in_a_callback_names_the_factory_and_callback():
    @factory(dict)
    def user():
        @after_build
        def explode(user):
            raise KeyError("boom")

    with pytest.raises(KeyError) as excinfo:
        build("user")
    assert re.fullmatch(
        r"while building factory 'user', callback 'explode' \(test_errors\.py:\d+\)",
        notes(excinfo)[0],
    )


def test_a_callback_whose_dependency_fails_is_noted_once():
    @factory(dict)
    def user():
        f.n = transient(lambda: 1 / 0)

        @after_build
        def use(user, n):
            pass

    with pytest.raises(ZeroDivisionError) as excinfo:
        build("user")
    assert [n.split(" (")[0] for n in notes(excinfo)] == [
        "while building factory 'user', attribute 'n'"
    ]


def test_a_factory_error_raised_in_a_body_names_the_factory():
    with pytest.raises(
        FactoryError, match=r"^Factory 'user': sequence\(\) takes a function"
    ):

        @factory(dict)
        def user():
            f.name = sequence("user")


def test_a_factory_error_raised_in_a_build_names_the_factory():
    @factory(dict)
    def shelf():
        f.book = lambda: build("nope")

    with pytest.raises(
        FactoryError, match=r"^Factory 'shelf': No factory named 'nope'\.\n"
    ):
        build("shelf")


def test_a_nested_factory_error_names_the_innermost_factory():
    @factory(dict)
    def inner():
        f.y = lambda missing: 1

    @factory(dict)
    def outer():
        f.i = association("inner")

    with pytest.raises(FactoryError, match=r"^Factory 'inner': 'y' depends on"):
        build("outer")


def test_a_factory_error_keeps_the_steps_that_led_to_it():
    @factory(dict)
    def inner():
        f.y = lambda missing: 1

    @factory(dict)
    def outer():
        f.i = association("inner")
        f.j = lambda: build("nope")

    with pytest.raises(FactoryError) as excinfo:
        build("outer", j=None)
    # The inner error names its own step; the outer build adds how it got there.
    assert notes(excinfo) == ["while building factory 'outer', attribute 'i'"]

    with pytest.raises(FactoryError) as excinfo:
        build("outer", i=None)
    assert [n.split(" (")[0] for n in notes(excinfo)] == [
        "while building factory 'outer', attribute 'j'"
    ]
