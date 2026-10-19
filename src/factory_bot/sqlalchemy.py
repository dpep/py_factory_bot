"""SQLAlchemy persistence: factory_bot.to_create(persist_with(session))."""

# Duck-typed on purpose: importing this module never imports SQLAlchemy.


def persist_with(session):
    """A to_create hook that adds each object to `session` and flushes, leaving commit or rollback to the caller."""
    if not (hasattr(session, "add") and hasattr(session, "flush")):
        raise TypeError(
            "persist_with() takes a Session, not a factory of them."
            " Pass the test's session, e.g. persist_with(session)."
        )

    def persist(obj):
        session.add(obj)
        session.flush()

    return persist
