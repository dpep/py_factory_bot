import pytest
from support.models import Post, User

from factory_bot import FactoryError, build, create, f, factory, to_create, trait


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


def test_to_create_replaces_save_for_every_factory():
    saved = []
    to_create(saved.append)

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
        r"Give it a save\(\) method, or set a hook with to_create\(fn\),"
        r" at top level or inside the factory\.$",
    ):
        create("point")


def test_to_create_none_restores_save():
    to_create(lambda obj: None)
    to_create(None)

    @factory(User)
    def user():
        pass

    assert create("user").saved


def test_to_create_inside_a_body_sets_that_factorys_hook_and_children_inherit_it():
    stored, global_saved = [], []
    to_create(global_saved.append)

    @factory(dict)
    def point():
        f.x = 1

        @to_create
        def store(obj):
            stored.append(obj)

        @factory
        def origin():
            f.x = 0

    @factory(dict)
    def other():
        pass

    create("point")
    create("origin")
    create("other")
    assert stored == [{"x": 1}, {"x": 0}]
    assert global_saved == [{}]


def test_to_create_inside_a_trait_is_rejected():
    message = r"^Factory 'point': to_create must be directly inside the factory, not inside trait 'stored'$"
    with pytest.raises(FactoryError, match=message):

        @factory(dict)
        def point():
            @trait
            def stored():
                to_create(print)


def test_create_while_a_factory_is_being_defined_is_an_error():
    @factory(User)
    def user():
        pass

    message = (
        r"^Factory 'post': create\('user'\) ran while a factory was being defined, so it would run once, at import\."
        r" Make it lazy: lambda: create\('user'\), or use association\('user'\)$"
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
