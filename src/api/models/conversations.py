import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_column, one_of, uuid_pk

KINDS = ("department", "channel", "dm")
MEMBER_ROLES = ("owner", "member")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        one_of("kind", KINDS),
        # One DM per user pair: member_key is the two user ids sorted and joined with ':'.
        Index("uq_conversations_dm_member_key", "member_key", unique=True, postgresql_where=text("kind = 'dm'")),
        Index(
            "uq_conversations_department",
            "department_id",
            unique=True,
            postgresql_where=text("kind = 'department'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    member_key: Mapped[str | None] = mapped_column(Text)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Allocator for messages.seq: UPDATE ... SET last_seq = last_seq + 1 RETURNING last_seq.
    last_seq: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now_column()


class ConversationMember(Base):
    """Rows are never deleted, only closed with left_at; a rejoin opens a new row."""

    __tablename__ = "conversation_members"
    __table_args__ = (
        one_of("role", MEMBER_ROLES),
        Index(
            "uq_conversation_members_open",
            "conversation_id",
            "user_id",
            unique=True,
            postgresql_where=text("left_at IS NULL"),
        ),
        Index("ix_conversation_members_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    joined_at: Mapped[datetime] = now_column()
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[str] = mapped_column(Text, server_default="member")
    muted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    ai_opt_in: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ChannelReadCursor(Base):
    __tablename__ = "channel_read_cursors"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    last_read_seq: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    updated_at: Mapped[datetime] = now_column()
