# Changelog

## Unreleased

### What you must do

- Rewrite factory and trait bodies without the `f` parameter: `from factory_bot import f`, `def user():`, and `@trait` instead of `@f.trait`. Applies if you wrote factories for 0.0.1. An old-style body raises an error showing the new form.
- Write `lambda: SomeClass()` where you want a class, or another callable object that isn't a function, called per build. Applies if you assigned one as a value: only functions (defs, lambdas, methods, builtins like `datetime.now`, `functools.partial`) are called now, and every other object is stored, so `f.status = Status` gives the `Enum` class and `f.client = Mock()` gives that `Mock`.
<!-- lane: hunt2-plugin -->
- Drop the parentheses from `fake` calls in bodies (`f.name = fake.first_name`), or wrap a call that needs arguments in a lambda. Applies if a body calls `fake.x()`, `fake.random.x()`, `fake.parse()` or `fake.format()`: that gave every build the same value, and is now an error.
<!-- /lane -->
- Replace `build(...)` or `attributes_for(...)` called directly in a body with `association(...)`, or wrap it in a lambda. Applies if a body calls one: it ran once, at import, so every build shared one object. It's now an error, and so is `create(...)`.
- Rename or remove one of the two. Applies if a factory defines two traits with the same name: the second used to replace the first silently, and is now an error.
- Remove a `seed()` call made once for the whole run, or disable the plugin with `-p no:factory_bot`. Applies if you seed `fake` in a conftest: the new pytest plugin reseeds before every test.
- Install Django or SQLAlchemy yourself. Applies if you installed `factory_bot[django]` or `factory_bot[sqlalchemy]`: the extras are gone, since factory_bot never imports either.

### Added

- `create` builds, then saves: `obj.save()` by default. `persist_with(fn)` saves with a function instead, and `persist_with(session)` adds and flushes to a SQLAlchemy `Session` or `scoped_session`, never committing, so the test's transaction still decides. `persist_with(None)` restores `obj.save()`.
- `build_list` and `create_list`.
- `association(factory, *traits, **overrides)` makes another factory's object with the parent's strategy: built for `build`, created first for `create`. Called during a build, from a lambda or a callback, it makes the object right away, for associations that depend on other attributes or come in lists. `attributes_for` leaves associations out unless you pass them.
- Passing `<name>_id=` skips association `<name>` and still reaches the model, so `create("book", author_id=a.id)` makes no spare author. It applies only to an attribute declared as `association(...)`.
- `transient(value)` declares an input other attributes and callbacks can use, which never reaches the model or `attributes_for`.
- Child factories: `@factory(parent=user)` defines a child that inherits its parent's model, attributes, traits, sequences and callbacks, typed `Factory[User]`; `@factory(Admin, parent=user)` switches model. A bare `@factory` nested in a factory's body is shorthand for `parent=` that factory.
- `@after_build` and `@after_create` callbacks get the object first, then other attributes by name, transients included. They run parent first, then child, then traits.
<!-- lane: hunt2-plugin -->
- `@factory(User)` returns a `Factory[User]`. Pass it wherever a name goes, as in `build(user)` or `association(user)`, and a type checker knows the result is a `User`. Names still work and give `Any`. Assigning one as a value, `f.author = user`, is an error suggesting `association(user)`.
<!-- /lane -->
- A sequence's function gets the counter first, then other attributes by name: `sequence(lambda n, title: f"{slugify(title)}-{n}")`.
- `lint()` builds every factory once, then once with each trait, and raises one error listing every call that failed, ready to paste into a test.
<!-- lane: hunt2-plugin -->
- A pytest plugin, on by default. It reseeds `fake` before each test from the test's id, and for each fixture from its name, its param and the test, module or session it belongs to, so every test and fixture gets the same fake data alone, in the suite, in any order or under pytest-xdist; with pytest-randomly, `--randomly-seed` drives it. A fixture that calls `seed()` keeps that seed. A `persist_with` set by a test or a fixture of any scope is undone when that test or fixture ends. `factory_bot_reset_sequences = true` restarts sequences per test. The report header shows the seed and whether sequences reset: `factory_bot: seed=0, reset_sequences=off`. Disable it with `-p no:factory_bot`.
<!-- /lane -->

### Changed

- Every list, dict, set and tuple written in a body, nested ones included, is copied per build, so `f.settings = {"roles": []}` no longer leaks between tests. Anything you pass at build time is used exactly as given.
- A `sequence` passed as an override is evaluated, not passed to the model as a raw object; so are the new `association` and `transient`.
- A `sequence` inside a container, or returned from a lambda, is an error naming the attribute, instead of reaching the model unevaluated.
- An `async def` as an attribute, a sequence's function or a callback is an error, instead of handing the model an un-awaited coroutine.
- `seed()` also clears `fake.unique`, so the same seed gives the same data whatever ran before.
- A lazy attribute's positional-only parameters are injected like the others.
- Errors say where they happened. A `FactoryError` names the factory, the innermost when builds nest. An exception from a model, lambda or callback keeps its type and gains notes naming the factory and attribute with its file:line. A model's unknown-keyword `TypeError` suggests the attribute you probably meant.
- "Factory 'user' is already defined" shows the first definition's full path and suggests `clear_factories()` for a REPL or a reload.
- Reading `f.x` raises an `AttributeError` too, so `hasattr(f, ...)`, `inspect.unwrap` and doctest work.
- A one-parameter function, `def make_point(x)`, can be a model; only a lone parameter named `f` is read as an old-style body.

## 0.0.1 - 2026-10-18

- Define factories with `@factory(Model)` and build them with `build` / `attributes_for`: static, lazy (dependencies injected by parameter name) and `sequence` attributes, traits, and a shared seedable `fake`. Faker is now a dependency.
