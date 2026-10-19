"""The public API's types, as a user's checker sees them. The gate runs pyright on this file;
at runtime assert_type is a no-op, so the test only proves the calls still work."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict, assert_type

from faker import Faker

from factory_bot import (
    Factory,
    after_build,
    after_create,
    association,
    attributes_for,
    build,
    build_list,
    create,
    create_list,
    f,
    factory,
    fake,
    lint,
    persist_with,
    seed,
    sequence,
    trait,
    transient,
)


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
        assert_type(sequence(lambda n: assert_type(n, int)), object)
        assert_type(sequence(lambda n, title: f"{title}-{n}"), object)
        f.title = sequence(lambda n: f"Book {n}")
        f.copies = transient(3)

        @trait
        def signed() -> None:
            f.title = "Signed"

        assert_type(signed, Callable[[], None])

        @factory
        def paperback() -> None:
            f.title = "Paperback"

        # The decorator never sees the parent, so a child can't know its model.
        assert_type(paperback, Factory[Any])

    assert_type(book, Factory[Book])

    # A top-level child names its parent, so it is typed by the parent's model.
    @factory(parent=book)
    def hardcover() -> None:
        f.title = "Hardcover"

    @factory(Novel, parent=book)
    def novel() -> None:
        pass

    @factory(parent="book")
    def by_name() -> None:
        pass

    assert_type(hardcover, Factory[Book])
    assert_type(novel, Factory[Novel])
    assert_type(by_name, Factory[Any])
    assert_type(build(hardcover), Book)

    @factory(dict)
    def shelf() -> None:
        # Inside a build, association() returns the built object, so it can't be a marker type.
        f.books = lambda: [association("book") for _ in range(2)]
        f.first = association(book)

    assert_type(shelf, Factory[dict[str, Any]])
    assert_type(build(shelf), dict[str, Any])
    assert_type(build("shelf")["books"], Any)

    # A name gives Any; the factory itself gives its model.
    assert_type(build("book"), Any)
    assert_type(create("book"), Any)
    assert_type(build_list("book", 2), list[Any])
    assert_type(create_list("book", 2), list[Any])
    assert_type(build(book, "signed", title="x"), Book)
    assert_type(create(book), Book)
    assert_type(build_list(book, 2), list[Book])
    assert_type(create_list(book, 2), list[Book])
    assert_type(attributes_for(book), dict[str, Any])
    assert_type(attributes_for("book"), dict[str, Any])
    assert_type(association(book), Any)
    assert_type(association("book"), Any)
    assert_type(lint(), None)
    assert_type(lint(book, "shelf"), None)
    assert_type(lint(book, strategy="create"), None)

    assert_type(persist_with(None), None)
    assert_type(persist_with(_Session()), _Session)
    assert_type(fake, Faker)
    assert_type(seed(1), None)


class Novel(Book):
    pass


class BookDict(TypedDict):
    title: str


def _make_book(**attrs: Any) -> Book:
    return Book(**attrs)


# Static only, from here down: these are never called.
def _models_of_every_kind() -> None:
    @factory(BookDict)
    def book_dict() -> None:
        f.title = "Dune"

    @factory(_make_book)
    def made() -> None:
        f.title = "Dune"

    assert_type(book_dict, Factory[BookDict])
    assert_type(made, Factory[Book])


def _handles_are_covariant(book: Factory[Book], novel: Factory[Novel], c: bool) -> None:
    def takes(fac: Factory[Book]) -> Book:
        return build(fac)

    takes(novel)
    assert_type(build(book if c else novel), Book)
    assert_type(build(book if c else "book"), Book | Any)


def _misuse_is_a_type_error(book: Factory[Book], untyped: Any) -> None:
    # Each ignore must stay needed: an unneeded one fails the gate.
    _n: int = build(book)  # pyright: ignore[reportAssignmentType]
    build(Book)  # pyright: ignore[reportCallIssue, reportArgumentType]
    _ = build(book).titel  # pyright: ignore[reportAttributeAccessIssue]
    book()  # pyright: ignore[reportCallIssue]
    book.build()  # pyright: ignore[reportAttributeAccessIssue]
    lint(strategy="attributes_for")  # pyright: ignore[reportArgumentType]
    persist_with("users")  # pyright: ignore[reportCallIssue, reportArgumentType]

    # A model typed Any matches every overload, so pyright keeps the undecorated function:
    # use the factory's name, or cast.
    @factory(untyped)
    def thing() -> None:
        pass

    build(thing)  # pyright: ignore[reportCallIssue, reportArgumentType]


# Decorators hand back what they were given, so a body or hook keeps its type.
def _decorators_keep_the_type(
    hook: Callable[[object], None], callback: Callable[[Book, int], None]
) -> None:
    assert_type(persist_with(hook), Callable[[object], None])
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
