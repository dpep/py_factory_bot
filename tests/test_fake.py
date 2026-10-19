import inspect

import pytest
from faker import Faker

from factory_bot import FactoryError, after_build, build, f, factory, fake, seed, trait
from factory_bot._fake import _Fake


def test_fake_is_a_shared_faker_whose_methods_are_lazy_values():
    @factory(dict)
    def user():
        f.first_name = fake.first_name
        f.bio = fake.paragraph  # its parameters all have defaults, so none are injected

    assert isinstance(fake, Faker)
    users = [build("user") for _ in range(5)]
    assert len({u["first_name"] + u["bio"] for u in users}) > 1


def test_seed_makes_fake_values_reproducible():
    @factory(dict)
    def user():
        f.first_name = fake.first_name

    seed(1234)
    first = [build("user") for _ in range(3)]
    seed(1234)
    assert [build("user") for _ in range(3)] == first


def test_seed_resets_fake_unique_so_the_same_seed_gives_the_same_values():
    seed(1234)
    first = [fake.unique.random_int(1, 5) for _ in range(4)]
    seed(1234)
    assert [fake.unique.random_int(1, 5) for _ in range(4)] == first


# Frozen calls: a provider called while a body runs would hand every build one value.


def test_calling_fake_in_a_body_is_an_error_naming_the_fix():
    with pytest.raises(FactoryError) as info:

        @factory(dict)
        def user():
            f.email = fake.first_name()

    assert str(info.value) == (
        "Factory 'user': fake.first_name() was called while the factory was being defined,"
        " so every build would get the same value."
        " Pass the method instead, without parentheses: fake.first_name"
        " (or lambda: fake.first_name(...) for arguments)"
    )


@pytest.mark.parametrize("proxy", ["unique", "optional"])
def test_unique_and_optional_calls_in_a_trait_name_the_call_written(proxy):
    # Faker's proxies call back into fake: the error must name fake.unique.x, not fake.x.
    with pytest.raises(
        FactoryError,
        match=rf"^Factory 'user': fake\.{proxy}\.random_int\(\) was called .* without parentheses: fake\.{proxy}\.random_int \(or",
    ):

        @factory(dict)
        def user():
            @trait
            def vip():
                f.code = getattr(fake, proxy).random_int(min=1, max=9)


def test_the_uncalled_method_stays_lazy_and_keeps_its_signature():
    stored = {}

    @factory(dict)
    def user():
        # Its parameters have defaults: nothing injected.
        f.bio = stored["bio"] = fake.paragraph
        f.code = fake.unique.random_int

    # inspect follows __wrapped__, so dependency injection sees the provider's parameters.
    assert "nb_sentences" in inspect.signature(stored["bio"]).parameters
    seed(1)
    first = [build("user") for _ in range(3)]
    seed(1)
    assert [build("user") for _ in range(3)] == first
    assert len({u["code"] for u in first}) == 3


def test_calls_at_build_time_and_outside_bodies_are_allowed():
    assert fake.first_name()

    @factory(dict)
    def user():
        f.age = lambda: fake.random_int(min=18, max=90)

        @after_build
        def tag(user):
            user["tag"] = fake.optional.word(prob=1.0) + fake.unique.word()

    assert set(build("user")) == {"age", "tag"}


def test_fakers_own_members_still_work_in_a_body():
    @factory(dict)
    def user():
        seed(3)  # touches fake.unique.clear()
        assert fake["en_US"] is fake
        f.n = fake.random.randint(1, 1)  # a Random, not a provider: not guarded

    assert build("user") == {"n": 1}


def test_a_multi_locale_fake_still_proxies_and_guards():
    multi = _Fake(["en_US", "ja_JP"])
    assert multi["ja_JP"].first_name() and multi.first_name()

    with pytest.raises(FactoryError, match=r"fake\.first_name\(\) was called"):

        @factory(dict)
        def user():
            f.name = multi.first_name()
