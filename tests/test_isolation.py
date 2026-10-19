"""No build shares a list, dict, set or tuple with another, whichever source the value came from.
A new place a value can come from is one more row."""

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
        @factory
        def guest():
            f.settings = settings()

    return build("guest")["settings"], build("guest")["settings"]


def from_transient():
    @factory(dict)
    def user():
        f.defaults = transient(settings())
        f.settings = lambda defaults: defaults

    return build("user")["settings"], build("user")["settings"]


def from_override():
    @factory(dict)
    def user():
        pass

    value = settings()
    return build("user", settings=value)["settings"], build("user", settings=value)[
        "settings"
    ]


def from_association_override():
    @factory(dict)
    def user():
        pass

    @factory(dict)
    def post():
        f.author = association("user", settings=settings())

    return build("post")["author"]["settings"], build("post")["author"]["settings"]


def from_a_list_helper():
    @factory(dict)
    def user():
        pass

    first, second = build_list("user", 2, settings=settings())
    return first["settings"], second["settings"]


SOURCES = [
    from_factory,
    from_trait,
    from_child,
    from_transient,
    from_override,
    from_association_override,
    from_a_list_helper,
]


@pytest.mark.parametrize("source", SOURCES, ids=lambda fn: fn.__name__)
def test_builds_share_no_container(source):
    first, second = source()
    first["roles"].append("admin")
    first["pair"][0].append("x")
    first["flags"].add("y")
    assert second == settings()
