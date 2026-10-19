import functools

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


def no_parameters():
    pass


def keyword_only(*, user):
    pass


@pytest.mark.parametrize(
    "callback, shown",
    [
        (no_parameters, r"no_parameters\(\)"),
        (keyword_only, r"keyword_only\(\*, user\)"),
    ],
)
def test_a_callback_that_cannot_take_the_instance_is_rejected(callback, shown):
    message = (
        rf"^Factory 'user': @after_build def {shown} must take the instance first,"
        rf" then other attributes by name: def {callback.__name__}\(user, \.\.\.\)$"
    )
    with pytest.raises(FactoryError, match=message):

        @factory(User)
        def user():
            after_build(callback)


def test_a_partial_that_cannot_take_the_instance_is_rejected_by_its_repr():
    message = (
        r"^Factory 'user': @after_build functools\.partial\(<function no_parameters at \w+>\)"
        r" must take the instance first, then other attributes by name: def callback\(user, \.\.\.\)$"
    )
    with pytest.raises(FactoryError, match=message):

        @factory(User)
        def user():
            after_build(functools.partial(no_parameters))


def test_a_partial_is_accepted_as_a_callback():
    @factory(User)
    def user():
        after_build(functools.partial(lambda calls, user: None, []))


def test_a_partial_callback_runs():
    def record(calls, user, first_name):
        calls.append(first_name)

    calls = []

    @factory(User)
    def user():
        f.first_name = "Ann"
        after_build(functools.partial(record, calls))

    build("user")
    assert calls == ["Ann"]
