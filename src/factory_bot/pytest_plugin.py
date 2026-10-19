"""Reseed `fake` (and reset `fake.unique`) before each test, and reseed it for each fixture from the
fixture's own scope; undo a `persist_with` hook when the test or fixture that set it ends; optionally
reset sequences. Disable with -p no:factory_bot."""

import pytest

from factory_bot import _core, fake, reset_sequences, seed

DEFAULT_SEED = 0


def pytest_addoption(parser):
    parser.addini(
        "factory_bot_reset_sequences",
        type="bool",
        default=False,
        help="factory_bot: restart every sequence at 1 before each test.",
    )


def pytest_report_header(config):
    source = " (--randomly-seed)" if _randomly_seed(config) is not None else ""
    return f"factory_bot: seed={_seed(config)}{source}"


# tryfirst: before fixtures run, so they share the test's fresh fake.unique.
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    seed(f"{_seed(item.config)}:{item.nodeid}")
    if item.config.getini("factory_bot_reset_sequences"):
        reset_sequences()


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(fixturedef, request):
    # request.node is the fixture's scope node (test, module, session), not its definition:
    # seeding from the definition would give a function fixture the same data in every test.
    # fake.unique is left alone, so a test and its fixtures share one seen-set.
    hook = _core._persist_hook
    # Registered before setup so it runs after the fixture's own teardown (finalizers are LIFO).
    request.addfinalizer(lambda: _core._set_persist_hook(hook))
    state = fake.random.getstate()
    fake.seed_instance(
        f"{_seed(request.config)}:{request.node.nodeid}::{fixturedef.argname}"
    )
    try:
        return (yield)
    finally:
        # Resume the stream the setup interrupted: the requesting test's data stays its own.
        fake.random.setstate(state)


@pytest.fixture(autouse=True)
def _factory_bot_restore_persist_hook():
    # Undoes what the test body set; pytest_fixture_setup undoes what each fixture set.
    hook = _core._persist_hook
    yield
    _core._set_persist_hook(hook)


def _seed(config):
    randomly = _randomly_seed(config)
    return DEFAULT_SEED if randomly is None else randomly


def _randomly_seed(config):
    # pytest-randomly resolves its option to an int in pytest_configure; absent or a
    # placeholder string ("default", "last") when it is not installed or not active.
    value = getattr(config.option, "randomly_seed", None)
    return value if isinstance(value, int) else None
