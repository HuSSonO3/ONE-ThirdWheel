import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, create_engine

requires_db = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="needs DATABASE_URL (migrated Postgres)")


@pytest.fixture
def db() -> Iterator[Connection]:
    """A connection inside a transaction that is always rolled back."""
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        finally:
            tx.rollback()
    engine.dispose()
