import re

import pytest
from support.models import User

from factory_bot import (
    FactoryError,
    attributes_for,
    build,
    f,
    factory,
    sequence,
    transient,
)


@pytest.fixture
def user_factory():
    @factory(User)
    def user():
        f.shout = transient(False)
        f.suffix = transient(lambda: "!")
        f.first_name = lambda shout, suffix: ("ANN" if shout else "Ann") + suffix


def test_a_transient_feeds_other_attributes_but_not_the_model(user_factory):
    assert build("user").first_name == "Ann!"


def test_a_transient_can_be_overridden(user_factory):
    assert build("user", shout=True, suffix="?").first_name == "ANN?"


def test_attributes_for_leaves_transients_out(user_factory):
    assert attributes_for("user", shout=True) == {"first_name": "ANN!"}


def test_a_transient_wraps_any_value_including_markers():
    @factory(dict)
    def user():
        f.n = transient(sequence(lambda n: n))
        f.label = lambda n: f"#{n}"

    assert [build("user") for _ in range(2)] == [{"label": "#1"}, {"label": "#2"}]


def test_an_undefined_dependency_of_a_transient_still_points_at_its_line():
    @factory(dict)
    def user():
        f.name = "Ann"
        f.greeting = transient(lambda nmae: nmae)
        f.card = lambda greeting: greeting

    with pytest.raises(
        FactoryError,
        match=r"'greeting' depends on 'nmae'.* \(test_transient\.py:\d+\)$",
    ):
        build("user")


def test_an_error_raised_by_a_transient_points_at_its_line():
    @factory(dict)
    def user():
        f.greeting = transient(lambda: 1 / 0)
        f.card = lambda greeting: greeting

    with pytest.raises(ZeroDivisionError) as excinfo:
        build("user")
    assert len(excinfo.value.__notes__) == 1
    assert re.fullmatch(
        r"while building factory 'user', attribute 'greeting' \(test_transient\.py:\d+\)",
        excinfo.value.__notes__[0],
    )
