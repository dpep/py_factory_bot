import inspect
import re

import pytest

from factory_bot import FactoryError, association, f, sequence, transient

pytest_plugins = ["pytester"]


def test_reading_f_is_an_attribute_error_that_keeps_the_hint():
    with pytest.raises(AttributeError) as info:
        f.name  # noqa: B018
    assert isinstance(info.value, FactoryError)
    assert "can't read f.name: f only declares attributes" in str(info.value)


def test_f_honors_hasattr_and_unwrap():
    assert not hasattr(f, "__wrapped__")
    assert inspect.unwrap(f) is f


def test_doctest_modules_collects_a_module_that_imports_f(pytester):
    pytester.makepyfile(
        factories='''
from factory_bot import f

def double(x):
    """
    >>> double(2)
    4
    """
    return 2 * x
'''
    )
    result = pytester.runpytest_subprocess("--doctest-modules", "-p", "no:randomly")
    result.assert_outcomes(passed=1)


def test_markers_show_what_they_declare():
    assert repr(association("author", "admin", name="A")) == "<association 'author'>"
    assert repr(transient([1])) == "<transient [1]>"
    assert re.fullmatch(
        r"<sequence \(test_introspection\.py:\d+\)>", repr(sequence(lambda n: n))
    )
