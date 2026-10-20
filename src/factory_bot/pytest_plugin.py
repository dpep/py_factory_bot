"""Reseed `fake` (and reset `fake.unique`) before each test, and reseed it for each fixture from the
fixture's own scope; tell persist_with which test or fixture is running, so its hook ends with
it; optionally reset sequences. Disable with -p no:factory_bot."""

import pytest

from factory_bot import _core, _fake, fake, reset_sequences, seed

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
    reset = "on" if config.getini("factory_bot_reset_sequences") else "off"
    return f"factory_bot: seed={_seed(config)}{source}, reset_sequences={reset}"


# tryfirst: before fixtures run, so they share the test's fresh fake.unique.
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    seed(f"{_seed(item.config)}:{item.nodeid}")
    if item.config.getini("factory_bot_reset_sequences"):
        reset_sequences()


# hookwrapper, not wrapper: pluggy < 1.2 rejects wrapper= at import, breaking every run.
@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    # request.node is the fixture's scope node (test, module, session), not its definition:
    # seeding from the definition would give a function fixture the same data in every test.
    # fake.unique is left alone, so a test and its fixtures share one seen-set.
    owner = object()
    # Registered before setup, so it runs after the fixture's own teardown (finalizers are LIFO).
    request.addfinalizer(lambda: _core._end_owner(owner))
    state, generation = fake.random.getstate(), _fake._generation
    key = f"{_seed(request.config)}:{request.node.nodeid}::{fixturedef.argname}"
    if hasattr(request, "param"):
        # A module fixture's node is the same for every param. param_index is undocumented
        # (request.param's repr can hold an address); a test pins it, and losing it here
        # only costs distinct data per param.
        key += f"[{getattr(request, 'param_index', 0)}]"
    fake.seed_instance(key)
    _core._enter_owner(owner)
    outcome = yield
    _core._leave_owner(owner)
    # Resume the stream the setup interrupted, so the requesting test's data stays its
    # own; unless the fixture called seed(), which is the stream it chose.
    if _fake._generation == generation:
        fake.random.setstate(state)
    if outcome.excinfo is None:
        # Runs before the fixture's teardown, so a persist_with there is the fixture's too.
        request.addfinalizer(lambda: _core._enter_owner(owner))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    owner = object()
    _core._enter_owner(owner)
    yield
    _core._end_owner(owner)


def _seed(config):
    randomly = _randomly_seed(config)
    return DEFAULT_SEED if randomly is None else randomly


def _randomly_seed(config):
    # pytest-randomly resolves its option to an int in pytest_configure; absent or a
    # placeholder string ("default", "last") when it is not installed or not active.
    value = getattr(config.option, "randomly_seed", None)
    return value if isinstance(value, int) else None
