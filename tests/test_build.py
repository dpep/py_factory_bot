import re

import pytest
from support.models import User

from factory_bot import (
    FactoryError,
    association,
    build,
    f,
    factory,
    transient,
)


def test_builds_the_model_from_static_attributes():
    @factory(User)
    def user():
        f.first_name = "John"
        f.last_name = "Doe"

    assert build("user") == User(first_name="John", last_name="Doe")


def test_any_callable_taking_kwargs_is_a_model():
    @factory(dict)
    def point():
        f.x = 1
        f.y = 2

    assert build("point") == {"x": 1, "y": 2}


def test_a_function_of_one_parameter_is_a_model_unless_the_parameter_is_f():
    def make_point(x):
        return ("point", x)

    @factory(make_point)
    def point():
        f.x = 1

    assert build("point") == ("point", 1)


def test_a_plain_function_is_a_model_too():
    def make_point(**kwargs):
        return kwargs

    @factory(make_point)
    def point():
        f.x = 1

    assert build("point") == {"x": 1}


def test_overrides_win_and_may_add_attributes():
    @factory(dict)
    def point():
        f.x = 1

    assert build("point", x=5, z=3) == {"x": 5, "z": 3}


def test_an_attribute_called_name_can_be_overridden():
    @factory(dict)
    def person():
        f.name = "Ann"

    assert build("person", name="Bea") == {"name": "Bea"}


def test_other_objects_are_shared_so_use_a_lambda_for_a_fresh_one():
    class Client:
        pass

    client = Client()

    @factory(dict)
    def user():
        f.client = client
        f.fresh = lambda: Client()

    first, second = build("user"), build("user")
    assert first["client"] is second["client"] is client
    assert first["fresh"] is not second["fresh"]


def test_unknown_factory_suggests_the_closest_name():
    @factory(User)
    def user():
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
        def user():
            pass


def test_model_must_be_callable():
    with pytest.raises(
        FactoryError, match=r"Factory 'user': model 'User' is not callable"
    ):

        @factory("User")
        def user():
            pass


def test_duplicate_factory_names_are_rejected():
    @factory(User)
    def user():
        pass

    with pytest.raises(
        FactoryError,
        match=rf"^Factory 'user' is already defined \({re.escape(__file__)}:\d+\)\."
        r" To redefine it, e\.g\. in a REPL or after a reload, call clear_factories\(\) first\.$",
    ):

        @factory(User)
        def user():
            pass


def test_a_marker_inside_a_container_is_an_error():
    @factory(dict)
    def author():
        f.name = "Ann"

    @factory(dict)
    def post():
        f.authors = [association("author")]

    rule = (
        r", so it was never evaluated: a sequence\(\), association\(\) or transient\(\)"
        r" works only as an attribute's whole value"
    )
    with pytest.raises(
        FactoryError,
        match=rf"^Factory 'post': <association 'author'> is inside a list{rule}",
    ) as excinfo:
        build("post")
    assert excinfo.value.__notes__ == [
        "while building factory 'post', attribute 'authors'"
    ]

    with pytest.raises(
        FactoryError, match=rf"^Factory 'author': <transient 1> is inside a dict{rule}"
    ):
        build("author", name={"first": transient(1)})
