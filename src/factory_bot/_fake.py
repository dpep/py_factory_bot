from faker import Faker

fake = Faker()


def seed(value):
    """Seed `fake` so a test's generated data is reproducible."""
    fake.seed_instance(value)
