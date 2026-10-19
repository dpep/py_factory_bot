import subprocess
import sys
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool
from support.sa_models import Author, Base, Book

import factory_bot.sqlalchemy
from factory_bot import (
    FactoryError,
    association,
    create,
    create_list,
    f,
    factory,
    persist_with,
)


@pytest.fixture(scope="module")
def engine():
    # One shared in-memory DB, with FK enforcement sqlite leaves off by default.
    engine = create_engine("sqlite://", poolclass=StaticPool)
    event.listen(
        engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@contextmanager
def rolled_back(engine):
    """SQLAlchemy's documented test recipe: a session joined to an outer transaction."""
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()


@pytest.fixture
def session(engine):
    with rolled_back(engine) as session:
        persist_with(factory_bot.sqlalchemy.persist_with(session))
        yield session


@pytest.fixture(autouse=True)
def book_factory():
    @factory(Author)
    def author():
        f.name = "Ann"

    @factory(Book)
    def book():
        f.title = "Dune"
        f.author = association("author")


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_create_adds_and_flushes_to_the_session(session):
    book = create("book")
    assert book.id is not None
    assert session.get(Book, book.id) is book


def test_associations_are_flushed_before_the_rows_that_reference_them(session):
    book = create("book")
    assert book.author.id is not None
    assert book.author_id == book.author.id


def test_an_id_override_makes_no_spare_author(session):
    ann = create("author")
    book = create("book", author_id=ann.id)
    assert count(session, Author) == 1
    assert book.author_id == ann.id
    session.expire(book)
    assert book.author is ann


def test_the_fk_constraint_is_really_enforced(session):
    with pytest.raises(IntegrityError):
        session.execute(insert(Book).values(title="Orphan", author_id=999))


def test_it_flushes_without_committing(engine):
    with Session(engine) as session:
        persist_with(factory_bot.sqlalchemy.persist_with(session))
        create_list("book", 2)
        session.rollback()
        assert count(session, Book) == 0


def test_rolling_back_the_test_transaction_leaves_the_db_empty(engine):
    with rolled_back(engine) as session:
        persist_with(factory_bot.sqlalchemy.persist_with(session))
        create("book")
        assert count(session, Book) == 1

    with Session(engine) as fresh:
        assert count(fresh, Book) == count(fresh, Author) == 0


def test_a_scoped_session_works_as_is(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        registry = scoped_session(sessionmaker(bind=connection))
        persist_with(factory_bot.sqlalchemy.persist_with(registry))

        book = create("book")
        assert registry().get(Book, book.id) is book

        registry.remove()
        transaction.rollback()


def test_a_session_factory_is_rejected_with_the_fix():
    message = (
        r"^persist_with\(\) takes a Session, not a factory of them\. "
        r"Pass the test's session, e.g\. persist_with\(session\)\.$"
    )
    with pytest.raises(FactoryError, match=message):
        factory_bot.sqlalchemy.persist_with(sessionmaker())


def test_importing_factory_bot_never_imports_an_orm():
    code = (
        "import sys, factory_bot, factory_bot.sqlalchemy;"
        "print(sorted({m.split('.')[0] for m in sys.modules} & {'django', 'sqlalchemy'}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"
