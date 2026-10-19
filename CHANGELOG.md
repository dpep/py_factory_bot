# Changelog

## Unreleased

- `create` builds and then saves: `obj.save()` by default, or a global hook set with `to_create(fn)`.
- `build_list` / `create_list` / `build_pair` / `create_pair`.
- `association("user", *traits, **overrides)` builds or creates another factory's object to match the parent; `attributes_for` leaves it out.
- `transient(value)` declares an input other attributes can depend on, kept out of the model and `attributes_for`.

## 0.0.1 - 2026-10-18

- Define factories with `@factory(Model)` and build them with `build` / `attributes_for`: static, lazy (dependencies injected by parameter name) and `sequence` attributes, traits, and a shared seedable `fake`. Faker is now a dependency.
