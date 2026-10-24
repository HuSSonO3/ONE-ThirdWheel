import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_column, one_of, uuid_pk

RUN_STATUSES = ("running", "succeeded", "failed")
PROPOSAL_KINDS = ("task", "status_change")
PROPOSAL_STATUSES = ("pending", "accepted", "modified", "rejected", "expired")
TOOL_CALL_STATUSES = ("executed", "denied", "failed", "stubbed")


class AiAgent(Base):
    """The AI principal. Not a user; never acts in a human's name."""

    __tablename__ = "ai_agent"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class AiRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (one_of("status", RUN_STATUSES),)

    id: Mapped[uuid.UUID] = uuid_pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_agent.id"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    from_event_id: Mapped[int] = mapped_column(BigInteger)
    to_event_id: Mapped[int] = mapped_column(BigInteger)
    started_at: Mapped[datetime] = now_column()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default="running")
    error: Mapped[str | None] = mapped_column(Text)


class AiProposal(Base):
    """A suggestion. Every one is kept, whatever its outcome, for evaluation."""

    __tablename__ = "ai_proposals"
    __table_args__ = (
        one_of("kind", PROPOSAL_KINDS),
        one_of("status", PROPOSAL_STATUSES),
        Index("ix_ai_proposals_conversation_status", "conversation_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_runs.id"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    applied_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now() + interval '7 days'")
    )
    created_at: Mapped[datetime] = now_column()


class AiToolCall(Base):
    __tablename__ = "ai_tool_calls"
    __table_args__ = (one_of("status", TOOL_CALL_STATUSES),)

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_runs.id"), index=True)
    tool_name: Mapped[str] = mapped_column(Text)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    scope_check: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = now_column()
