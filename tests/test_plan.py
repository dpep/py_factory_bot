"""How layers combine, at the one place that decides it: lineage, then traits, then overrides
in, a plan out. No model is built; the end-to-end tests keep one case per user-visible rule."""

from dataclasses import dataclass

import pytest

from factory_bot import (
    after_build,
    after_create,
    association,
    f,
    factory,
    sequence,
    trait,
    transient,
)
from factory_bot._core import _Given, _is_lazy, _registry, _Sequence, _Transient


@dataclass
class Robot:
    name: str = ""


@pytest.fixture(autouse=True)
def factories():
    @factory(dict)
    def user():
        f.name = "Ann"
        f.email = lambda name: f"{name}@x.io"
        f.code = transient(0)
        f.n = sequence(lambda n: n)
        f.boss = association("user")

        @after_build
        def stamp(user):
            pass

        @trait
        def admin():
            f.role = "admin"

            @after_build
            def promote(user):
                pass

        @trait
        def coded():
            f.code = "c"

        @trait
        def loud():
            f.name = "ANN"

            @after_create
            def shout(user):
                pass

        @factory
        def guest():
            f.name = "Guest"
            f.code = "g"

            @trait
            def admin():
                f.role = "guest admin"

        @factory(Robot)
        def robot():
            pass

    @factory(dict)
    def plain():
        f.x = 1


def kind(value):
    if isinstance(value, _Given):
        return f"given {kind(value.value)}"
    if isinstance(value, _Transient):
        return f"transient {kind(value.value)}"
    if isinstance(value, _Sequence):
        return "sequence"
    if _is_lazy(value):
        return "lazy"
    return repr(value)


def project(plan):
    return {
        "definitions": {n: kind(v) for n, v in plan.definitions.items()},
        "transients": plan.transients,
        "declared": plan.declared,
        "associations": plan.associations,
        "model": plan.model,
        "replaced": plan.replaced,
        "callbacks": {k: [cb.__name__ for cb in v] for k, v in plan.callbacks.items()},
    }


USER = {
    "name": "'Ann'",
    "email": "lazy",
    "code": "transient 0",
    "n": "sequence",
    "boss": "<association 'user'>",
}

ROWS = {
    "the lineage alone": (
        "user",
        (),
        {},
        {
            "definitions": USER,
            "transients": {"code"},
            "declared": set(USER),
            "associations": {"boss"},
            "model": dict,
            "callbacks": {"after_build": ["stamp"], "after_create": []},
        },
    ),
    "an override wins in place, and a new name goes last": (
        "user",
        (),
        {"name": "Bea", "extra": 1},
        {
            "definitions": {**USER, "name": "given 'Bea'", "extra": "given 1"},
            "declared": set(USER),
        },
    ),
    "a callable override is a plain value, never called": (
        "user",
        (),
        {"email": print},
        {"definitions": {**USER, "email": "given lazy"}},
    ),
    "a marker override evaluates like a definition": (
        "user",
        (),
        {"name": sequence(lambda n: n), "boss": association("plain")},
        {
            "definitions": {
                **USER,
                "name": "sequence",
                "boss": "<association 'plain'>",
            }
        },
    ),
    "an association passed, as a marker or a value, is not left out": (
        "user",
        (),
        {"boss": association("plain"), "pal": association("plain")},
        {"associations": set()},
    ),
    "a transient override is transient": (
        "plain",
        (),
        {"seed": transient(3)},
        {
            "definitions": {"x": "1", "seed": "transient 3"},
            "transients": {"seed"},
            "declared": {"x"},
        },
    ),
    "transient stays transient under a trait's plain value": (
        "user",
        ("coded",),
        {},
        {"definitions": {**USER, "code": "'c'"}, "transients": {"code"}},
    ),
    "transient stays transient under a child's plain value": (
        "guest",
        (),
        {},
        {
            "definitions": {**USER, "name": "'Guest'", "code": "'g'"},
            "transients": {"code"},
        },
    ),
    "transient stays transient under an override": (
        "user",
        (),
        {"code": 7},
        {"definitions": {**USER, "code": "given 7"}, "transients": {"code"}},
    ),
    "traits apply in the order given, callbacks after the lineage's": (
        "user",
        ("loud", "admin"),
        {},
        {
            "definitions": {**USER, "name": "'ANN'", "role": "'admin'"},
            "declared": {*USER, "role"},
            "callbacks": {
                "after_build": ["stamp", "promote"],
                "after_create": ["shout"],
            },
        },
    ),
    "a trait passed twice applies once": (
        "user",
        ("admin", "admin"),
        {},
        {"callbacks": {"after_build": ["stamp", "promote"], "after_create": []}},
    ),
    "a child's trait shadows its parent's": (
        "guest",
        ("admin",),
        {},
        {
            "definitions": {
                **USER,
                "name": "'Guest'",
                "code": "'g'",
                "role": "'guest admin'",
            },
            "callbacks": {"after_build": ["stamp"], "after_create": []},
        },
    ),
    "an override <name>_id replaces association <name>": (
        "user",
        (),
        {"boss_id": 1, "name_id": 2},
        {"replaced": {"boss": "boss_id"}},
    ),
    "passing <name> too replaces nothing": (
        "user",
        (),
        {"boss_id": 1, "boss": None},
        {"replaced": {}},
    ),
    "a child inherits the nearest model": ("guest", (), {}, {"model": dict}),
    "a child's own model wins": ("robot", (), {}, {"model": Robot}),
}


@pytest.mark.parametrize(
    ("name", "traits", "overrides", "expected"), ROWS.values(), ids=ROWS
)
def test_resolve(name, traits, overrides, expected):
    plan = project(_registry[name].resolve(traits, overrides))
    assert {k: plan[k] for k in expected} == expected
    if "definitions" in expected:  # order matters too: it is evaluation and model order
        assert list(plan["definitions"]) == list(expected["definitions"])
