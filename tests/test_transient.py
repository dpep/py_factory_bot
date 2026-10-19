import pytest
from support.models import User

from factory_bot import (
    FactoryError,
    attributes_for,
    build,
    f,
    factory,
    sequence,
    trait,
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


def test_a_transient_stays_transient_when_a_trait_or_child_gives_it_a_plain_value():
    @factory(dict)
    def order():
        f.n = transient(0)
        f.label = lambda n: f"{n} lines"

        @trait
        def big():
            f.n = 5

        @factory
        def small_order():
            f.n = 1

    assert build("order", "big") == {"label": "5 lines"}
    assert build("small_order") == {"label": "1 lines"}
    assert attributes_for("order", "big", n=7) == {"label": "7 lines"}
