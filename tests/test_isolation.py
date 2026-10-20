"""A body writes a recipe: containers written in a body are copied per build. Anything passed
at build time is used exactly as given. A new place a value can come from is one more row."""

import pytest

from factory_bot import association, build, build_list, f, factory, trait, transient


def settings():
    return {"roles": [], "pair": ([],), "flags": {frozenset()}}


def from_factory():
    @factory(dict)
    def user():
        f.settings = settings()

    return build("user")["settings"], build("user")["settings"]


def from_trait():
    @factory(dict)
    def user():
        @trait
        def admin():
            f.settings = settings()

    return build("user", "admin")["settings"], build("user", "admin")["settings"]


def from_child():
    @factory(dict)
    def user():
        pass

    @factory(parent=user)
    def guest():
        f.settings = settings()

    return build("guest")["settings"], build("guest")["settings"]


def from_transient():
    @factory(dict)
    def user():
        f.defaults = transient(settings())
        f.settings = lambda defaults: defaults

    return build("user")["settings"], build("user")["settings"]


def from_association_override():
    @factory(dict)
    def user():
        pass

    @factory(dict)
    def post():
        f.author = association("user", settings=settings())

    return build("post")["author"]["settings"], build("post")["author"]["settings"]


WRITTEN_IN_A_BODY = [
    from_factory,
    from_trait,
    from_child,
    from_transient,
    from_association_override,
]


@pytest.mark.parametrize("source", WRITTEN_IN_A_BODY, ids=lambda fn: fn.__name__)
def test_builds_share_no_container_written_in_a_body(source):
    first, second = source()
    first["roles"].append("admin")
    first["pair"][0].append("x")
    first["flags"].add("y")
    assert second == settings()


def from_override(value):
    @factory(dict)
    def user():
        f.settings = None

    return build("user", settings=value)["settings"]


def from_a_list_helper(value):
    @factory(dict)
    def user():
        pass

    return build_list("user", 2, settings=value)[1]["settings"]


def from_a_transient_override(value):
    @factory(dict)
    def user():
        f.defaults = transient(None)
        f.settings = lambda defaults: defaults

    return build("user", defaults=transient(value))["settings"]


def from_an_association_passed(value):
    @factory(dict)
    def user():
        pass

    @factory(dict)
    def post():
        f.author = association("user")

    return build("post", author=association("user", settings=value))["author"][
        "settings"
    ]


def from_an_association_made_during_a_build(value):
    @factory(dict)
    def user():
        pass

    @factory(dict)
    def post():
        f.author = lambda: association("user", settings=value)

    return build("post")["author"]["settings"]


PASSED_AT_BUILD_TIME = [
    from_override,
    from_a_list_helper,
    from_a_transient_override,
    from_an_association_passed,
    from_an_association_made_during_a_build,
]


@pytest.mark.parametrize("source", PASSED_AT_BUILD_TIME, ids=lambda fn: fn.__name__)
def test_a_value_passed_at_build_time_is_used_exactly_as_given(source):
    value = settings()
    assert source(value) is value


def test_an_object_made_during_a_build_is_passed_on_as_is():
    @factory(dict)
    def account():
        f.plan = "free"

    @factory(dict)
    def task():
        f.account = association("account")

    @factory(dict)
    def profile():
        f.account = association("account")
        f.task = lambda account: association("task", account=account)

    p = build("profile")
    assert p["task"]["account"] is p["account"]
