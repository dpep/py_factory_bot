import pytest
from support.models import User

from factory_bot import (
    FactoryError,
    after_build,
    after_create,
    attributes_for,
    build,
    create,
    f,
    factory,
    trait,
    transient,
)


def test_after_build_gets_the_instance_and_injected_attributes_including_transients():
    @factory(User)
    def user():
        f.first_name = "Ann"
        f.shout = transient(False)

        @after_build
        def maybe_shout(user, shout, first_name):
            if shout:
                user.first_name = first_name.upper()

    assert build("user", shout=True).first_name == "ANN"
    assert build("user").first_name == "Ann"


def test_after_create_runs_after_saving_and_only_on_create():
    seen = []

    @factory(User)
    def user():
        @after_create
        def record(user):
            seen.append(user.saved)

    build("user")
    assert seen == []
    create("user")
    assert seen == [True]


def test_callbacks_run_in_definition_order_parent_first_then_traits():
    calls = []

    @factory(dict)
    def user():
        @after_build
        def first(obj):
            calls.append("user 1")

        @after_build
        def second(obj):
            calls.append("user 2")

        @trait
        def admin():
            @after_build
            def from_trait(obj):
                calls.append("admin trait")

        @factory
        def guest():
            @after_build
            def from_child(obj):
                calls.append("guest")

    build("guest", "admin")
    assert calls == ["user 1", "user 2", "guest", "admin trait"]


def test_attributes_for_runs_no_callbacks():
    @factory(dict)
    def user():
        f.name = "Ann"

        @after_build
        def explode(obj):
            raise AssertionError("should not run")

    assert attributes_for("user") == {"name": "Ann"}


def test_a_callback_with_an_undefined_dependency_names_it():
    @factory(dict)
    def user():
        f.name = "Ann"

        @after_build
        def greet(obj, nmae):
            pass

    with pytest.raises(
        FactoryError,
        match=r"^Factory 'user': 'greet' depends on 'nmae', which is not defined\. Did you mean 'name'\?",
    ):
        build("user")


def test_a_callback_outside_a_body_says_where_it_works():
    with pytest.raises(
        FactoryError,
        match=r"^@after_build def greet only works inside a @factory body$",
    ):

        @after_build
        def greet(obj):
            pass
