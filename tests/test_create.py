import pytest
from support.models import Post, User

from factory_bot import FactoryError, build, create, f, factory, persist_with, trait


def test_create_builds_then_saves():
    @factory(User)
    def user():
        f.first_name = "Ann"

        @trait
        def admin():
            f.admin = True

    created = create("user", "admin", last_name="Lee")
    assert created == User(first_name="Ann", last_name="Lee", admin=True)
    assert created.saved


def test_persist_with_replaces_save_for_every_factory():
    saved = []
    persist_with(saved.append)

    @factory(dict)
    def point():
        f.x = 1

    assert create("point") == {"x": 1}
    assert saved == [{"x": 1}]


def test_an_object_without_save_names_both_fixes():
    @factory(dict)
    def point():
        f.x = 1

    with pytest.raises(
        FactoryError,
        match=r"^Factory 'point': can't create a dict: it has no save\(\)\. "
        r"Give it a save\(\) method, or call persist_with\(\) with a function or a SQLAlchemy session\.$",
    ):
        create("point")


def test_persist_with_none_restores_save():
    persist_with(lambda obj: None)
    persist_with(None)

    @factory(User)
    def user():
        pass

    assert create("user").saved


class Session:
    """Just the SQLAlchemy shape persist_with relies on, plus a commit it must never call."""

    def __init__(self):
        self.calls = []

    def add(self, obj):
        self.calls.append(("add", obj))

    def flush(self):
        self.calls.append(("flush",))

    def commit(self):
        self.calls.append(("commit",))


def test_persist_with_a_session_adds_and_flushes_each_object_without_committing():
    session = Session()
    assert persist_with(session) is session

    @factory(dict)
    def point():
        f.x = 1

    first, second = create("point"), create("point")
    assert session.calls == [("add", first), ("flush",), ("add", second), ("flush",)]


def test_persist_with_a_callable_session_treats_it_as_a_session():
    # scoped_session is callable, but it has add and flush, so it's a session.
    class Scoped(Session):
        def __call__(self, **kw):
            raise AssertionError("called like a hook")

    session = Scoped()
    persist_with(session)

    @factory(dict)
    def point():
        f.x = 1

    point_ = create("point")
    assert session.calls == [("add", point_), ("flush",)]


def test_persist_with_anything_else_lists_what_it_takes():
    message = (
        r"^persist_with\(\) takes a function, a SQLAlchemy session, or None to restore obj\.save\(\);"
        r" got 'users'\.$"
    )
    with pytest.raises(FactoryError, match=message):
        persist_with("users")


def test_persist_with_inside_a_body_points_at_the_global_hook():
    message = r"^Factory 'point': persist_with\(\) sets the global save hook, so call it outside any factory body, e\.g\. in a fixture\.$"
    with pytest.raises(FactoryError, match=message):

        @factory(dict)
        def point():
            persist_with(print)

    with pytest.raises(FactoryError, match=message):

        @factory(dict)
        def point():
            @trait
            def stored():
                persist_with(print)


def test_create_while_a_factory_is_being_defined_is_an_error():
    @factory(User)
    def user():
        pass

    message = (
        r"^Factory 'post': create\('user'\) ran while a factory was being defined, so it would run once, at import\."
        r" Use association\('user'\), which builds or creates to match the parent, or make it lazy: lambda: create\('user'\)$"
    )
    with pytest.raises(FactoryError, match=message):

        @factory(Post)
        def post():
            f.author = create("user")

    with pytest.raises(
        FactoryError, match=r"^Factory 'draft': build\('user'\) ran while"
    ):

        @factory(Post)
        def draft():
            f.author = build("user")


def test_create_in_a_lazy_attribute_runs_at_build_time():
    @factory(User)
    def user():
        pass

    @factory(Post)
    def post():
        f.author = lambda: create("user")

    assert create("post").author.saved
