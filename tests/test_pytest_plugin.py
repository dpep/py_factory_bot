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
    result = pytester.runpytest_subprocess("-s", "-p", "no:randomly", *args)
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
from factory_bot import build, factory, sequence

@factory(dict)
def user(f):
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


def test_pytest_randomly_seed_drives_the_data_too(suite):
    pytest.importorskip("pytest_randomly")

    def randomly(seed, *args):
        result = suite.runpytest_subprocess("-s", f"--randomly-seed={seed}", *args)
        result.stdout.fnmatch_lines([f"factory_bot: seed={seed} (--randomly-seed)"])
        return names(result)

    assert randomly(1) == randomly(1)
    assert randomly(1) != randomly(2)
    assert randomly(1, "test_data.py::test_b")["test_b"] == randomly(1)["test_b"]
