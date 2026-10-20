import re

import pytest
from support.models import User

from factory_bot import FactoryError, after_build, build, f, factory, sequence, trait


class Admin(User):
    pass


@pytest.fixture
def user_factory():
    @factory(User)
    def user():
        f.first_name = "John"
        f.email = "john@example.com"
        f.username = sequence(lambda n: f"user{n}")

        @trait
        def shouty():
            f.first_name = "JOHN"

        @after_build
        def mark(user):
            user.last_name = "Built"

    @factory(parent=user)
    def guest():
        f.first_name = "Guest"

        @trait
        def anonymous():
            f.email = None

    @factory(parent=guest)
    def ghost():
        f.last_name = "Boo"

    @factory(Admin, parent="user")
    def admin():
        f.admin = True


def test_a_child_inherits_the_model_attributes_and_callbacks(user_factory):
    assert build("guest") == User(
        first_name="Guest",
        last_name="Built",
        email="john@example.com",
        username="user1",
    )


def test_a_child_does_not_change_its_parent(user_factory):
    assert build("user").first_name == "John"


def test_a_child_inherits_traits_and_adds_its_own(user_factory):
    assert build("guest", "shouty", "anonymous") == User(
        first_name="JOHN", last_name="Built", username="user1"
    )


def test_a_child_shares_its_parents_sequences(user_factory):
    assert [build("user").username, build("guest").username] == ["user1", "user2"]


def test_children_nest(user_factory):
    # The parent's callback runs after the build, over the grandchild's last_name.
    assert build("ghost", "anonymous") == User(
        first_name="Guest", last_name="Built", username="user1"
    )


def test_a_child_with_a_model_switches_model(user_factory):
    admin = build("admin")
    assert type(admin) is Admin
    assert admin.admin and admin.first_name == "John"


def test_an_unknown_trait_lists_inherited_traits_too(user_factory):
    message = "Factory 'ghost' has no trait 'x'. Traits: shouty, anonymous"
    with pytest.raises(FactoryError, match=f"^{re.escape(message)}$"):
        build("ghost", "x")


def test_a_child_of_an_unknown_parent_is_an_error():
    with pytest.raises(FactoryError, match=r"^No factory named 'usr'"):

        @factory(parent="usr")
        def guest():
            pass


def _in_body():
    @factory(User)
    def user():
        @factory
        def guest():
            pass


def _in_trait():
    @factory(User)
    def user():
        @trait
        def admin():
            @factory(Admin, parent="user")
            def guest():
                pass


@pytest.mark.parametrize("define", [_in_body, _in_trait], ids=["body", "trait"])
def test_a_factory_inside_a_body_shows_the_parent_spelling(define):
    message = (
        "Factory 'user': @factory def guest is inside factory 'user'; define a child"
        " after its parent, at the top level: @factory(parent=user) def guest"
    )
    with pytest.raises(FactoryError, match=f"^{re.escape(message)}$"):
        define()
    with pytest.raises(FactoryError, match="No factory named 'guest'"):
        build("guest")


def test_a_child_is_registered_on_its_own():
    @factory(User)
    def user():
        pass

    @factory(parent=user)
    def guest():
        pass

    with pytest.raises(FactoryError, match="Factory 'guest' is already defined"):

        @factory(parent=user)
        def guest():
            pass
