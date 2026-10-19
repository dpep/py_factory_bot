"""SQLAlchemy persistence: factory_bot.persist_with(persist_with(session))."""

# Duck-typed on purpose: importing this module never imports SQLAlchemy.

from collections.abc import Callable
from typing import Any

from ._core import FactoryError


def persist_with(session: Any) -> Callable[[object], None]:
    """A persist_with hook that adds each object to `session` and flushes, leaving commit or rollback to the caller."""
    if not (hasattr(session, "add") and hasattr(session, "flush")):
        raise FactoryError(
            "persist_with() takes a Session, not a factory of them."
            " Pass the test's session, e.g. persist_with(session)."
        )

    def persist(obj: object) -> None:
        session.add(obj)
        session.flush()

    return persist
