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
        f.username = sequence(lambda n: f"user{n}")

        @trait
        def shouty():
            f.first_name = "JOHN"

        @factory
        def guest():
            f.first_name = "Guest"

            @trait
            def anonymous():
                f.email = None

            @factory
            def ghost():
                f.last_name = "Boo"

        @factory(Admin)
        def admin():
            f.admin = True

        f.email = "late@example.com"  # declared after the children, still inherited


def test_a_child_inherits_the_model_and_attributes_declared_before_and_after_it(
    user_factory,
):
    assert build("guest") == User(
        first_name="Guest", email="late@example.com", username="user1"
    )


def test_a_child_does_not_change_its_parent(user_factory):
    assert build("user").first_name == "John"


def test_a_child_inherits_traits_and_adds_its_own(user_factory):
    assert build("guest", "shouty", "anonymous") == User(
        first_name="JOHN", username="user1"
    )


def test_a_child_shares_its_parents_sequences(user_factory):
    assert [build("user").username, build("guest").username] == ["user1", "user2"]


def test_children_nest(user_factory):
    assert build("ghost", "anonymous") == User(
        first_name="Guest", last_name="Boo", username="user1"
    )


def test_a_nested_factory_with_a_model_switches_model(user_factory):
    admin = build("admin")
    assert type(admin) is Admin
    assert admin.admin and admin.email == "late@example.com"


def test_an_unknown_trait_lists_inherited_traits_too(user_factory):
    message = "Factory 'ghost' has no trait 'x'. Traits: shouty, anonymous"
    with pytest.raises(FactoryError, match=f"^{re.escape(message)}$"):
        build("ghost", "x")


def test_a_factory_inside_a_trait_is_rejected():
    message = r"^Factory 'user': @factory def guest must be directly inside the factory, not inside trait 'admin'$"
    with pytest.raises(FactoryError, match=message):

        @factory(User)
        def user():
            @trait
            def admin():
                @factory
                def guest():
                    pass


def test_a_parent_body_that_raises_registers_its_children_neither():
    with pytest.raises(RuntimeError):

        @factory(User)
        def user():
            @factory
            def guest():
                pass

            raise RuntimeError

    with pytest.raises(FactoryError, match="No factory named 'guest'"):
        build("guest")


def _nested():
    @factory(User)
    def user():
        f.first_name = "John"
        f.username = sequence(lambda n: f"user{n}")

        @trait
        def shouty():
            f.first_name = "JOHN"

        @after_build
        def mark(user):
            user.last_name = "Built"

        @factory
        def guest():
            f.email = "guest@example.com"

        @factory(Admin)
        def admin():
            f.admin = True


def _top_level():
    @factory(User)
    def user():
        f.first_name = "John"
        f.username = sequence(lambda n: f"user{n}")

        @trait
        def shouty():
            f.first_name = "JOHN"

        @after_build
        def mark(user):
            user.last_name = "Built"

    @factory(parent=user)
    def guest():
        f.email = "guest@example.com"

    @factory(Admin, parent="user")
    def admin():
        f.admin = True


@pytest.mark.parametrize("define", [_nested, _top_level], ids=["nested", "parent="])
def test_a_child_is_the_same_whichever_spelling_defines_it(define):
    define()
    assert [build("user").username, build("guest", "shouty")] == [
        "user1",
        User(
            first_name="JOHN",
            last_name="Built",
            email="guest@example.com",
            username="user2",
        ),
    ]
    admin = build("admin")
    assert type(admin) is Admin and admin.admin and admin.first_name == "John"


def test_a_child_of_an_unknown_parent_is_an_error():
    with pytest.raises(FactoryError, match=r"^No factory named 'usr'"):

        @factory(parent="usr")
        def guest():
            pass


def test_parent_is_not_given_inside_a_body():
    message = (
        r"^Factory 'user': @factory\(parent=\.\.\.\) def guest is inside factory 'user',"
        r" which is already its parent: drop parent=$"
    )
    with pytest.raises(FactoryError, match=message):

        @factory(User)
        def user():
            @factory(parent="user")
            def guest():
                pass


def test_a_top_level_child_is_registered_on_its_own():
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
