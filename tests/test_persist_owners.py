"""Which persist_with call decides, as the pytest plugin drives the owners: one row per sequence.

enter/leave bracket an owner's setup or call, end is its last finalizer, and `set x` is
persist_with(hook x) by whichever owner is innermost (the base owner when none is).
"""

import pytest

from factory_bot import _core, create, factory


class Thing:
    by = "save"

    def save(self):
        pass


def hook(name):
    def save(obj):
        obj.by = name

    return save


@pytest.fixture
def saved_by(monkeypatch):
    monkeypatch.setattr(_core, "_owners", [])
    monkeypatch.setattr(_core, "_hooks", {})

    @factory(Thing)
    def thing():
        pass

    return lambda: create(thing).by


def play(events):
    owners = {}
    for event in filter(None, events.split(", ")):
        action, name = event.split()
        if action == "set":
            _core._set_persist_hook(None if name == "None" else hook(name))
        else:
            owner = owners.setdefault(name, object())
            {
                "enter": _core._enter_owner,
                "leave": _core._leave_owner,
                "end": _core._end_owner,
            }[action](owner)


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        ("", "save"),
        ("set a", "a"),
        ("set a, set b", "b"),
        ("set a, set None", "save"),
        # a test
        ("enter T, set t", "t"),
        ("set a, enter T, set t, end T", "a"),
        # a fixture's hook outlives its setup, until its teardown ends
        ("enter F, set f, leave F, enter T", "f"),
        ("enter F, set f, leave F, enter T, set t, end T", "f"),
        ("enter F, set f, leave F, enter T, end T, enter F, end F", "save"),
        # set in its teardown: still the fixture's
        ("enter F, set f, leave F, enter F, set None", "save"),
        ("enter F, set f, leave F, enter F, set None, end F", "save"),
        ("set a, enter F, leave F, enter F, set g, end F", "a"),
        # a setup that fails is never re-entered
        ("enter F, set f, leave F, end F", "save"),
        # the most recent call of a live owner wins
        ("enter M, set m, leave M, enter T, set t", "t"),
        ("enter T, set t, enter M, set m, leave M", "m"),
        ("enter T, set t, enter M, set m, leave M, set t2", "t2"),
        ("enter T, set t, enter M, set m, leave M, set t2, end T", "m"),
        # an owner's later call replaces its earlier one
        (
            "enter A, set a, leave A, enter B, set b, leave B, enter A, set a2, end A",
            "b",
        ),
        # a fixture set up inside a test, setting nothing, never keeps the test's hook
        ("enter T, set t, enter M, leave M, end T", "save"),
        ("enter A, set a, leave A, enter T, set t, enter M, leave M, end T", "a"),
        # nor does one that set its hook lose it when the test ends
        ("enter T, enter S, set s, leave S, end T", "s"),
        # leaving or ending an owner that never entered changes nothing
        ("set a, leave X, end X", "a"),
    ],
)
def test_the_active_hook(saved_by, events, expected):
    play(events)
    assert saved_by() == expected
