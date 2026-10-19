import pytest
from support.models import User

from factory_bot import (
    build_list,
    create_list,
    f,
    factory,
    sequence,
    trait,
)


@pytest.fixture
def user_factory():
    @factory(User)
    def user():
        f.username = sequence(lambda n: f"user{n}")

        @trait
        def admin():
            f.admin = True


def test_build_list_builds_n_separate_objects_with_the_same_traits_and_overrides(
    user_factory,
):
    users = build_list("user", 3, "admin", first_name="Ann")
    assert [u.username for u in users] == ["user1", "user2", "user3"]
    assert all(u.admin and u.first_name == "Ann" and not u.saved for u in users)


def test_create_list_saves_each_object(user_factory):
    assert all(u.saved for u in create_list("user", 2))
