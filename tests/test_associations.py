import pytest
from support.models import Post, User

from factory_bot import (
    FactoryError,
    after_build,
    association,
    attributes_for,
    build,
    create,
    f,
    factory,
    trait,
    transient,
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


def test_containers_in_association_overrides_are_not_shared_between_builds():
    @factory(User)
    def user():
        pass

    @factory(Post)
    def post():
        f.author = association("user", tags=[])

    first, second = build("post"), build("post")
    first.author.tags.append("x")
    assert second.author.tags == []


def test_an_association_passed_as_an_override_follows_the_strategy(post_factory):
    built = build("post", author=association("user", "admin"))
    assert built.author == User(first_name="Ann", admin=True)
    assert not built.author.saved
    assert create("post", author=association("user")).author.saved
    assert attributes_for("post", author=association("user")) == {"title": "Hello"}


@pytest.fixture
def has_many_factory():
    @factory(User)
    def tag():
        f.first_name = "red"

    @factory(User)
    def user():
        f.n_tags = transient(1)
        f.tags = lambda n_tags: [association("tag") for _ in range(n_tags)]

    @factory(Post)
    def post():
        f.author = association("user", n_tags=2)


def test_association_called_while_building_builds_with_the_current_strategy(
    has_many_factory,
):
    assert [t.saved for t in build("user").tags] == [False]
    assert [t.saved for t in create("user").tags] == [True]
    assert [t.saved for t in attributes_for("user")["tags"]] == [False]


def test_the_strategy_follows_through_nested_builds(has_many_factory):
    assert [t.saved for t in build("post").author.tags] == [False, False]
    assert [t.saved for t in create("post").author.tags] == [True, True]


def test_association_called_in_a_callback_builds_with_the_current_strategy():
    @factory(User)
    def user():
        pass

    @factory(Post)
    def post():
        @after_build
        def add_author(post):
            post.author = association("user")

    assert not build("post").author.saved
    assert create("post").author.saved


def test_an_unknown_association_called_while_building_names_the_attribute():
    @factory(User)
    def user():
        f.tags = lambda: [association("tga")]

    @factory(User)
    def tag():
        pass

    message = r"^Factory 'user': 'tags' is an association to 'tga', which is not a factory\. Did you mean 'tag'\?$"
    with pytest.raises(FactoryError, match=message):
        build("user")


def test_an_association_cycle_names_the_chain():
    @factory(dict)
    def post():
        f.author = association("user")

    @factory(dict)
    def user():
        f.post = association("post")

    message = r"^Factory 'post': circular association: post\.author -> user\.post -> post\.author\n"
    with pytest.raises(FactoryError, match=message):
        build("post")


def test_an_association_cycle_through_a_lazy_attribute_names_the_chain():
    @factory(dict)
    def user():
        f.posts = lambda: [association("post")]

    @factory(dict)
    def post():
        f.author = association("user")

    message = r"^Factory 'user': circular association: user\.posts -> post\.author -> user\.posts\n"
    with pytest.raises(FactoryError, match=message):
        build("user")


def test_an_association_that_overrides_its_way_out_is_not_a_cycle():
    @factory(dict)
    def node():
        f.depth = transient(2)
        f.parent = lambda depth: association("node", depth=depth - 1) if depth else None

    assert build("node") == {"parent": {"parent": {"parent": None}}}
