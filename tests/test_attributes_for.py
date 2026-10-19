from support.models import User

from factory_bot import association, attributes_for, f, factory, sequence, trait


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


def test_attributes_for_keeps_an_override_of_an_association():
    @factory(User)
    def user():
        pass

    @factory(dict)
    def post():
        f.title = "Hi"
        f.author = association("user")

    assert attributes_for("post", author=7) == {"title": "Hi", "author": 7}


def test_attributes_for_keeps_any_association_passed_and_omits_only_declared_ones():
    @factory(dict)
    def account():
        f.plan = "free"

    @factory(dict)
    def task():
        f.title = "t"
        f.account = association("account")
        f.owner = association("account")

    assert attributes_for(
        "task",
        account=association("account", plan="pro"),
        reviewer=association("account"),
    ) == {"title": "t", "account": {"plan": "pro"}, "reviewer": {"plan": "free"}}
