from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api import config

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
# Module attribute on purpose: tests swap it for a factory bound to a rolled-back connection.
session_factory = sessionmaker(engine, expire_on_commit=False)
SessionLocal = session_factory  # used by scripts


def get_db() -> Iterator[Session]:
    """One request, one transaction. Real-time frames go out only after the commit succeeds."""
    from api import realtime

    db = session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    else:
        realtime.dispatch(db)
    finally:
        db.close()
