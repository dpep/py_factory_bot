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


HOOKS_CONFTEST = """
import pytest
from factory_bot import persist_with

def at_import(obj): ...
def in_fixture(obj): ...
def in_session(obj): ...

persist_with(at_import)

@pytest.fixture
def leaky():
    persist_with(in_fixture)  # no teardown

@pytest.fixture(scope="session")
def session_hook():
    persist_with(in_session)  # no teardown
"""

HOOKS = """
from factory_bot import _core, persist_with

def in_test(obj): ...

def hook():
    return _core._persist_hook.__name__

def test_a_fixture(leaky):
    print(f"test_a_fixture={hook()}")

def test_b_body():
    persist_with(in_test)
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


def test_a_persist_with_hook_set_by_a_test_or_its_function_fixtures_is_undone_after_it(
    hooks,
):
    # A conftest's import-time hook is the baseline every test returns to.
    data = names(run(hooks))
    assert data["test_a_fixture"] == "in_fixture"
    assert data["test_b_body"] == "in_test"
    assert data["test_c_after"] == "at_import"


def test_a_session_fixtures_persist_with_hook_stays_while_the_session_fixture_does(
    hooks,
):
    # The restore runs inside the higher-scoped fixtures, so they own their own teardown.
    data = names(run(hooks))
    assert data["test_d_session"] == "in_session"
    assert data["test_e_after_session"] == "in_session"


MODULE_HOOK = """
import pytest
from factory_bot import _core, persist_with

def in_module(obj): ...

@pytest.fixture(scope="module")
def module_hook():
    persist_with(in_module)  # no undo
    yield
    print(f"teardown={_core._persist_hook.__name__}")

def test_m1(module_hook):
    print(f"test_m1={_core._persist_hook.__name__}")
"""

NEXT_MODULE = """
from factory_bot import _core

def test_m2():
    print(f"test_m2={_core._persist_hook.__name__}")
"""


@pytest.fixture
def modules(hooks):
    hooks.makepyfile(test_m1=MODULE_HOOK, test_m2=NEXT_MODULE)
    return hooks


def test_a_module_fixtures_persist_with_hook_is_undone_after_its_teardown(modules):
    result = run(modules, "test_m1.py", "test_m2.py")
    assert names(result) == {"test_m1": "in_module", "test_m2": "at_import"}
    # Undone after the fixture's own teardown, which may still save with it.
    assert "teardown=in_module" in result.stdout.str()


def test_a_session_fixtures_persist_with_hook_lasts_the_session(hooks):
    hooks.makepyfile(
        test_s1="def test_s1(session_hook):\n    print('test_s1=ok')",
        test_s2=NEXT_MODULE,
    )
    data = names(run(hooks, "test_s1.py", "test_s2.py"))
    assert data["test_m2"] == "in_session"


def test_p_no_factory_bot_leaves_the_persist_with_hook_alone(hooks):
    data = names(run(hooks, "-p", "no:factory_bot"))
    assert data["test_a_fixture"] == "in_fixture"
    assert data["test_b_body"] == "in_test"
    assert data["test_c_after"] == "in_test"


def test_p_no_factory_bot_leaves_a_module_fixtures_hook_in_place(modules):
    data = names(run(modules, "test_m1.py", "test_m2.py", "-p", "no:factory_bot"))
    assert data["test_m2"] == "in_module"


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


# A fixture restores only a hook it changed: the hook it found may be a test's, already undone.

LAZY = """
import pytest
from factory_bot import persist_with

def in_test(obj): ...

@pytest.fixture(scope="module")
def mod_resource():
    return "resource"

@pytest.fixture(scope="class")
def cls_resource():
    return "resource"

class TestK:
    def test_class(self, request):
        persist_with(in_test)
        request.getfixturevalue("cls_resource")

    def test_after_class(self):
        pass

def test_module(request):
    persist_with(in_test)
    request.getfixturevalue("mod_resource")
"""


@pytest.mark.parametrize("which", ["test_lazy.py", "test_lazy.py::TestK"])
def test_a_fixture_set_up_lazily_does_not_restore_the_tests_hook(hooks, which):
    hooks.makepyfile(test_lazy=LAZY, test_next=NEXT_MODULE)
    result = hooks.runpytest("-s", "-p", "no:randomly", which, "test_next.py")
    result.assert_outcomes(passed=4 if which == "test_lazy.py" else 3)
    assert names(result)["test_m2"] == "at_import"


AUTOUSE_CONFTEST = """
import pytest
from factory_bot import _core, persist_with

def at_import(obj): ...
def in_autouse(obj): ...

persist_with(at_import)

@pytest.fixture(autouse=True)
def autouse_hook():
    persist_with(in_autouse)  # no undo, like a per-test database fixture

@pytest.fixture(scope="session")
def session_resource():  # like pytest-django's django_db_setup
    return "resource"

def pytest_sessionfinish():
    print(f"test_session_end={_core._persist_hook.__name__}")
"""


def test_a_session_fixture_set_up_after_an_autouse_hook_does_not_restore_it(
    pytester,
):
    pytester.makeconftest(AUTOUSE_CONFTEST)
    pytester.makepyfile(
        test_lazy="def test_lazy(request):\n    request.getfixturevalue('session_resource')"
    )
    # Faker's plugin sets up a session fixture first, whose teardown would mask the leak.
    result = pytester.runpytest("-s", "-p", "no:randomly", "-p", "no:faker")
    result.assert_outcomes(passed=1)
    assert names(result)["test_session_end"] == "at_import"
