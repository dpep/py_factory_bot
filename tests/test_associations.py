import pytest
from support.models import Post, User

from factory_bot import (
    FactoryError,
    association,
    attributes_for,
    build,
    create,
    f,
    factory,
    trait,
)


@pytest.fixture
def post_factory():
    @factory(User)
    def user():
        f.first_name = "Ann"

        @trait
        def admin():
            f.admin = True

    @factory(Post)
    def post():
        f.title = "Hello"
        f.author = association("user", "admin", last_name="Lee")


def test_an_association_builds_its_factory_with_traits_and_overrides(post_factory):
    post = build("post")
    assert post.author == User(first_name="Ann", last_name="Lee", admin=True)
    assert not post.author.saved


def test_create_creates_the_association_too(post_factory):
    post = create("post")
    assert post.saved and post.author.saved


def test_an_override_replaces_the_association(post_factory):
    author = User(first_name="Bea")
    assert build("post", author=author).author is author


def test_attributes_for_leaves_associations_out(post_factory):
    assert attributes_for("post") == {"title": "Hello"}


def test_an_association_to_an_unknown_factory_names_the_attribute():
    @factory(Post)
    def post():
        f.author = association("usr")

    @factory(User)
    def user():
        pass

    message = r"^Factory 'post': 'author' is an association to 'usr', which is not a factory\. Did you mean 'user'\?$"
    with pytest.raises(FactoryError, match=message):
        build("post")


def test_attributes_for_still_builds_an_association_another_attribute_needs():
    @factory(User)
    def user():
        f.first_name = "Ann"

    @factory(dict)
    def post():
        f.author = association("user")
        f.byline = lambda author: f"by {author.first_name}"

    assert attributes_for("post") == {"byline": "by Ann"}
