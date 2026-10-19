import pytest
from support.models import User

from factory_bot import FactoryError, create, f, factory, to_create, trait


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
        r"Give it a save\(\) method, or set a hook with factory_bot\.to_create\(fn\)\.$",
    ):
        create("point")


def test_to_create_none_restores_save():
    to_create(lambda obj: None)
    to_create(None)

    @factory(User)
    def user():
        pass

    assert create("user").saved
