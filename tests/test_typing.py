"""The public API's types, as a user's checker sees them. The gate runs pyright on this file;
at runtime assert_type is a no-op, so the test only proves the calls still work."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, assert_type

from faker import Faker

from factory_bot import (
    after_build,
    after_create,
    association,
    attributes_for,
    build,
    build_list,
    build_pair,
    create,
    create_list,
    create_pair,
    f,
    factory,
    fake,
    seed,
    sequence,
    to_create,
    trait,
    transient,
)
from factory_bot.sqlalchemy import persist_with


@dataclass
class Book:
    title: str = ""
    copies: int = 0
    saved: bool = False

    def save(self) -> None:
        self.saved = True


def test_the_public_api_has_honest_types():
    @factory(Book)
    def book() -> None:
        # Markers are opaque: a user can pass them to factory_bot and nothing else.
        assert_type(sequence(lambda n: f"Book {n}"), object)
        assert_type(transient(3), object)
        f.title = sequence(lambda n: f"Book {n}")
        f.copies = transient(3)

        @trait
        def signed() -> None:
            f.title = "Signed"

        assert_type(signed, Callable[[], None])

    assert_type(book, Callable[[], None])

    @factory(dict)
    def shelf() -> None:
        # Inside a build, association() returns the built object, so it can't be a marker type.
        f.books = lambda: [association("book") for _ in range(2)]
        f.first = association("book")

    assert_type(association("book"), Any)
    assert_type(build("book"), Any)
    assert_type(create("book"), Any)
    assert_type(attributes_for("book"), dict[str, Any])
    assert_type(build_list("book", 2), list[Any])
    assert_type(create_list("book", 2), list[Any])
    assert_type(build_pair("book"), list[Any])
    assert_type(create_pair("book"), list[Any])
    assert_type(build("shelf")["books"], Any)

    assert_type(to_create(None), None)
    assert_type(persist_with(_Session()), Callable[[object], None])
    assert_type(fake, Faker)
    assert_type(seed(1), None)


# Static only: decorators hand back what they were given, so a body or hook keeps its type.
def _decorators_keep_the_type(
    hook: Callable[[object], None], callback: Callable[[Book, int], None]
) -> None:
    assert_type(to_create(hook), Callable[[object], None])
    assert_type(after_build(callback), Callable[[Book, int], None])
    assert_type(after_create(callback), Callable[[Book, int], None])


def _reading_f_is_a_type_error() -> None:
    # Fails the gate if f.<name> ever stops being a type error: the ignore would be unneeded.
    _ = f.title  # pyright: ignore[reportAttributeAccessIssue]


class _Session:
    def add(self, obj: object) -> None:
        pass

    def flush(self) -> None:
        pass
