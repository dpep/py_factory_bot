from faker import Faker

from factory_bot import build, factory, fake, seed


def test_fake_is_a_shared_faker_whose_methods_are_lazy_values():
    @factory(dict)
    def user(f):
        f.first_name = fake.first_name
        f.bio = fake.paragraph  # its parameters all have defaults, so none are injected

    assert isinstance(fake, Faker)
    users = [build("user") for _ in range(5)]
    assert len({u["first_name"] + u["bio"] for u in users}) > 1


def test_seed_makes_fake_values_reproducible():
    @factory(dict)
    def user(f):
        f.first_name = fake.first_name

    seed(1234)
    first = [build("user") for _ in range(3)]
    seed(1234)
    assert [build("user") for _ in range(3)] == first
