import pytest

from factory_bot import FactoryError, build, factory, reset_sequences, sequence


def test_a_sequence_counts_up_from_one_per_build():
    @factory(dict)
    def user(f):
        f.username = sequence(lambda n: f"user{n}")

    assert [build("user")["username"] for _ in range(3)] == ["user1", "user2", "user3"]


def test_each_sequence_keeps_its_own_count():
    @factory(dict)
    def user(f):
        f.username = sequence(lambda n: f"user{n}")
        f.code = sequence(lambda n: n * 10)

    build("user")
    assert build("user") == {"username": "user2", "code": 20}


def test_an_override_does_not_advance_the_sequence():
    @factory(dict)
    def user(f):
        f.username = sequence(lambda n: f"user{n}")

    build("user", username="custom")
    assert build("user")["username"] == "user1"


def test_reset_sequences_starts_every_count_over():
    @factory(dict)
    def user(f):
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
