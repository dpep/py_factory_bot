from dataclasses import dataclass

import pytest

from factory_bot import (
    FactoryError,
    build,
    f,
    factory,
    lint,
    sequence,
    to_create,
    trait,
)


@dataclass
class User:
    name: str
    admin: bool = False


def test_lint_passes_when_everything_builds():
    @factory(User)
    def user():
        f.name = "Ann"

        @trait
        def admin():
            f.admin = True

    lint()


def test_lint_reports_every_failing_build_as_a_call_to_reproduce():
    @factory(User)
    def user():
        f.name = "Ann"

        @trait
        def broken():
            f.nmae = "x"

        @factory
        def guest():
            f.email = lambda frist: frist

    @factory(dict)
    def post():
        f.title = "t"

    with pytest.raises(FactoryError) as info:
        lint()
    assert str(info.value) == (
        "lint: 3 of 5 builds failed:\n"
        "  build('user', 'broken'): TypeError: User.__init__() got an unexpected keyword argument 'nmae'\n"
        "  build('guest'): FactoryError: Factory 'guest': 'email' depends on 'frist', which is not defined. (test_lint.py:46)\n"
        "  build('guest', 'broken'): FactoryError: Factory 'guest': 'email' depends on 'frist', which is not defined. (test_lint.py:46)"
    )
    group = info.value.__cause__
    assert isinstance(group, ExceptionGroup)
    assert [e.__notes__[-1] for e in group.exceptions] == [
        "factory_bot.lint: build('user', 'broken')",
        "factory_bot.lint: build('guest')",
        "factory_bot.lint: build('guest', 'broken')",
    ]


def test_lint_without_traits_and_for_some_factories():
    @factory(User)
    def user():
        f.name = "Ann"

        @trait
        def broken():
            f.nmae = "x"

    @factory(dict)
    def post():
        f.title = lambda missing: missing

    lint(user, traits=False)
    with pytest.raises(FactoryError, match=r"^lint: 1 of 1 builds failed:"):
        lint("post")


def test_lint_create_saves_through_the_hook():
    saved = []
    to_create(saved.append)

    @factory(dict)
    def post():
        f.title = "t"

    lint(strategy="create")
    assert saved == [{"title": "t"}]


def test_lint_takes_build_or_create_only():
    with pytest.raises(
        FactoryError,
        match=r"^lint\(\) takes strategy='build' or 'create', not 'attributes_for'$",
    ):
        lint(strategy="attributes_for")  # pyright: ignore[reportArgumentType]


def test_lint_uses_up_sequence_numbers_like_any_build():
    @factory(dict)
    def post():
        f.n = sequence(lambda n: n)

    lint()
    assert build("post") == {"n": 2}
