import re

import pytest

from factory_bot import (
    FactoryError,
    build,
    f,
    factory,
    reset_sequences,
    sequence,
    transient,
)


def test_a_sequence_counts_up_from_one_per_build():
    @factory(dict)
    def user():
        f.username = sequence(lambda n: f"user{n}")

    assert [build("user")["username"] for _ in range(3)] == ["user1", "user2", "user3"]


def test_a_builtin_without_a_signature_is_trusted_to_take_the_counter():
    @factory(dict)
    def user():
        f.code = sequence(str)

    assert [build("user")["code"] for _ in range(2)] == ["1", "2"]


def test_each_sequence_keeps_its_own_count():
    @factory(dict)
    def user():
        f.username = sequence(lambda n: f"user{n}")
        f.code = sequence(lambda n: n * 10)

    build("user")
    assert build("user") == {"username": "user2", "code": 20}


def test_an_override_does_not_advance_the_sequence():
    @factory(dict)
    def user():
        f.username = sequence(lambda n: f"user{n}")

    build("user", username="custom")
    assert build("user")["username"] == "user1"


def test_reset_sequences_starts_every_count_over():
    @factory(dict)
    def user():
        f.username = sequence(lambda n: f"user{n}")

    build("user")
    reset_sequences()
    assert build("user")["username"] == "user1"


def test_a_sequence_needs_a_function_of_the_counter():
    with pytest.raises(
        FactoryError,
        match=r"sequence\(\) takes a function of the counter, e\.g\. sequence\(lambda n:",
    ):
        sequence("user")
    for counterless in (lambda: 1, lambda *, title: title):
        with pytest.raises(FactoryError, match=r"sequence\(\) takes a function"):
            sequence(counterless)


def test_a_sequence_passed_as_an_override_gives_its_next_value():
    @factory(dict)
    def user():
        f.username = "ann"

    seq = sequence(lambda n: f"user{n}")
    assert [build("user", username=seq)["username"] for _ in range(2)] == [
        "user1",
        "user2",
    ]


def test_a_sequence_takes_the_counter_first_and_attributes_by_name():
    @factory(dict)
    def page():
        f.title = "Hello"
        f.prefix = transient("p-")
        f.slug = sequence(lambda n, title, prefix: f"{prefix}{title.lower()}-{n}")

    assert build("page")["slug"] == "p-hello-1"
    assert build("page", title="About")["slug"] == "p-about-2"


def test_the_counter_is_the_first_parameter_whatever_its_name():
    @factory(dict)
    def row():
        f.n = "attr"
        f.code = sequence(lambda i, n: f"{n}-{i}")

    assert build("row")["code"] == "attr-1"


def test_a_shared_sequence_takes_dependencies_from_the_factory_building():
    seq = sequence(lambda n, name: f"{name}{n}")

    @factory(dict)
    def a():
        f.name = "a"
        f.code = seq

    @factory(dict)
    def b():
        f.name = "b"
        f.code = seq

    assert [build("a")["code"], build("b")["code"]] == ["a1", "b2"]
    reset_sequences()
    assert build("b")["code"] == "b1"


def test_a_sequence_override_gets_dependencies_too():
    @factory(dict)
    def page():
        f.title = "Hi"
        f.slug = "fixed"

    assert build("page", slug=sequence(lambda n, title: f"{title}{n}"))["slug"] == "Hi1"


def test_a_missing_sequence_dependency_names_the_factory():
    @factory(dict)
    def page():
        f.title = "Hi"
        f.slug = sequence(lambda n, ttle: n)

    message = "Factory 'page': 'slug' depends on 'ttle', which is not defined. Did you mean 'title'?"
    with pytest.raises(FactoryError, match=f"^{re.escape(message)}"):
        build("page")
