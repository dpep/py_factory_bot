from faker import Faker

fake = Faker()


def seed(value: float | str | bytes | None) -> None:
    """Seed `fake` so a test's generated data is reproducible."""
    fake.seed_instance(value)
