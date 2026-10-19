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
        r"Give it a save\(\) method, or set a global hook with persist_with\(fn\)\.$",
    ):
        create("point")


def test_persist_with_none_restores_save():
    persist_with(lambda obj: None)
    persist_with(None)

    @factory(User)
    def user():
        pass

    assert create("user").saved


def test_persist_with_inside_a_body_points_at_the_global_hook():
    message = r"^Factory 'point': persist_with\(fn\) sets the global save hook, so call it outside any factory body, e\.g\. in a fixture\.$"
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
