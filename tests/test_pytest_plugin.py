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


SCOPED = """
import pytest
from factory_bot import fake

@pytest.fixture(scope="module")
def shared():
    return fake.name()

def test_a(shared):
    print(f"test_a={shared}|{fake.name()}")

def test_b():
    print(f"test_b={fake.name()}")

def test_c(shared):
    print(f"test_c={shared}|{fake.name()}")
"""


@pytest.fixture
def scoped(pytester):
    pytester.makepyfile(test_scoped=SCOPED)
    return pytester


def test_a_module_fixtures_data_is_the_same_whichever_test_sets_it_up(scoped):
    shared = {
        names(run(scoped))["test_c"].split("|")[0],
        names(run(scoped, "test_scoped.py::test_c"))["test_c"].split("|")[0],
        names(run(scoped, "test_scoped.py::test_c", "test_scoped.py::test_a"))[
            "test_c"
        ].split("|")[0],
    }
    assert len(shared) == 1


def test_setting_up_a_module_fixture_leaves_the_tests_own_data_alone(scoped):
    # Alone, test_c sets the fixture up; in the suite, test_a already has.
    alone = names(run(scoped, "test_scoped.py::test_c"))["test_c"]
    assert alone == names(run(scoped))["test_c"]


def test_the_seed_and_sequence_reset_are_in_the_header(suite):
    run(suite).stdout.fnmatch_lines(["factory_bot: seed=0, reset_sequences=off"])


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
    result = run(pytester)
    assert names(result) == {"test_a": "user1", "test_b": "user1"}
    result.stdout.fnmatch_lines(["factory_bot: seed=0, reset_sequences=on"])


def test_p_no_factory_bot_disables_the_plugin(suite):
    result = run(suite, "-p", "no:factory_bot")
    assert "factory_bot:" not in result.stdout.str()


def test_pytest_randomly_seed_drives_the_data_too(suite):
    pytest.importorskip("pytest_randomly")

    def randomly(seed, *args):
        result = suite.runpytest("-s", f"--randomly-seed={seed}", *args)
        result.stdout.fnmatch_lines(
            [f"factory_bot: seed={seed} (--randomly-seed), reset_sequences=off"]
        )
        return names(result)

    assert randomly(1) == randomly(1)
    assert randomly(1) != randomly(2)
    assert randomly(1, "test_data.py::test_b")["test_b"] == randomly(1)["test_b"]


def test_pytest_randomly_seed_drives_scoped_fixtures_too(scoped):
    pytest.importorskip("pytest_randomly")

    def randomly(seed, *args):
        return names(scoped.runpytest("-s", f"--randomly-seed={seed}", *args))

    # Each seed shuffles the tests differently, so the first to set `shared` up varies.
    assert randomly(1)["test_c"] == randomly(1, "test_scoped.py::test_c")["test_c"]
    assert randomly(1)["test_a"].split("|")[0] != randomly(2)["test_a"].split("|")[0]


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


PARAMS = """
import pytest
from factory_bot import fake

@pytest.fixture(scope="module", params=__PARAMS__, ids=["a", "b"])
def shared(request):
    return fake.name()

def test_p(shared, request):
    print(f"test_p_{request.node.callspec.id}={shared}")
"""


# An object's repr may hold an address, so it is seeded by the param's index instead.
@pytest.mark.parametrize("params", ['["a", "b"]', "[object(), object()]"])
def test_each_param_of_a_module_fixture_gets_its_own_data(pytester, params):
    pytester.makepyfile(test_params=PARAMS.replace("__PARAMS__", params))
    data = names(run(pytester))
    assert data.keys() == {"test_p_a", "test_p_b"}
    assert data["test_p_a"] != data["test_p_b"]
    alone = names(run(pytester, "test_params.py::test_p[b]"))
    assert alone["test_p_b"] == data["test_p_b"]


OVERRIDE = """
import pytest
from factory_bot import fake

@pytest.fixture
def user(user):
    return f"{user}|{fake.name()}"

def test_override(user):
    print(f"test_override={user}")
"""


def test_a_fixture_overriding_one_of_its_name_gets_its_own_data(pytester):
    pytester.makeconftest(
        "import pytest\nfrom factory_bot import fake\n\n"
        "@pytest.fixture\ndef user():\n    return fake.name()\n"
    )
    pytester.makepyfile(test_override=OVERRIDE)
    inner, outer = names(run(pytester))["test_override"].split("|")
    assert inner != outer


INDIRECT = """
import pytest
from factory_bot import fake

@pytest.fixture(scope="module")
def account(request):
    return fake.name()

@pytest.mark.parametrize("account", ["free"], indirect=True)
def test_free(account):
    print(f"test_free={account}")

@pytest.mark.parametrize("account", ["pro"], indirect=True)
def test_pro(account):
    print(f"test_pro={account}")
"""


def test_each_indirect_param_of_a_module_fixture_gets_its_own_data(pytester):
    pytester.makepyfile(test_indirect=INDIRECT)
    data = names(run(pytester))
    assert data["test_free"] != data["test_pro"]
    assert (
        names(run(pytester, "test_indirect.py::test_pro"))["test_pro"]
        == data["test_pro"]
    )


SHARED_UNIQUE = """
import pytest
from factory_bot import fake

@pytest.fixture(scope="session")
def code():
    return fake.unique.random_int(1, 3)

def test_a(code):
    print("test_a=ok")

def test_b(code):
    print(f"test_b={sorted(fake.unique.random_int(1, 3) for _ in range(3))}")
"""


def test_a_session_fixtures_unique_values_leave_the_tests_alone(pytester):
    # If the fixture's draw counted against test_b alone, its three draws couldn't all fit.
    pytester.makepyfile(test_shared=SHARED_UNIQUE)
    together = names(run(pytester))
    alone = names(run(pytester, "test_shared.py::test_b"))
    assert alone["test_b"] == together["test_b"] == "[1, 2, 3]"


# A fixture's seed() is the fixture's own change: the plugin's restore must not undo it.

SEEDED = """
import pytest
from factory_bot import fake, seed

@pytest.fixture(autouse=__AUTOUSE__)
def pinned():
    seed(42)

@pytest.fixture
def plain():
    return fake.name()

def test_seeded(pinned, plain):
    print(f"test_seeded={fake.name()}")

def test_expected():
    seed(42)
    print(f"test_expected={fake.name()}")
"""


@pytest.mark.parametrize("autouse", [True, False])
def test_seed_in_a_fixture_pins_the_data_after_it(pytester, autouse):
    # plain still draws from its own seed and resumes the pinned stream after it.
    pytester.makepyfile(test_seeded=SEEDED.replace("__AUTOUSE__", str(autouse)))
    data = names(run(pytester))
    assert data["test_seeded"] == data["test_expected"]


# persist_with: one case per lifecycle, for the plugin's finalizer choreography; the rule
# itself is test_persist_owners' table.

HELPERS = """
from factory_bot import create, factory

class Thing:
    by = None

    def save(self):
        self.by = "save"

@factory(Thing)
def thing():
    pass

def hook(name):
    def save(obj):
        obj.by = name
    return save

def saved_by():
    return create(thing).by
"""

OWNERS_CONFTEST = """
import pytest
from factory_bot import persist_with
from helpers import hook, saved_by

persist_with(hook("at_import"))

@pytest.fixture
def in_fixture():
    persist_with(hook("in_fixture"))
    yield
    assert saved_by() == "in_fixture"

@pytest.fixture(scope="module")
def in_module():
    persist_with(hook("in_module"))
    yield
    assert saved_by() == "in_module"

@pytest.fixture(scope="session")
def in_session():
    persist_with(hook("in_session"))
"""

PREAMBLE = """
import pytest
from factory_bot import persist_with
from helpers import hook, saved_by
"""

AT_IMPORT = """
def test_next_module():
    assert saved_by() == "at_import"
"""


@pytest.fixture
def owners(pytester):
    pytester.makepyfile(helpers=HELPERS)
    pytester.makeconftest(OWNERS_CONFTEST)
    return pytester


def run_owners(pytester, passed, *args, **files):
    """Runs the files in name order, each a test module that asserts on saved_by()."""
    pytester.makepyfile(**{name: PREAMBLE + code for name, code in files.items()})
    paths = [f"{name}.py" for name in sorted(files)]
    result = pytester.runpytest("-p", "no:randomly", *args, *paths)
    result.assert_outcomes(passed=passed)


def test_a_hook_set_at_import_lasts_the_session(owners):
    test_1 = """
def test_a():
    assert saved_by() == "at_import"

def test_b(in_fixture):
    pass
"""
    run_owners(owners, 3, test_1=test_1, test_2=AT_IMPORT)


def test_a_function_fixtures_hook_lasts_until_its_teardown(owners):
    # in_fixture's teardown asserts it still sees its own hook.
    test_1 = """
def test_a(in_fixture):
    assert saved_by() == "in_fixture"

def test_b():
    assert saved_by() == "at_import"
"""
    run_owners(owners, 2, test_1=test_1)


def test_a_tests_hook_lasts_until_the_test_ends(owners):
    test_1 = """
def test_a():
    persist_with(hook("in_test"))
    assert saved_by() == "in_test"

def test_b():
    assert saved_by() == "at_import"
"""
    run_owners(owners, 2, test_1=test_1)


def test_a_session_fixture_created_lazily_by_a_test_keeps_its_hook(owners):
    test_1 = """
def test_a(request):
    request.getfixturevalue("in_session")
    assert saved_by() == "in_session"

def test_b(in_session):
    assert saved_by() == "in_session"
"""
    test_2 = """
def test_c():
    assert saved_by() == "in_session"
"""
    run_owners(owners, 3, test_1=test_1, test_2=test_2)


def test_the_most_recent_hook_wins_and_each_lasts_as_long_as_its_owner(owners):
    # in_module's teardown asserts it still sees its own hook.
    test_1 = """
def test_a(request):
    persist_with(hook("in_test"))
    request.getfixturevalue("in_module")
    assert saved_by() == "in_module"
    persist_with(hook("in_test_again"))
    assert saved_by() == "in_test_again"

def test_b(in_module):
    assert saved_by() == "in_module"

def test_c():
    assert saved_by() == "in_module"
"""
    run_owners(owners, 4, test_1=test_1, test_2=AT_IMPORT)


def test_a_hook_set_in_a_fixtures_teardown_ends_with_it(owners):
    test_1 = """
@pytest.fixture
def undoes():
    persist_with(hook("in_fixture"))
    yield
    persist_with(None)  # a manual undo, as written before the plugin did it

def test_a(undoes):
    pass

def test_b():
    assert saved_by() == "at_import"
"""
    run_owners(owners, 2, test_1=test_1)


def test_a_fixture_that_fails_setup_ends_with_its_hook(owners):
    test_1 = """
@pytest.fixture
def broken():
    persist_with(hook("in_broken"))
    raise RuntimeError

def test_a(broken):
    pass

def test_b():
    assert saved_by() == "at_import"
"""
    owners.makepyfile(test_1=PREAMBLE + test_1)
    result = owners.runpytest("-p", "no:randomly")
    result.assert_outcomes(passed=1, errors=1)


def test_p_no_factory_bot_makes_persist_with_global(owners):
    test_1 = """
def test_a():
    persist_with(hook("in_test"))

def test_b():
    assert saved_by() == "in_test"
"""
    run_owners(owners, 2, "-p", "no:factory_bot", test_1=test_1)


def test_hooks_hold_under_xdist_and_randomly(owners):
    pytest.importorskip("xdist")
    pytest.importorskip("pytest_randomly")
    module = """
def test_fixture(in_fixture):
    assert saved_by() == "in_fixture"

def test_body():
    persist_with(hook("in_test"))
    assert saved_by() == "in_test"

def test_import():
    assert saved_by() == "at_import"
"""
    owners.makepyfile(**{f"test_{i}": PREAMBLE + module for i in range(4)})
    for seed in (1, 2):
        # A subprocess: a second in-process run would redefine helpers' factory.
        result = owners.runpytest_subprocess("-n", "2", f"--randomly-seed={seed}")
        result.assert_outcomes(passed=12)
