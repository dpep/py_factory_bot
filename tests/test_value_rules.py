"""The three value rules, held against real CPython values rather than the four obvious types.

- Calling: functions are called per build; every other object is stored.
- Copying: containers written in a body are copied per build; anything passed at build time
  is used as given.
- Markers: they work only as an attribute's whole value.

A value that slips past a rule is one more row.
"""

import collections
import datetime
import enum
import functools
import operator
import time
import uuid
from unittest.mock import MagicMock, Mock

import pytest

from factory_bot import FactoryError, build, f, factory, fake, sequence

# --- Calling -------------------------------------------------------------------------


class _Thing:
    def method(self):
        return 1

    @staticmethod
    def static():
        return 2

    @classmethod
    def klass(cls):
        return 3


class _Handler:
    def __call__(self):
        return "handled"


class _Status(enum.Enum):
    ACTIVE = "active"


def _defined():
    return 1


def _generate():
    yield 1


async def _fetch():
    return 1


async def _stream():
    yield 1


CALLED = {
    "def": _defined,
    "lambda": lambda: 1,
    "bound method": _Thing().method,
    "staticmethod": _Thing.static,
    "a staticmethod object": staticmethod(_defined),
    "classmethod": _Thing.klass,
    "datetime.now": datetime.datetime.now,
    "time.time": time.time,
    "uuid.uuid4": uuid.uuid4,
    "a builtin's bound method": {}.copy,
    "partial": functools.partial(_defined),
    "lru_cache": functools.lru_cache(_defined),
    "functools.cache": functools.cache(_defined),
    # It passes isinstance(..., FunctionType), so it stands in for the function.
    "Mock(spec=func)": Mock(spec=_defined, return_value="mocked"),
    "fake.first_name": fake.first_name,
    "fake.unique.first_name": fake.unique.first_name,
}
STORED = {
    "Mock()": Mock(),
    "MagicMock()": MagicMock(),
    "a callable instance": _Handler(),
    "operator.methodcaller": operator.methodcaller("upper"),
    "operator.itemgetter": operator.itemgetter(0),
    "a class": _Thing,
    "an Enum": _Status,
    "an Enum member": _Status.ACTIVE,
    "a cached_property object": functools.cached_property(_defined),
    "a classmethod object": classmethod(_defined),
}
REJECTED = {
    "async def": (_fetch, "is an async def"),
    "async generator": (_stream, "is an async def"),
    "partial of an async def": (functools.partial(_fetch), "is an async def"),
    "generator function": (_generate, "is a generator function"),
    "lambda returning a coroutine": (lambda: _fetch(), "returned a coroutine"),
}


def _declare(value):
    @factory(dict)
    def thing():
        f.value = value


@pytest.mark.parametrize("value", CALLED.values(), ids=CALLED)
def test_a_function_is_called_on_every_build(value):
    _declare(value)
    assert build("thing")["value"] is not value


@pytest.mark.parametrize("value", STORED.values(), ids=STORED)
def test_every_other_object_is_stored(value):
    _declare(value)
    assert build("thing")["value"] is value


@pytest.mark.parametrize("value,message", REJECTED.values(), ids=REJECTED)
def test_a_function_that_gives_no_value_is_an_error(value, message):
    _declare(value)
    with pytest.raises(FactoryError, match=message):
        build("thing")


ANY_CALLABLE = {**CALLED, **STORED, **{k: v for k, (v, _) in REJECTED.items()}}


@pytest.mark.parametrize("value", ANY_CALLABLE.values(), ids=ANY_CALLABLE)
def test_a_callable_passed_at_build_time_is_never_called(value):
    _declare(None)
    assert build("thing", value=value)["value"] is value


# --- Copying -------------------------------------------------------------------------

_Pair = collections.namedtuple("_Pair", "a b")


class _Bag(dict):
    pass


class _Tags(list):
    pass


def _cyclic_list():
    value = [[]]
    value.append(value)
    return value


def _cyclic_dict():
    value = {"k": []}
    value["self"] = value
    return value


def _cyclic_tuple():
    value = ([],)
    value[0].append(value)
    return value


def _append(v):
    v.append(1)
    v[0].append(1)


def _add_key(v):
    v["new"] = 1
    v["k"].append(1)


# name: (make the value, mutate a build's copy deeply)
CONTAINERS = {
    "list": (lambda: [[]], _append),
    "dict": (lambda: {"k": []}, _add_key),
    "set": (lambda: {1}, lambda v: v.add(2)),
    "tuple": (lambda: ([],), lambda v: v[0].append(1)),
    "frozenset": (lambda: frozenset({1}), lambda v: None),
    "defaultdict": (
        lambda: collections.defaultdict(list, k=[]),
        lambda v: v["other"].append(v["k"].append(1)),
    ),
    "Counter": (lambda: collections.Counter(a=1), lambda v: v.update("ab")),
    "OrderedDict": (
        lambda: collections.OrderedDict(b=[], a=[]),
        lambda v: v.move_to_end("b") or v["a"].append(1),
    ),
    "namedtuple": (lambda: _Pair([], {}), lambda v: v.a.append(1) or v.b.update(x=1)),
    "deque": (lambda: collections.deque([[]], maxlen=5), _append),
    "bytearray": (lambda: bytearray(b"ab"), lambda v: v.append(1)),
    "a dict subclass": (lambda: _Bag(k=[]), _add_key),
    "a list subclass": (lambda: _Tags([[]]), _append),
    "nested": (
        lambda: {
            "pairs": [_Pair(collections.OrderedDict(x=[]), collections.deque())],
            "counts": collections.defaultdict(collections.Counter),
        },
        lambda v: (
            v["pairs"][0].a["x"].append(1)
            or v["pairs"][0].b.append(1)
            or v["counts"]["a"].update("b")
        ),
    ),
    "a cyclic list": (_cyclic_list, lambda v: v[0].append(1)),
    "a cyclic dict": (_cyclic_dict, lambda v: v["k"].append(1)),
    "a cycle through a tuple": (_cyclic_tuple, lambda v: v[0].append(1)),
}


def _shape(value):
    """What a copy must keep beside equality: type, order, default_factory and maxlen."""
    return (
        type(value),
        list(value) if isinstance(value, dict) else None,
        getattr(value, "default_factory", None),
        getattr(value, "maxlen", None),
    )


@pytest.mark.parametrize("make,mutate", CONTAINERS.values(), ids=CONTAINERS)
def test_a_container_written_in_a_body_is_copied_per_build(make, mutate):
    _declare(make())
    first, second = build("thing")["value"], build("thing")["value"]
    expected = make()
    assert _shape(first) == _shape(expected)
    mutate(first)
    assert repr(second) == repr(expected)
    assert _shape(second) == _shape(expected)


def test_a_cyclic_copy_refers_to_itself():
    _declare([_cyclic_list(), _cyclic_tuple()])
    in_list, in_tuple = build("thing")["value"]
    assert in_list[1] is in_list
    assert in_tuple[0][0] is in_tuple


@pytest.mark.parametrize("make,mutate", CONTAINERS.values(), ids=CONTAINERS)
def test_a_container_passed_at_build_time_is_used_as_given(make, mutate):
    _declare(None)
    value = make()
    assert build("thing", value=value)["value"] is value


# --- Markers -------------------------------------------------------------------------


def _counter():
    return sequence(lambda n: n)


INSIDE = {
    "list": lambda m: [m],
    "dict value": lambda m: {"k": m},
    "dict key": lambda m: {m: 1},
    "set": lambda m: {m},
    "tuple": lambda m: (m,),
    "frozenset": lambda m: frozenset({m}),
    "defaultdict": lambda m: collections.defaultdict(list, k=m),
    "OrderedDict": lambda m: collections.OrderedDict(k=m),
    "namedtuple": lambda m: _Pair(m, None),
    "deque": lambda m: collections.deque([m]),
    "a dict subclass": lambda m: _Bag(k=m),
    "nested": lambda m: {"k": [_Pair(collections.deque([m]), None)]},
}


@pytest.mark.parametrize("wrap", INSIDE.values(), ids=INSIDE)
def test_a_marker_inside_a_container_is_an_error(wrap):
    _declare(wrap(_counter()))
    with pytest.raises(
        FactoryError, match="is inside a container, which never evaluates it"
    ):
        build("thing")
