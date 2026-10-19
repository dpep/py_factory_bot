import functools

from faker import Faker
from faker.generator import Generator

from ._core import FactoryError, _defining_factory

# Generator's own methods (format, parse, add_provider, ...) are helpers, not provider calls.
_HELPERS = frozenset(dir(Generator))


class _Fake(Faker):
    """Faker that refuses a provider call made while a factory body runs: it would freeze one value."""

    def __getattr__(self, attr):
        # Only reached for what Faker proxies to its Generator: provider methods and Generator
        # helpers. Faker's own members (unique, seed_instance, random, ...) are found first.
        value = super().__getattr__(attr)
        if callable(value) and attr not in _HELPERS and _defining_factory():
            return _guard(attr, value)
        return value

    # Faker's proxies call back into fake: guard them too, so the error names the call written.
    # Faker's stub doesn't declare them, hence the ignores.
    @property
    def unique(self):
        proxy = super().unique  # pyright: ignore[reportAttributeAccessIssue]
        return _Proxy(proxy, "unique") if _defining_factory() else proxy

    @property
    def optional(self):
        proxy = super().optional  # pyright: ignore[reportAttributeAccessIssue]
        return _Proxy(proxy, "optional") if _defining_factory() else proxy


class _Proxy:
    def __init__(self, proxy, prefix):
        self._proxy, self._prefix = proxy, prefix

    def __getattr__(self, attr):
        value = getattr(self._proxy, attr)
        if attr == "exclude_types":
            # Returns another UniqueProxy: guard it too, under the call as written.
            prefix = f"{self._prefix}.exclude_types(...)"
            return lambda *args, **kwargs: _Proxy(value(*args, **kwargs), prefix)
        if attr == "clear" or not callable(value):
            return value
        return _guard(f"{self._prefix}.{attr}", value)


def _guard(name, method):
    # wraps sets __wrapped__, so inspect.signature (and dependency injection) sees the provider's.
    @functools.wraps(method)
    def guarded(*args, **kwargs):
        if factory := _defining_factory():
            raise FactoryError(
                f"fake.{name}() was called while the factory was being defined,"
                " so every build would get the same value."
                f" Pass the method instead, without parentheses: fake.{name}"
                f" (or lambda: fake.{name}(...) for arguments)",
                factory=factory,
            )
        return method(*args, **kwargs)

    return guarded


fake: Faker = _Fake()


def seed(value: float | str | bytes | None) -> None:
    """Seed `fake` so a test's generated data is reproducible, `fake.unique` included."""
    fake.seed_instance(value)
    fake.unique.clear()  # its seen-values would otherwise make output depend on history
