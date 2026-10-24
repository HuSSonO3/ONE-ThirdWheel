import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_column, one_of, uuid_pk

ROLES = ("admin", "member")


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = now_column()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (one_of("role", ROLES),)

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    # Source of truth for the hierarchy; user_closure is rebuilt from it by triggers.
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"), index=True)
    role: Mapped[str] = mapped_column(Text, server_default="member")
    avatar_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id", use_alter=True, ondelete="SET NULL")
    )
    timezone: Mapped[str] = mapped_column(Text, server_default="UTC")
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = now_column()


class UserClosure(Base):
    """Derived from users.manager_id by triggers. Application code never writes this table."""

    __tablename__ = "user_closure"

    ancestor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    descendant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    depth: Mapped[int] = mapped_column(Integer)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # opaque random token, the cookie value
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = now_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
