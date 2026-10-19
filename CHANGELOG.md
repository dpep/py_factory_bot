# Changelog

## Unreleased

- `create` builds and then saves: `obj.save()` by default, or a global hook set with `to_create(fn)`.
- `build_list` / `create_list` / `build_pair` / `create_pair`.
- `association("user", *traits, **overrides)` builds or creates another factory's object to match the parent; `attributes_for` leaves it out.
- `transient(value)` declares an input other attributes can depend on, kept out of the model and `attributes_for`.
- Breaking: factory and trait bodies take no parameters. Drop the `f` parameter, import it instead (`from factory_bot import f`), and write `@trait` instead of `@f.trait`. An old-style body raises an error showing the new form.
- Child factories: a bare `@factory` nested in a factory body inherits its model, attributes, traits and sequences; nest `@factory(Model)` to switch model.
- `@after_build` / `@after_create` callbacks get the instance first and other attributes, transients included, by parameter name. They run in definition order: parent, child, then traits.
- `@to_create` inside a factory body sets that factory's persistence hook, and children inherit it. At top level `to_create(fn)` is still the global hook.
- SQLAlchemy: `factory_bot.to_create(persist_with(session))` adds and flushes each created object without committing, so the test's transaction still decides. Takes a `Session` or `scoped_session`.
- pytest plugin, on by default: `fake` is reseeded before each test from the test's node id, so its data is the same alone, in the suite or in any order; with pytest-randomly, `--randomly-seed` drives it. Set `factory_bot_reset_sequences = true` to restart sequences per test. Disable with `-p no:factory_bot`.

## 0.0.1 - 2026-10-18

- Define factories with `@factory(Model)` and build them with `build` / `attributes_for`: static, lazy (dependencies injected by parameter name) and `sequence` attributes, traits, and a shared seedable `fake`. Faker is now a dependency.
