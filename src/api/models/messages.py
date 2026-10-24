import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Computed, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_column, one_of, uuid_pk

MENTION_KINDS = ("user", "department", "channel", "here")
REF_TARGETS = ("message", "channel", "task")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq"),
        # Idempotent send: a retried POST with the same client_id returns the existing row.
        UniqueConstraint("author_id", "client_id"),
        Index("ix_messages_parent_id", "parent_id"),
        Index("ix_messages_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    seq: Mapped[int] = mapped_column(BigInteger)
    body_md: Mapped[str] = mapped_column(Text)
    client_id: Mapped[uuid.UUID | None]
    reply_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now_column()
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', coalesce(body_md, ''))", persisted=True)
    )


class MessageEdit(Base):
    __tablename__ = "message_edits"

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    prior_body_md: Mapped[str] = mapped_column(Text)
    edited_at: Mapped[datetime] = now_column()


class MessageMention(Base):
    """kind=user sets user_id, kind=department sets department_id; channel/here expand at notify time."""

    __tablename__ = "message_mentions"
    __table_args__ = (one_of("kind", MENTION_KINDS), Index("ix_message_mentions_user_id", "user_id"))

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))


class MessageRef(Base):
    """Internal links found in a message body. target_id is polymorphic, so no FK."""

    __tablename__ = "message_refs"
    __table_args__ = (one_of("target_type", REF_TARGETS), Index("ix_message_refs_target", "target_type", "target_id"))

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[uuid.UUID]


class Reaction(Base):
    __tablename__ = "reactions"

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    emoji: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = now_column()
