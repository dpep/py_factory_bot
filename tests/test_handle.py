import copy
import pickle
import re
from dataclasses import dataclass

import pytest

from factory_bot import (
    Factory,
    FactoryError,
    association,
    attributes_for,
    build,
    build_list,
    clear_factories,
    create_list,
    f,
    factory,
    persist_with,
    trait,
)


@dataclass
class User:
    name: str
    admin: bool = False


def test_the_decorator_returns_a_handle_that_goes_wherever_a_name_goes():
    @factory(User)
    def user():
        f.name = "Ann"

        @trait
        def admin():
            f.admin = True

    persist_with(lambda obj: None)
    assert isinstance(user, Factory)
    assert user.name == "user"
    assert build(user, "admin", name="Bea") == User("Bea", admin=True)
    assert build("user") == build(user)
    assert attributes_for(user) == {"name": "Ann"}
    assert build_list(user, 2) == create_list(user, 2) == [User("Ann"), User("Ann")]


def test_a_child_returns_a_handle_too():
    @factory(User)
    def user():
        f.name = "Ann"

    @factory(parent=user)
    def guest():
        f.name = "Guest"

    assert guest.name == "guest"
    assert build(guest) == User("Guest")


def test_a_handle_is_only_a_name():
    @factory(dict)
    def thing():
        f.a = 1

    assert repr(thing) == "<Factory 'thing'>"
    assert not callable(thing)  # so the value rule never calls it
    assert build(pickle.loads(pickle.dumps(thing))) == {"a": 1}
    assert build(copy.deepcopy(thing)) == {"a": 1}


def test_a_stale_handle_after_clear_factories_names_the_factory():
    @factory(dict)
    def thing():
        f.a = 1

    clear_factories()
    with pytest.raises(FactoryError, match=r"^No factory named 'thing'\.$"):
        build(thing)


def test_passing_something_else_explains_shadowing():
    message = (
        "Expected a factory or a factory's name, not User(name='Ann', admin=False)."
        " If a fixture or variable shadows the factory, use its name or its module: factories.user"
    )
    with pytest.raises(FactoryError, match=f"^{re.escape(message)}$"):
        build(User("Ann"))


def test_association_takes_a_handle():
    @factory(User)
    def user():
        f.name = "Ann"

    @factory(dict)
    def post():
        f.author = association(user, name="Bea")

    assert build(post) == {"author": User("Bea")}


def test_build_with_a_handle_in_a_body_names_the_factory_not_the_handle():
    @factory(dict)
    def tag():
        f.a = 1

    with pytest.raises(
        FactoryError, match=re.escape("Factory 'draft': build('tag') ran while")
    ):

        @factory(dict)
        def draft():
            f.tag = build(tag)
