# Changelog

## Unreleased

- `create` builds and then saves: `obj.save()` by default, or a global hook set with `to_create(fn)`.
- `build_list` / `create_list`.
- `association("user", *traits, **overrides)` builds or creates another factory's object to match the parent; `attributes_for` leaves it out.
- `transient(value)` declares an input other attributes can depend on, kept out of the model and `attributes_for`.
- Breaking: factory and trait bodies take no parameters. Drop the `f` parameter, import it instead (`from factory_bot import f`), and write `@trait` instead of `@f.trait`. An old-style body raises an error showing the new form.
- Child factories: a bare `@factory` nested in a factory body inherits its model, attributes, traits and sequences; nest `@factory(Model)` to switch model.
- `@after_build` / `@after_create` callbacks get the instance first and other attributes, transients included, by parameter name. They run in definition order: parent, child, then traits.
- SQLAlchemy: `factory_bot.to_create(persist_with(session))` adds and flushes each created object without committing, so the test's transaction still decides. Takes a `Session` or `scoped_session`.
- pytest plugin, on by default: `fake` is reseeded before each test from the test's node id, so its data is the same alone, in the suite or in any order (a module- or session-scoped fixture's data is not: it takes the seed of the first test that uses it); with pytest-randomly, `--randomly-seed` drives it. Set `factory_bot_reset_sequences = true` to restart sequences per test. Disable with `-p no:factory_bot`.
- `seed()` also forgets the values `fake.unique` has handed out, so the same seed gives the same data whatever ran before. Under the pytest plugin each test starts with a fresh unique pool, so a test no longer fails with `UniquenessException` depending on which tests ran first.
- A second trait with the same name in one factory is an error naming where the first is defined; it used to replace the first silently. A child may still redefine its parent's trait.
- Fix: each build gets its own copy of every list, dict, set and tuple, nested ones included, so `f.settings = {"roles": []}` no longer leaks between tests. Overrides are copied the same way, so the model holds a copy of a list you pass, not the list itself. Other objects are shared between builds: use a lambda for a fresh one.
- Fix: a `sequence(...)` passed as an override gives its next value instead of reaching the model as a raw object.
- Fix: a `sequence(...)` or `transient(...)` returned from a lazy attribute, as in `f.code = lambda: sequence(...)`, is an error naming the attribute, instead of reaching the model as a raw object. Assign the marker itself: `f.code = sequence(...)`. So is a marker inside a list, dict, set or tuple, as in `f.authors = [association("author")]`; for a list of associations, build it in a lambda: `lambda: [association("author")]`.
- Fix: a lazy attribute's positional-only parameters (`lambda name, /: ...`) are injected like the others.
- An exception from a model or a lazy attribute keeps its type and gains a note naming the factory, plus the attribute and its file:line. A model's unknown-keyword `TypeError` also suggests the factory attribute you probably meant.
- A `FactoryError` raised while a factory's body runs or while it builds names that factory, the innermost one when builds nest. `f.book = lambda: build("nope")` now says `Factory 'shelf': No factory named 'nope'.` Like other exceptions, it also gains a note from each build it passes through, so a failure deep in an association shows the attributes that led to it.
- `build(...)`, `create(...)` or `attributes_for(...)` called directly in a factory body is now an error: it ran once at definition time, so every build shared one object. Use `association("user")`, which builds or creates to match the parent, or wrap it in a lambda (`f.author = lambda: build("user")`).
- "Factory 'user' is already defined" shows the first definition's full path, and points at `clear_factories()` for redefining in a REPL or after a reload.
<!-- lane: r2-fake -->
- `fake.x()` inside a factory or trait body is now an error: it ran once, at definition, so every build got the same value. Drop the parentheses (`f.name = fake.first_name`), or wrap a call with arguments in a lambda. `fake.unique.x()` and `fake.optional.x()` are caught too; calls in lambdas, callbacks and at module level are unchanged.
- pytest plugin: a `to_create` hook set by a test or one of its function-scoped fixtures is undone after the test, so a fixture that sets it without teardown can no longer leak a closed session into later tests. A hook set at import (in a conftest) or by a session-, module- or class-scoped fixture stays: undo those in the fixture's own teardown.
<!-- /lane -->
<!-- lane: r2-core -->
- `@factory(User)` returns the factory itself, a `Factory[User]`. Pass it wherever a factory's name goes, `build(user)` or `association(user)`, and a type checker knows the result is a `User`; a name still works and gives `Any`. Nothing to change: calling the old return value never worked.
<!-- /lane -->

## 0.0.1 - 2026-10-18

- Define factories with `@factory(Model)` and build them with `build` / `attributes_for`: static, lazy (dependencies injected by parameter name) and `sequence` attributes, traits, and a shared seedable `fake`. Faker is now a dependency.
