"""Tasks, the dashboard and projects (spec 2.2–2.4, 2.7)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import case, distinct, select, update
from sqlalchemy.orm import Session

from api import events
from api.access import can_assign, can_see, is_member, is_superior, task_visible_clause
from api.errors import forbidden, invalid
from api.models import Conversation, Message, Task, TaskHistory, TaskSource, User
from api.schemas import contract as c
from api.services import notifications
from api.services.common import get_or_404, now
from api.services.conversations import require_writable

OPEN_FIRST = case((Task.status.in_(("open", "in_progress")), 0), else_=1)


def _filtered(q, project: str | None, assignee: uuid.UUID | None, statuses: list[str] | None):
    if project:
        q = q.where(Task.project == project)
    if assignee:
        q = q.where(Task.assignee_id == assignee)
    if statuses:
        q = q.where(Task.status.in_(statuses))
    return q.order_by(OPEN_FIRST, Task.due_at.asc().nulls_last(), Task.created_at.desc())


def visible(db: Session, user: User, task_id: uuid.UUID) -> Task:
    task = get_or_404(db, Task, task_id, "Task")
    if not can_see(db, user, task):
        raise forbidden()
    return task


def for_conversation(db: Session, conv: Conversation, project: str | None, assignee: uuid.UUID | None,
                     statuses: list[str] | None) -> list[Task]:
    """Department channel: every task of every department member. Anything else: tasks spawned here (2.3)."""
    if conv.kind == "department":
        q = select(Task).join(User, User.id == Task.assignee_id).where(User.department_id == conv.department_id)
    else:
        q = select(Task).where(Task.source_conversation_id == conv.id)
    return list(db.scalars(_filtered(q, project, assignee, statuses)))


def for_user(db: Session, viewer: User, user_id: uuid.UUID, project: str | None,
             statuses: list[str] | None) -> list[Task]:
    """The personal dashboard (2.4): yours, or a subordinate's."""
    get_or_404(db, User, user_id, "User")
    if user_id != viewer.id and not is_superior(db, viewer, user_id):
        raise forbidden("You can only open your own dashboard or a subordinate's.")
    return list(db.scalars(_filtered(select(Task).where(Task.assignee_id == user_id), project, None, statuses)))


def projects(db: Session, user: User) -> list[str]:
    return list(db.scalars(select(distinct(Task.project)).where(Task.project.is_not(None), task_visible_clause(user))
                           .order_by(Task.project)))


def _assignee(db: Session, assignee_id: uuid.UUID) -> User:
    assignee = db.get(User, assignee_id)
    if not assignee or not assignee.active:
        raise invalid("assignee_id", "Unknown or inactive user.")
    return assignee


def _check_assign(db: Session, actor: User, assignee: User, conv: Conversation) -> None:
    if not is_member(db, actor, conv):
        raise forbidden("You're not a member of this conversation.", code="not_a_member")
    if not can_assign(db, actor, assignee, conv):
        raise forbidden(f"{assignee.name} isn't in this channel.", code="assignee_not_member")


def create(db: Session, actor: User, conv: Conversation, body: c.TaskCreate, *, created_by_ai: bool = False,
           suggestion_id: uuid.UUID | None = None) -> Task:
    require_writable(conv)
    assignee = _assignee(db, body.assignee_id)
    _check_assign(db, actor, assignee, conv)

    sources = []
    for message_id in dict.fromkeys(body.source_message_ids or []):
        m = db.get(Message, message_id)
        if not m or m.conversation_id != conv.id or m.deleted_at is not None:
            raise invalid("source_message_ids", "Source messages must be in this conversation.")
        sources.append(m)

    description = body.description_md or ""
    if sources and not is_member(db, assignee, conv):
        # Direct-manager exception: the assignee can't open the source, so the task carries its text (2.7).
        quoted = "\n\n".join("> " + m.body_md.replace("\n", "\n> ") for m in sources)
        description = f"{description}\n\n{quoted}".strip()

    task = Task(assignee_id=assignee.id, created_by=actor.id, created_by_ai=created_by_ai,
                source_conversation_id=conv.id, project=(body.project or None), title=body.title.strip(),
                description_md=description, priority=body.priority or "normal", due_at=body.due_at)
    db.add(task)
    db.flush()
    db.add_all([TaskSource(task_id=task.id, message_id=m.id) for m in sources])
    events.task_created(db, task, assignee, [m.id for m in sources], suggestion_id)
    if assignee.id != actor.id:
        notifications.notify(db, {assignee.id}, "task_assigned", "task", task.id)
    return task


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def update_task(db: Session, actor: User, task: Task, body: c.TaskUpdate) -> Task:
    if not can_see(db, actor, task):
        raise forbidden()
    changes: dict[str, list[Any]] = {}
    for field in sorted(body.model_fields_set):
        value = getattr(body, field)
        if field in ("title", "assignee_id", "status", "priority") and value is None:
            raise invalid(field, "Can't be empty.")
        if field == "title":
            value = value.strip()
        if field == "project":
            value = value or None
        if getattr(task, field) != value:
            changes[field] = [getattr(task, field), value]

    if "assignee_id" in changes:
        assignee = _assignee(db, changes["assignee_id"][1])
        _check_assign(db, actor, assignee, db.get(Conversation, task.source_conversation_id))
    if not changes:
        return task

    for field, (old, new) in changes.items():
        setattr(task, field, new)
        db.add(TaskHistory(task_id=task.id, actor_id=actor.id, field=field, old_value=_text(old),
                           new_value=_text(new)))
    if "status" in changes:
        task.completed_at = now() if task.status == "done" else None
    task.updated_at = now()
    db.flush()
    assignee = db.get(User, task.assignee_id)
    events.task_updated(db, task, assignee, actor, changes)
    if "assignee_id" in changes and assignee.id != actor.id:
        notifications.notify(db, {assignee.id}, "task_assigned", "task", task.id)
    return task


def history(db: Session, task: Task) -> list[TaskHistory]:
    return list(db.scalars(select(TaskHistory).where(TaskHistory.task_id == task.id)
                           .order_by(TaskHistory.changed_at, TaskHistory.id)))


def rename_project(db: Session, admin: User, old: str, new: str) -> int:
    rows = list(db.scalars(select(Task).where(Task.project == old)))
    if not rows or old == new:
        return 0
    db.execute(update(Task).where(Task.project == old).values(project=new, updated_at=now()))
    for task in rows:
        db.add(TaskHistory(task_id=task.id, actor_id=admin.id, field="project", old_value=old, new_value=new))
        events.task_updated(db, task, db.get(User, task.assignee_id), admin, {"project": [old, new]})
    return len(rows)
