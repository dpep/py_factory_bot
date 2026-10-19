from faker import Faker

fake = Faker()


def seed(value: float | str | bytes | None) -> None:
    """Seed `fake` so a test's generated data is reproducible, `fake.unique` included."""
    fake.seed_instance(value)
    fake.unique.clear()  # its seen-values would otherwise make output depend on history
