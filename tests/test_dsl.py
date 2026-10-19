import functools
import threading

import pytest

from factory_bot import FactoryError, _dsl, build, f, factory, trait


def test_f_outside_a_body_says_where_it_works():
    with pytest.raises(
        FactoryError, match=r"^f\.x = \.\.\. only works inside a @factory body$"
    ):
        f.x = 1


def test_trait_outside_a_body_says_where_it_works():
    with pytest.raises(
        FactoryError, match=r"^@trait def admin only works inside a @factory body$"
    ):

        @trait
        def admin():
            pass


def test_f_used_at_build_time_is_outside_any_body():
    @factory(dict)
    def user():
        f.name = lambda: setattr(f, "x", 1)

    with pytest.raises(FactoryError, match="only works inside a @factory body"):
        build("user")


def test_a_trait_inside_a_trait_is_rejected():
    message = r"^Factory 'user': @trait def b must be directly inside the factory, not inside trait 'a'$"
    with pytest.raises(FactoryError, match=message):

        @factory(dict)
        def user():
            @trait
            def a():
                @trait
                def b():
                    pass


def test_a_duplicate_trait_name_is_rejected():
    message = r"^Factory 'user': trait 'admin' is already defined \(test_dsl\.py:\d+\)$"
    with pytest.raises(FactoryError, match=message):

        @factory(dict)
        def user():
            @trait
            def admin():
                f.admin = True

            @trait
            def admin():  # noqa: F811
                f.role = "admin"


def test_a_child_may_redefine_its_parents_trait():
    @factory(dict)
    def user():
        @trait
        def admin():
            f.admin = True

        @factory
        def guest():
            @trait
            def admin():
                f.admin = False

    assert build("guest", "admin") == {"admin": False}


def test_a_body_that_raises_registers_nothing():
    with pytest.raises(RuntimeError):

        @factory(dict)
        def user():
            f.a = 1
            raise RuntimeError

    with pytest.raises(FactoryError, match="No factory named 'user'"):
        build("user")
    with pytest.raises(FactoryError, match="only works inside a @factory body"):
        f.x = 1


def test_an_old_style_body_shows_the_new_form():
    message = (
        r"^def user\(f\) takes no parameters: drop the parameter and import f"
        r" \(from factory_bot import f\), and write @trait instead of @f\.trait$"
    )
    with pytest.raises(FactoryError, match=message):

        @factory(dict)
        def user(f):
            pass


def test_an_old_style_bare_factory_shows_the_new_form():
    message = r"^def guest\(f\) takes no parameters: drop the parameter and import f"
    with pytest.raises(FactoryError, match=message):

        @factory(dict)
        def user():
            @factory
            def guest(f):
                pass

    with pytest.raises(FactoryError, match=r"^def admin\(f\) takes no parameters"):

        @factory
        def admin(f):
            pass


def test_a_generator_body_is_rejected():
    with pytest.raises(
        FactoryError,
        match=r"^def user must be a plain function: its body runs once, now$",
    ):

        @factory(dict)
        def user():
            yield


def test_an_async_generator_body_is_rejected():
    with pytest.raises(
        FactoryError,
        match=r"^def user must be a plain function: its body runs once, now$",
    ):

        @factory(dict)
        async def user():
            yield


def test_a_lambda_body_is_rejected():
    with pytest.raises(
        FactoryError,
        match=r"^@factory takes a def, not a lambda: the function's name names the factory$",
    ):
        factory(dict)(lambda: None)


def test_a_body_that_is_not_a_function_is_rejected():
    body = functools.partial(lambda: None)
    with pytest.raises(
        FactoryError, match=r"^@trait takes a def, not functools\.partial\("
    ):

        @factory(dict)
        def user():
            trait(body)


def test_defining_is_true_only_while_a_body_runs():
    seen = []

    @factory(dict)
    def user():
        seen.append(_dsl._defining())

    assert seen == [True]
    assert not _dsl._defining()


def test_threads_defining_factories_at_once_do_not_cross_talk():
    barrier = threading.Barrier(4)

    def define(i):
        def body():
            barrier.wait()
            for k in range(100):
                setattr(f, f"a{k}", i)

        body.__name__ = f"t{i}"
        factory(dict)(body)

    threads = [threading.Thread(target=define, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert [set(build(f"t{i}").values()) for i in range(4)] == [{0}, {1}, {2}, {3}]
