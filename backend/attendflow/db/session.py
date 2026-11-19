"""Engine and session factory."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str) -> Engine:
    # timezone=UTC on the connection: we only store "timestamp without time zone", so this
    # never shifts our wall-clock values, but it keeps any server-side now() predictable.
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
