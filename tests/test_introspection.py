import inspect

import pytest

from factory_bot import FactoryError, f

pytest_plugins = ["pytester"]


def test_reading_f_is_an_attribute_error_that_keeps_the_hint():
    with pytest.raises(AttributeError) as info:
        f.name  # noqa: B018
    assert isinstance(info.value, FactoryError)
    assert "can't read f.name in a definition" in str(info.value)


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
