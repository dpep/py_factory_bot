"""Reseed `fake` (and reset `fake.unique`) before each test, and reseed it for each fixture from the
fixture's own scope; tell persist_with which test or fixture is running, so its hook ends with
it; optionally reset sequences. Disable with -p no:factory_bot."""

import pytest

from factory_bot import _core, _fake, reset_sequences, seed

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


# tryfirst: before fixtures run, so its function fixtures share the test's fresh fake.unique.
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
    owner = object()
    # Registered before setup, so it runs after the fixture's own teardown (finalizers are LIFO).
    request.addfinalizer(lambda: _core._end_owner(owner))
    # baseid tells apart a fixture from the same-named one it overrides.
    key = f"{_seed(request.config)}:{request.node.nodeid}::{fixturedef.baseid}::{fixturedef.argname}"
    if hasattr(request, "param"):
        key += f"[{_param_id(request)}]"
    # A higher-scope fixture outlives the test that sets it up, so its fake.unique values
    # must not count against that test's.
    with _fake.scoped(key, own_unique=fixturedef.scope != "function"):
        _core._enter_owner(owner)
        outcome = yield
        _core._leave_owner(owner)
    if outcome.excinfo is None:
        # Runs before the fixture's teardown, so a persist_with there is the fixture's too.
        request.addfinalizer(lambda: _core._enter_owner(owner))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    owner = object()
    _core._enter_owner(owner)
    yield
    _core._end_owner(owner)


def _param_id(request):
    # A higher-scope fixture's node is the same for every param, and an indirect param's
    # index is 0 in each test, so name it by value, as pytest's ids do; a repr may hold an
    # address, though, so other objects fall back to the (undocumented) index.
    if isinstance(request.param, (str, int, float, type(None))):
        return repr(request.param)
    return getattr(request, "param_index", 0)


def _seed(config):
    randomly = _randomly_seed(config)
    return DEFAULT_SEED if randomly is None else randomly


def _randomly_seed(config):
    # pytest-randomly resolves its option to an int in pytest_configure; absent or a
    # placeholder string ("default", "last") when it is not installed or not active.
    value = getattr(config.option, "randomly_seed", None)
    return value if isinstance(value, int) else None
