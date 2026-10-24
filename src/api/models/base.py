import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, MetaData, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Fetch server defaults (ids, timestamps, now()) with RETURNING on insert.
    __mapper_args__ = {"eager_defaults": True}

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))


def now_column() -> Mapped[datetime]:
    # Python default for ORM inserts (wall-clock time, distinct per request even inside one transaction);
    # the server default covers raw SQL.
    return mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now())


def one_of(column: str, values: Iterable[str]) -> CheckConstraint:
    """Enums are text + CHECK (contracts/DECISIONS.md), so adding a value is a one-line migration."""
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=column)
