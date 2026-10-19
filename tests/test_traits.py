import re

import pytest
from support.models import User

from factory_bot import FactoryError, build, factory, sequence


@pytest.fixture
def user_factory():
    @factory(User)
    def user(f):
        f.first_name = "John"
        f.email = lambda first_name: f"{first_name}@example.com".lower()
        f.admin = False

        @f.trait
        def admin(f):
            f.admin = True
            f.first_name = "Root"

        @f.trait
        def anonymous(f):
            f.first_name = "Anon"
            f.email = None


def test_a_trait_overrides_the_factory_and_feeds_dependencies(user_factory):
    assert build("user", "admin") == User(
        first_name="Root", email="root@example.com", admin=True
    )


def test_traits_apply_in_order_and_later_wins(user_factory):
    assert build("user", "admin", "anonymous").first_name == "Anon"
    assert build("user", "anonymous", "admin").first_name == "Root"


def test_overrides_win_over_traits(user_factory):
    assert build("user", "admin", admin=False, first_name="Jane").admin is False


def test_a_trait_body_runs_once_so_its_sequence_keeps_counting():
    @factory(dict)
    def user(f):
        f.username = sequence(lambda n: f"user{n}")

        @f.trait
        def admin(f):
            f.username = sequence(lambda n: f"admin{n}")

    assert [build("user", "admin")["username"] for _ in range(3)] == [
        "admin1",
        "admin2",
        "admin3",
    ]


def test_an_unknown_trait_suggests_the_closest_and_lists_them_all(user_factory):
    message = "Factory 'user' has no trait 'admn'. Did you mean 'admin'? Traits: admin, anonymous"
    with pytest.raises(FactoryError, match=rf"^{re.escape(message)}$"):
        build("user", "admn")


def test_a_factory_without_traits_says_so():
    @factory(User)
    def user(f):
        pass

    with pytest.raises(
        FactoryError, match=r"^Factory 'user' has no trait 'admin'\. Traits: \(none\)$"
    ):
        build("user", "admin")
