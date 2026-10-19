import enum
import functools
import inspect
import itertools
import re
from dataclasses import dataclass

import pytest

from factory_bot import (
    FactoryError,
    attributes_for,
    build,
    f,
    factory,
    sequence,
    transient,
)


def test_callables_are_called_on_every_build():
    counter = itertools.count(1)

    @factory(dict)
    def ticket():
        f.number = lambda: next(counter)

    assert [build("ticket")["number"] for _ in range(3)] == [1, 2, 3]


def test_required_parameters_are_injected_by_name():
    @factory(dict)
    def user():
        f.email = lambda first_name, last_name: f"{first_name}.{last_name}@example.com"
        f.first_name = "Ann"
        f.last_name = "Lee"

    assert build("user")["email"] == "Ann.Lee@example.com"


def test_dependencies_see_overrides():
    @factory(dict)
    def user():
        f.first_name = "Ann"
        f.email = lambda first_name: f"{first_name}@example.com"

    assert build("user", first_name="Bea")["email"] == "Bea@example.com"


def test_parameters_with_defaults_are_left_alone():
    @factory(dict)
    def post():
        f.domain = "wrong.example"
        f.body = lambda nb_sentences=3, domain=None: (nb_sentences, domain)

    assert build("post")["body"] == (3, None)


def test_a_callable_without_an_inspectable_signature_has_no_dependencies():
    @factory(dict)
    def user():
        f.top = functools.partial(max, [1, 2])

    assert build("user") == {"top": 2}


class Status(enum.Enum):
    ACTIVE = "active"


@dataclass
class Address:
    city: str


class Meta(type):
    def __call__(cls, *args, **kwargs):
        raise AssertionError("a class is never called")


class Handler(metaclass=Meta):
    pass


def test_a_class_is_stored_not_called():
    @factory(dict)
    def account():
        f.status_type = Status
        f.address_type = Address
        f.handler = Handler
        f.meta = dict

    assert build("account") == {
        "status_type": Status,
        "address_type": Address,
        "handler": Handler,
        "meta": dict,
    }


def test_overrides_are_never_called():
    @factory(dict)
    def job():
        f.run = lambda: "default"

    def callback():
        pass

    assert build("job", run=callback)["run"] is callback


def test_an_undefined_dependency_names_the_attribute_and_suggests_a_fix():
    @factory(dict)
    def broken():
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
    def cyclic():
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
        def user():
            f.first_name = "Ann"
            f.email = f.first_name + "@example.com"


def test_positional_only_parameters_are_injected_by_name_too():
    @factory(dict)
    def user():
        f.first_name = "Ann"
        f.last_name = "Lee"
        f.email = lambda first_name, /, last_name: f"{first_name}.{last_name}"

    assert build("user")["email"] == "Ann.Lee"


def test_reading_f_at_build_time_names_the_factory_and_the_fix():
    @factory(dict)
    def user():
        f.first_name = "Ann"
        f.email = lambda: f.first_name

    with pytest.raises(FactoryError) as excinfo:
        build("user")
    assert str(excinfo.value) == (
        "Factory 'user': can't read f.first_name: f only declares attributes."
        " To use another attribute, take it as a parameter: lambda first_name: ..."
    )


@pytest.mark.parametrize(
    "returns",
    [lambda: sequence(lambda n: n), lambda: transient(1)],
    ids=["sequence", "transient"],
)
@pytest.mark.parametrize("strategy", [build, attributes_for])
def test_a_marker_returned_by_a_function_is_an_error(returns, strategy):
    @factory(dict)
    def user():
        f.name = returns

    with pytest.raises(FactoryError) as excinfo:
        strategy("user")
    assert re.fullmatch(
        r"Factory 'user': <\w+ .+> was returned from a function, so it was never evaluated:"
        r" a sequence\(\), association\(\) or transient\(\) works only as an attribute's"
        r" whole value, never returned from a function or inside a container\.",
        str(excinfo.value),
    )
    assert re.fullmatch(
        r"while building factory 'user', attribute 'name' \(test_lazy\.py:\d+\)",
        excinfo.value.__notes__[0],
    )


def test_a_callables_parameters_are_read_once_across_builds(monkeypatch):
    class Stamp:
        __slots__ = ()  # no weak reference, so it can't be cached

        def __call__(self):
            return 1

    email, stamp = lambda first_name: f"{first_name}@x.io", Stamp()
    read = []
    signature = inspect.signature
    monkeypatch.setattr(
        inspect, "signature", lambda fn: read.append(fn) or signature(fn)
    )

    @factory(dict)
    def user():
        f.first_name = "Ann"
        f.email = email
        f.stamp = stamp

    for _ in range(3):
        assert build("user") == {"first_name": "Ann", "email": "Ann@x.io", "stamp": 1}
    assert (read.count(email), read.count(stamp)) == (1, 3)
