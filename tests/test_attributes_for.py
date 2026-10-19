from support.models import User

from factory_bot import attributes_for, f, factory, sequence, trait


def test_attributes_for_returns_the_resolved_attributes_without_building():
    @factory(User)
    def user():
        f.first_name = "John"
        f.email = lambda first_name: f"{first_name}@example.com"
        f.username = sequence(lambda n: f"user{n}")
        f.admin = False

        @trait
        def admin():
            f.admin = True

    assert attributes_for("user", "admin", first_name="Ann") == {
        "first_name": "Ann",
        "email": "Ann@example.com",
        "username": "user1",
        "admin": True,
    }
