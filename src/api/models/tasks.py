import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_column, one_of, uuid_pk

STATUSES = ("open", "in_progress", "done", "cancelled")
PRIORITIES = ("low", "normal", "high", "urgent")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (one_of("status", STATUSES), one_of("priority", PRIORITIES))

    id: Mapped[uuid.UUID] = uuid_pk()
    assignee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_by_ai: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    source_conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    project: Mapped[str | None] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text)
    description_md: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[str] = mapped_column(Text, server_default="open", index=True)
    priority: Mapped[str] = mapped_column(Text, server_default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now_column()
    updated_at: Mapped[datetime] = now_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskSource(Base):
    __tablename__ = "task_sources"

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), primary_key=True, index=True)


class TaskHistory(Base):
    __tablename__ = "task_history"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    field: Mapped[str] = mapped_column(Text)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = now_column()
