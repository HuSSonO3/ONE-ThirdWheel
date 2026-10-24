"""The `events` writer (spec 2.6). Shapes: contracts/events-row.md.

Every mutating service calls `record` in the same transaction as its primary write. The row is
also queued on the session so `realtime.dispatch` can fan it out once the transaction commits.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from api.models import AiProposal, File, Message, Task, User
from api.text import Mention, Ref


def _s(value: Any) -> Any:
    """JSON-safe payload values: UUIDs and datetimes as strings."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {k: _s(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_s(v) for v in value]
    return value


def record(db: Session, type_: str, *, conversation_id: uuid.UUID | None, actor_id: uuid.UUID | None,
           subject_type: str, subject_id: uuid.UUID, payload: dict[str, Any]) -> None:
    from api.models import Event

    event = Event(type=type_, conversation_id=conversation_id, actor_id=actor_id, subject_type=subject_type,
                  subject_id=subject_id, payload=_s(payload))
    db.add(event)
    db.flush()
    db.info.setdefault("pending_events", []).append(event.id)


# ---------------------------------------------------------------- one builder per type

def message_created(db: Session, m: Message, mentions: list[Mention], refs: list[Ref], file_ids: list[uuid.UUID]):
    record(db, "message.created", conversation_id=m.conversation_id, actor_id=m.author_id, subject_type="message",
           subject_id=m.id, payload={
               "message_id": m.id, "seq": m.seq, "parent_id": m.parent_id, "also_in_channel": m.also_in_channel,
               "author_id": m.author_id, "body_md": m.body_md, "mentions": mentions, "refs": refs,
               "file_ids": file_ids, "created_at": m.created_at,
           })


def message_updated(db: Session, m: Message, prior: str, mentions: list[Mention], refs: list[Ref]) -> None:
    record(db, "message.updated", conversation_id=m.conversation_id, actor_id=m.author_id, subject_type="message",
           subject_id=m.id, payload={
               "message_id": m.id, "seq": m.seq, "parent_id": m.parent_id, "body_md": m.body_md,
               "prior_body_md": prior, "mentions": mentions, "refs": refs, "edited_at": m.edited_at,
           })


def message_deleted(db: Session, m: Message, actor: User) -> None:
    record(db, "message.deleted", conversation_id=m.conversation_id, actor_id=actor.id, subject_type="message",
           subject_id=m.id, payload={"message_id": m.id, "seq": m.seq, "parent_id": m.parent_id,
                                     "deleted_at": m.deleted_at})


def reaction(db: Session, added: bool, m: Message, user: User, emoji: str) -> None:
    record(db, "reaction.added" if added else "reaction.removed", conversation_id=m.conversation_id,
           actor_id=user.id, subject_type="message", subject_id=m.id,
           payload={"message_id": m.id, "user_id": user.id, "emoji": emoji})


def member(db: Session, joined: bool, conversation_id: uuid.UUID, user_id: uuid.UUID, role: str, via: str,
           by: uuid.UUID | None) -> None:
    record(db, "member.joined" if joined else "member.left", conversation_id=conversation_id,
           actor_id=by or user_id, subject_type="user", subject_id=user_id,
           payload={"user_id": user_id, "role": role, "via": via, "by_user_id": by})


def conversation_updated(db: Session, conversation_id: uuid.UUID, actor_id: uuid.UUID | None,
                         changes: dict[str, list[Any]]) -> None:
    record(db, "conversation.updated", conversation_id=conversation_id, actor_id=actor_id,
           subject_type="conversation", subject_id=conversation_id, payload={"changes": changes})


def task_created(db: Session, t: Task, assignee: User, source_message_ids: list[uuid.UUID],
                 suggestion_id: uuid.UUID | None) -> None:
    record(db, "task.created", conversation_id=t.source_conversation_id, actor_id=t.created_by, subject_type="task",
           subject_id=t.id, payload={
               "task_id": t.id, "title": t.title, "description_md": t.description_md, "assignee_id": t.assignee_id,
               "assignee_department_id": assignee.department_id, "created_by": t.created_by,
               "created_by_ai": t.created_by_ai, "suggestion_id": suggestion_id, "project": t.project,
               "status": t.status, "priority": t.priority, "due_at": t.due_at,
               "source_conversation_id": t.source_conversation_id, "source_message_ids": source_message_ids,
           })


def task_updated(db: Session, t: Task, assignee: User, actor: User, changes: dict[str, list[Any]]) -> None:
    record(db, "task.updated", conversation_id=t.source_conversation_id, actor_id=actor.id, subject_type="task",
           subject_id=t.id, payload={
               "task_id": t.id, "assignee_id": t.assignee_id, "assignee_department_id": assignee.department_id,
               "status": t.status, "changes": changes,
           })


def file_uploaded(db: Session, f: File) -> None:
    record(db, "file.uploaded", conversation_id=f.conversation_id, actor_id=f.uploader_id, subject_type="file",
           subject_id=f.id, payload={
               "file_id": f.id, "message_id": f.message_id, "uploader_id": f.uploader_id, "kind": f.kind,
               "name": f.name, "mime": f.mime, "size": f.size, "language": f.language,
           })


def suggestion_created(db: Session, p: AiProposal) -> None:
    record(db, "suggestion.created", conversation_id=p.conversation_id, actor_id=None, subject_type="suggestion",
           subject_id=p.id, payload={"suggestion_id": p.id, "run_id": p.run_id, "kind": p.kind,
                                     "proposal": p.payload, "confidence": p.confidence})


def suggestion_decided(db: Session, p: AiProposal) -> None:
    record(db, "suggestion.decided", conversation_id=p.conversation_id, actor_id=p.decided_by,
           subject_type="suggestion", subject_id=p.id,
           payload={"suggestion_id": p.id, "status": p.status, "applied_task_id": p.applied_task_id})
