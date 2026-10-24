"""Read adapters. Writes to product tables are exclusively api.services.suggestions."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.context import Context, event_messages
from api.access import is_member
from api.events import _s
from api.models import AiProposal, Conversation, Department, Event, Message, Task, TaskSource, User


def event_dict(event: Event) -> dict:
    return {"id": event.id, "type": event.type, "actor_id": str(event.actor_id) if event.actor_id else None,
            "created_at": event.created_at.isoformat(), "payload": event.payload}


def assemble(db: Session, conversation: Conversation, batch: list[Event]) -> Context:
    history = list(db.scalars(select(Event).where(
        Event.conversation_id == conversation.id, Event.id <= batch[-1].id,
        Event.type.in_(["message.created", "message.updated", "message.deleted"]),
    ).order_by(Event.id)))
    # Include triggering messages and their threads, even outside the recent window.
    snapshots = event_messages([event_dict(e) for e in history], limit=len(history))
    new_ids = {str(e.subject_id) for e in batch if e.subject_type == "message"}
    roots = {m.get("parent_id") or m["message_id"] for m in snapshots if m["message_id"] in new_ids}
    selected = {m["message_id"]: m for m in snapshots[-30:]}
    selected.update({m["message_id"]: m for m in snapshots
                     if m["message_id"] in new_ids | roots or m.get("parent_id") in roots})
    # Deleted content must not be sent even during historical replay.
    deleted = {str(i) for i in db.scalars(select(Message.id).where(
        Message.conversation_id == conversation.id, Message.deleted_at.is_not(None)))}
    messages = [m for i, m in selected.items() if i not in deleted]
    tasks = []
    for task in db.scalars(select(Task).where(Task.source_conversation_id == conversation.id,
                                             Task.status.in_(["open", "in_progress"]))):
        sources = db.scalars(select(TaskSource.message_id).where(TaskSource.task_id == task.id))
        tasks.append({"task_id": str(task.id), "title": task.title, "status": task.status,
                      "assignee_id": str(task.assignee_id), "project": task.project,
                      "source_message_ids": [str(i) for i in sources]})
    proposals = [{"kind": p.kind, "payload": p.payload} for p in db.scalars(select(AiProposal).where(
        AiProposal.conversation_id == conversation.id, AiProposal.status == "pending",
        AiProposal.expires_at > datetime.now(UTC),
    ))]
    # Directory fields only: never include email, credentials, or unrelated conversation data.
    users = [{"id": str(u.id), "name": u.name, "job_title": u.job_title,
              "department_id": str(u.department_id) if u.department_id else None,
              "manager_id": str(u.manager_id) if u.manager_id else None,
              "timezone": u.timezone, "is_member": is_member(db, u, conversation)}
             for u in db.scalars(select(User).where(User.active))]
    # Only projects visible within this conversation are considered; no cross-channel task leakage.
    projects = list(db.scalars(select(Task.project).where(
        Task.source_conversation_id == conversation.id, Task.project.is_not(None)).distinct()))
    return Context(
        {"id": str(conversation.id), "kind": conversation.kind, "description": conversation.description or ""},
        [event_dict(e) for e in batch if str(e.subject_id) not in deleted],
        _s(messages), users, tasks, proposals, projects,
        [{"id": str(d.id), "name": d.name} for d in db.scalars(select(Department))],
    )


class RecordingBackend:
    def __init__(self):
        self.calls: list[dict] = []

    def create_proposal(self, **kwargs) -> uuid.UUID:
        self.calls.append(kwargs)
        return uuid.uuid4()
