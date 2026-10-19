import itertools
import re

import pytest

from factory_bot import FactoryError, build, factory


def test_callables_are_called_on_every_build():
    counter = itertools.count(1)

    @factory(dict)
    def ticket(f):
        f.number = lambda: next(counter)

    assert [build("ticket")["number"] for _ in range(3)] == [1, 2, 3]


def test_required_parameters_are_injected_by_name():
    @factory(dict)
    def user(f):
        f.email = lambda first_name, last_name: f"{first_name}.{last_name}@example.com"
        f.first_name = "Ann"
        f.last_name = "Lee"

    assert build("user")["email"] == "Ann.Lee@example.com"


def test_dependencies_see_overrides():
    @factory(dict)
    def user(f):
        f.first_name = "Ann"
        f.email = lambda first_name: f"{first_name}@example.com"

    assert build("user", first_name="Bea")["email"] == "Bea@example.com"


def test_parameters_with_defaults_are_left_alone():
    @factory(dict)
    def post(f):
        f.domain = "wrong.example"
        f.body = lambda nb_sentences=3, domain=None: (nb_sentences, domain)

    assert build("post")["body"] == (3, None)


def test_a_callable_without_an_inspectable_signature_has_no_dependencies():
    @factory(dict)
    def user(f):
        f.meta = dict

    first, second = build("user"), build("user")
    assert first["meta"] == {}
    assert first["meta"] is not second["meta"]


def test_overrides_are_never_called():
    @factory(dict)
    def job(f):
        f.run = lambda: "default"

    def callback():
        pass

    assert build("job", run=callback)["run"] is callback


def test_an_undefined_dependency_names_the_attribute_and_suggests_a_fix():
    @factory(dict)
    def broken(f):
        f.first_name = "x"
        f.email = lambda frist_name: frist_name

    message = (
        "Factory 'broken': 'email' depends on 'frist_name', which is not defined."
        " Did you mean 'first_name'?"
    )
    with pytest.raises(
        FactoryError, match=rf"^{re.escape(message)} \(test_lazy\.py:\d+\)$"
    ):
        build("broken")


def test_a_circular_dependency_shows_the_cycle():
    @factory(dict)
    def cyclic(f):
        f.a = lambda b: b
        f.b = lambda c: c
        f.c = lambda a: a

    with pytest.raises(
        FactoryError, match=r"^Factory 'cyclic': circular dependency: a -> b -> c -> a$"
    ):
        build("cyclic")


def test_reading_an_attribute_in_a_definition_points_to_injection():
    with pytest.raises(
        FactoryError,
        match=r"Factory 'user': can't read f\.first_name.*lambda first_name:",
    ):

        @factory(dict)
        def user(f):
            f.first_name = "Ann"
            f.email = f.first_name + "@example.com"
