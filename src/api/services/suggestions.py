"""AI suggestions: created by the worker, decided by humans (spec 3.2, 3.3, 3.5).

The AI never creates tasks. `ServiceBackend.create_proposal` is the one write it gets (the
`Backend` protocol in ai/tools/base.py); accepting runs the normal task path with the accepting
human as the assigner.
"""

import uuid
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import config, events
from api.access import can_assign, can_see, is_member
from api.errors import conflict, invalid
from api.models import AiProposal, Conversation, Task, User
from api.schemas import contract as c
from api.services import notifications, tasks
from api.services.common import get_or_404, now
from api.services.conversations import require_member


class ServiceBackend:
    """What AI tools may do to the system, bound to one session (implements ai.tools.base.Backend)."""

    def __init__(self, db: Session):
        self.db = db

    def create_proposal(self, *, run_id: uuid.UUID, conversation_id: uuid.UUID,
                        kind: Literal["task", "status_change"], payload: dict[str, Any],
                        confidence: float | None) -> uuid.UUID:
        return create_proposal(self.db, run_id=run_id, conversation_id=conversation_id, kind=kind,
                               payload=payload, confidence=confidence).id


def create_proposal(db: Session, *, run_id: uuid.UUID | None, conversation_id: uuid.UUID,
                    kind: Literal["task", "status_change"], payload: dict[str, Any],
                    confidence: float | None) -> AiProposal:
    conv = get_or_404(db, Conversation, conversation_id, "Conversation")
    model = c.TaskProposal if kind == "task" else c.StatusChangeProposal
    try:
        proposal = model.model_validate(payload)
    except ValidationError as exc:
        raise invalid("payload", str(exc)) from exc
    data = proposal.model_dump(mode="json")
    if kind == "task":
        data["assignee_is_member"] = bool(proposal.assignee_id and is_member(db, proposal.assignee_id, conv))
    p = AiProposal(run_id=run_id, conversation_id=conv.id, kind=kind, payload=data, confidence=confidence,
                   expires_at=now() + config.SUGGESTION_TTL)
    db.add(p)
    db.flush()
    events.suggestion_created(db, p)
    if kind == "task" and proposal.assignee_id and data["assignee_is_member"]:
        notifications.notify(db, {proposal.assignee_id}, "suggestion", "suggestion", p.id)
    return p


def expire_due(db: Session) -> None:
    """Lazy expiry: pending suggestions past `expires_at` become `expired` on the next read or decision."""
    for p in db.scalars(select(AiProposal).where(AiProposal.status == "pending", AiProposal.expires_at < now())
                        .with_for_update(skip_locked=True)):
        p.status, p.decided_at = "expired", now()
        events.suggestion_decided(db, p)


def can_accept(db: Session, viewer: User, p: AiProposal) -> bool:
    """Whether Accept is enabled for this viewer: pending, a member, and the assignment rule holds (2.7)."""
    if p.status != "pending":
        return False
    conv = db.get(Conversation, p.conversation_id)
    if not is_member(db, viewer, conv):
        return False
    if p.kind == "status_change":
        task = db.get(Task, uuid.UUID(p.payload["task_id"]))
        return task is not None and can_see(db, viewer, task)
    assignee_id = p.payload.get("assignee_id")
    assignee = db.get(User, uuid.UUID(assignee_id)) if assignee_id else None
    return assignee is not None and can_assign(db, viewer, assignee, conv)


def for_conversation(db: Session, viewer: User, conv: Conversation, status: str | None) -> list[AiProposal]:
    require_member(db, viewer, conv)
    expire_due(db)
    q = select(AiProposal).where(AiProposal.conversation_id == conv.id)
    if status:
        q = q.where(AiProposal.status == status)
    return list(db.scalars(q.order_by(AiProposal.created_at.desc())))


def for_me(db: Session, viewer: User) -> list[AiProposal]:
    """Pending task suggestions proposing the viewer, in conversations they're a member of (3.2)."""
    expire_due(db)
    rows = db.scalars(select(AiProposal).where(
        AiProposal.status == "pending", AiProposal.kind == "task",
        AiProposal.payload["assignee_id"].astext == str(viewer.id),
    ).order_by(AiProposal.created_at.desc()))
    return [p for p in rows if is_member(db, viewer, db.get(Conversation, p.conversation_id))]


def _pending(db: Session, viewer: User, suggestion_id: uuid.UUID) -> tuple[AiProposal, Conversation]:
    expire_due(db)
    p = get_or_404(db, AiProposal, suggestion_id, "Suggestion", lock=True)
    conv = db.get(Conversation, p.conversation_id)
    require_member(db, viewer, conv)
    if p.status != "pending":
        raise conflict("already_decided", f"This suggestion was already {p.status}.")
    return p, conv


def _decide(db: Session, viewer: User, p: AiProposal, status: str, task: Task | None) -> None:
    p.status, p.decided_by, p.decided_at = status, viewer.id, now()
    p.applied_task_id = task.id if task else None
    db.flush()
    events.suggestion_decided(db, p)


def accept(db: Session, viewer: User, suggestion_id: uuid.UUID) -> tuple[AiProposal, Task]:
    p, conv = _pending(db, viewer, suggestion_id)
    if p.kind == "status_change":
        task = get_or_404(db, Task, uuid.UUID(p.payload["task_id"]), "Task")
        tasks.update_task(db, viewer, task, c.TaskUpdate(status=p.payload["new_status"]))
    else:
        if not p.payload.get("assignee_id"):
            raise invalid("assignee_id", "No assignee was proposed; use modify to pick one.")
        body = c.TaskCreate(title=p.payload["title"], description_md=p.payload.get("description_md") or "",
                            assignee_id=p.payload["assignee_id"], project=p.payload.get("project"),
                            due_at=p.payload.get("due_at"), source_message_ids=p.payload["source_message_ids"])
        task = tasks.create(db, viewer, conv, body, created_by_ai=True, suggestion_id=p.id)
    _decide(db, viewer, p, "accepted", task)
    return p, task


def modify(db: Session, viewer: User, suggestion_id: uuid.UUID, body: c.TaskCreate) -> tuple[AiProposal, Task]:
    p, conv = _pending(db, viewer, suggestion_id)
    if p.kind != "task":
        raise invalid("kind", "Only task suggestions can be modified.")
    if not body.source_message_ids:
        body = body.model_copy(update={"source_message_ids": p.payload["source_message_ids"]})
    task = tasks.create(db, viewer, conv, body, created_by_ai=True, suggestion_id=p.id)
    _decide(db, viewer, p, "modified", task)
    return p, task


def reject(db: Session, viewer: User, suggestion_id: uuid.UUID) -> AiProposal:
    p, _ = _pending(db, viewer, suggestion_id)
    _decide(db, viewer, p, "rejected", None)
    return p

