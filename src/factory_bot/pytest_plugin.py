"""Reseed `fake` (and reset `fake.unique`) before each test; optionally reset sequences. Disable with -p no:factory_bot."""

import pytest

from factory_bot import reset_sequences, seed

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


# tryfirst: reseed before fixtures run, so data they build is reproducible too.
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    seed(f"{_seed(item.config)}:{item.nodeid}")
    if item.config.getini("factory_bot_reset_sequences"):
        reset_sequences()


def _seed(config):
    randomly = _randomly_seed(config)
    return DEFAULT_SEED if randomly is None else randomly


def _randomly_seed(config):
    # pytest-randomly resolves its option to an int in pytest_configure; absent or a
    # placeholder string ("default", "last") when it is not installed or not active.
    value = getattr(config.option, "randomly_seed", None)
    return value if isinstance(value, int) else None
