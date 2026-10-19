import pytest
from support.models import User

from factory_bot import FactoryError, build, factory


def test_builds_the_model_from_static_attributes():
    @factory(User)
    def user(f):
        f.first_name = "John"
        f.last_name = "Doe"

    assert build("user") == User(first_name="John", last_name="Doe")


def test_any_callable_taking_kwargs_is_a_model():
    @factory(dict)
    def point(f):
        f.x = 1
        f.y = 2

    assert build("point") == {"x": 1, "y": 2}


def test_a_plain_function_is_a_model_too():
    def make_point(**kwargs):
        return kwargs

    @factory(make_point)
    def point(f):
        f.x = 1

    assert build("point") == {"x": 1}


def test_overrides_win_and_may_add_attributes():
    @factory(dict)
    def point(f):
        f.x = 1

    assert build("point", x=5, z=3) == {"x": 5, "z": 3}


def test_an_attribute_called_name_can_be_overridden():
    @factory(dict)
    def person(f):
        f.name = "Ann"

    assert build("person", name="Bea") == {"name": "Bea"}


def test_mutable_values_are_not_shared_between_builds():
    @factory(User)
    def user(f):
        f.tags = []

    first, second = build("user"), build("user")
    first.tags.append("x")
    assert second.tags == []


def test_unknown_factory_suggests_the_closest_name():
    @factory(User)
    def user(f):
        pass

    with pytest.raises(
        FactoryError, match=r"^No factory named 'usr'\. Did you mean 'user'\?$"
    ):
        build("usr")


def test_bare_decorator_names_the_fix():
    with pytest.raises(
        FactoryError, match=r"@factory needs a model.*@factory\(User\).*def user"
    ):

        @factory
        def user(f):
            pass


def test_model_must_be_callable():
    with pytest.raises(
        FactoryError, match=r"Factory 'user': model 'User' is not callable"
    ):

        @factory("User")
        def user(f):
            pass


def test_duplicate_factory_names_are_rejected():
    @factory(User)
    def user(f):
        pass

    with pytest.raises(
        FactoryError,
        match=r"^Factory 'user' is already defined \(test_build\.py:\d+\)$",
    ):

        @factory(User)
        def user(f):
            pass
