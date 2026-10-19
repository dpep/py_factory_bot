# Changelog

## Unreleased

- `create` builds and then saves: `obj.save()` by default, or a global hook set with `to_create(fn)`.
- `build_list` / `create_list` / `build_pair` / `create_pair`.
- `association("user", *traits, **overrides)` builds or creates another factory's object to match the parent; `attributes_for` leaves it out.
- `transient(value)` declares an input other attributes can depend on, kept out of the model and `attributes_for`.
- SQLAlchemy: `factory_bot.to_create(persist_with(session))` adds and flushes each created object without committing, so the test's transaction still decides. Takes a `Session` or `scoped_session`.

## 0.0.1 - 2026-10-18

- Define factories with `@factory(Model)` and build them with `build` / `attributes_for`: static, lazy (dependencies injected by parameter name) and `sequence` attributes, traits, and a shared seedable `fake`. Faker is now a dependency.
