import re

import pytest

pytest_plugins = ["pytester"]

TESTS = """
import pytest
from factory_bot import fake

@pytest.fixture
def name():
    return fake.name()

def test_a(name):
    fake.name(), fake.name(), fake.name()  # consumes, so test_b would shift without a reseed
    print(f"test_a={name}")

def test_b(name):
    print(f"test_b={name}")
"""


@pytest.fixture
def suite(pytester):
    pytester.makepyfile(test_data=TESTS)
    return pytester


def names(result):
    return dict(re.findall(r"(test_\w+)=(.+)", result.stdout.str()))


def run(pytester, *args):
    result = pytester.runpytest("-s", "-p", "no:randomly", *args)
    result.assert_outcomes(passed=len(names(result)))
    return result


def test_data_is_the_same_alone_in_the_suite_and_in_any_order(suite):
    together = names(run(suite))
    reversed_order = names(run(suite, "test_data.py::test_b", "test_data.py::test_a"))
    alone = names(run(suite, "test_data.py::test_b"))

    assert reversed_order == together
    assert alone["test_b"] == together["test_b"]


def test_each_test_gets_its_own_data(suite):
    # Identical data per test would collide on unique columns in suites that keep rows.
    data = names(run(suite))
    assert data["test_a"] != data["test_b"]


def test_the_seed_is_in_the_header(suite):
    run(suite).stdout.fnmatch_lines(["factory_bot: seed=0"])


SEQUENCES = """
from factory_bot import build, f, factory, sequence

@factory(dict)
def user():
    f.username = sequence(lambda n: f"user{n}")

def test_a():
    print(f"test_a={build('user')['username']}")

def test_b():
    print(f"test_b={build('user')['username']}")
"""


def test_sequences_keep_counting_across_tests_by_default(pytester):
    pytester.makepyfile(test_seq=SEQUENCES)
    assert names(run(pytester)) == {"test_a": "user1", "test_b": "user2"}


def test_factory_bot_reset_sequences_restarts_them_per_test(pytester):
    pytester.makepyfile(test_seq=SEQUENCES)
    pytester.makeini("[pytest]\nfactory_bot_reset_sequences = true\n")
    assert names(run(pytester)) == {"test_a": "user1", "test_b": "user1"}


def test_p_no_factory_bot_disables_the_plugin(suite):
    result = run(suite, "-p", "no:factory_bot")
    assert "factory_bot:" not in result.stdout.str()


HOOKS_CONFTEST = """
import pytest
from factory_bot import to_create

def at_import(obj): ...
def in_fixture(obj): ...
def in_session(obj): ...

to_create(at_import)

@pytest.fixture
def leaky():
    to_create(in_fixture)  # no teardown

@pytest.fixture(scope="session")
def session_hook():
    to_create(in_session)  # no teardown
"""

HOOKS = """
from factory_bot import _core, to_create

def in_test(obj): ...

def hook():
    return _core._to_create.__name__

def test_a_fixture(leaky):
    print(f"test_a_fixture={hook()}")

def test_b_body():
    to_create(in_test)
    print(f"test_b_body={hook()}")

def test_c_after():
    print(f"test_c_after={hook()}")

def test_d_session(session_hook):
    print(f"test_d_session={hook()}")

def test_e_after_session():
    print(f"test_e_after_session={hook()}")
"""


@pytest.fixture
def hooks(pytester):
    pytester.makeconftest(HOOKS_CONFTEST)
    pytester.makepyfile(test_hooks=HOOKS)
    return pytester


def test_a_to_create_hook_set_by_a_test_or_its_function_fixtures_is_undone_after_it(
    hooks,
):
    # A conftest's import-time hook is the baseline every test returns to.
    data = names(run(hooks))
    assert data["test_a_fixture"] == "in_fixture"
    assert data["test_b_body"] == "in_test"
    assert data["test_c_after"] == "at_import"


def test_a_session_fixtures_to_create_hook_stays_while_the_session_fixture_does(hooks):
    # The restore runs inside the higher-scoped fixtures, so they own their own teardown.
    data = names(run(hooks))
    assert data["test_d_session"] == "in_session"
    assert data["test_e_after_session"] == "in_session"


def test_p_no_factory_bot_leaves_the_to_create_hook_alone(hooks):
    data = names(run(hooks, "-p", "no:factory_bot"))
    assert data["test_a_fixture"] == "in_fixture"
    assert data["test_b_body"] == "in_test"
    assert data["test_c_after"] == "in_test"


def test_pytest_randomly_seed_drives_the_data_too(suite):
    pytest.importorskip("pytest_randomly")

    def randomly(seed, *args):
        result = suite.runpytest("-s", f"--randomly-seed={seed}", *args)
        result.stdout.fnmatch_lines([f"factory_bot: seed={seed} (--randomly-seed)"])
        return names(result)

    assert randomly(1) == randomly(1)
    assert randomly(1) != randomly(2)
    assert randomly(1, "test_data.py::test_b")["test_b"] == randomly(1)["test_b"]


UNIQUE = """
from factory_bot import fake

def test_a():
    print(f"test_a={[fake.unique.random_int(1, 5) for _ in range(4)]}")

def test_b():
    print(f"test_b={[fake.unique.random_int(1, 5) for _ in range(4)]}")
"""


def test_fake_unique_starts_fresh_each_test(pytester):
    # Without a reset the second test exhausts the pool of five.
    pytester.makepyfile(test_unique=UNIQUE)
    together = names(run(pytester))
    reversed_order = names(
        run(pytester, "test_unique.py::test_b", "test_unique.py::test_a")
    )
    alone = names(run(pytester, "test_unique.py::test_b"))

    assert reversed_order == together
    assert alone["test_b"] == together["test_b"]
