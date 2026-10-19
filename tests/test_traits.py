import re

import pytest
from support.models import User

from factory_bot import FactoryError, after_build, build, f, factory, sequence, trait


@pytest.fixture
def user_factory():
    @factory(User)
    def user():
        f.first_name = "John"
        f.email = lambda first_name: f"{first_name}@example.com".lower()
        f.admin = False

        @trait
        def admin():
            f.admin = True
            f.first_name = "Root"

        @trait
        def anonymous():
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
    def user():
        f.username = sequence(lambda n: f"user{n}")

        @trait
        def admin():
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
    def user():
        pass

    with pytest.raises(
        FactoryError, match=r"^Factory 'user' has no trait 'admin'\. Traits: \(none\)$"
    ):
        build("user", "admin")


def test_a_trait_passed_twice_applies_once():
    calls = []

    @factory(dict)
    def user():
        @trait
        def admin():
            f.admin = True

            @after_build
            def record(user):
                calls.append(user)

    build("user", "admin", "admin")
    assert len(calls) == 1
