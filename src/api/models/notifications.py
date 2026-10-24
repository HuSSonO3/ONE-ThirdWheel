import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_column, one_of, uuid_pk

NOTIFICATION_TYPES = ("mention", "dm", "thread_reply", "task_assigned", "suggestion")
REF_TYPES = ("message", "task", "suggestion")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        one_of("type", NOTIFICATION_TYPES),
        one_of("ref_type", REF_TYPES),
        Index("ix_notifications_user_unread", "user_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(Text)
    ref_type: Mapped[str] = mapped_column(Text)
    ref_id: Mapped[uuid.UUID]
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now_column()
