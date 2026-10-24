"""Slash commands (spec 1.20) and the AI admin page (3.4, 3.5)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import serializers
from api.errors import invalid
from api.models import AiAgent, AiRun, AiToolCall, Conversation, User
from api.schemas import contract as c
from api.services import conversations, tasks
from api.services.common import get_or_404
from api.text import extract, strip_mentions

ALL_SCOPES = ["conversations:read", "suggestions:create", "suggestions:status", "leave:request", "claims:submit",
              "calendar:create"]


# ---------------------------------------------------------------- slash commands

def run_command(db: Session, user: User, conversation_id: uuid.UUID, text: str) -> dict[str, Any]:
    conv = get_or_404(db, Conversation, conversation_id, "Conversation")
    name, _, rest = text.strip().partition(" ")
    mentioned = [uuid.UUID(m["user_id"]) for m in extract(rest)[0] if m["user_id"]]
    if name == "/task":
        title = strip_mentions(rest)
        if not title:
            raise invalid("text", "Usage: /task <title> [@person]")
        task = tasks.create(db, user, conv, c.TaskCreate(title=title, assignee_id=mentioned[0] if mentioned
                                                         else user.id))
        return {"command": "task", "message": f"Task created: {task.title}", "task": serializers.task(db, task)}
    if name == "/invite":
        if not mentioned:
            raise invalid("text", "Usage: /invite @person …")
        conversations.invite(db, user, conv, mentioned)
        return {"command": "invite", "message": f"Invited {len(mentioned)} people.", "task": None}
    if name == "/leave":
        conversations.leave(db, user, conv)
        return {"command": "leave", "message": f"You left #{conv.name}.", "task": None}
    raise invalid("text", f"Unknown command {name}. Try /task, /invite or /leave.")


# ---------------------------------------------------------------- AI configuration and audit

def agent(db: Session) -> AiAgent:
    return db.scalar(select(AiAgent).order_by(AiAgent.name).limit(1))


def ai_config(db: Session) -> dict[str, Any]:
    a = agent(db)
    return {"id": a.id, "name": a.name, "active": a.active, "scopes": list(a.scopes),
            "available_scopes": ALL_SCOPES}


def update_ai(db: Session, scopes: list[str] | None, active: bool | None) -> dict[str, Any]:
    a = agent(db)
    if scopes is not None:
        a.scopes = list(dict.fromkeys(scopes))
    if active is not None:
        a.active = active
    db.flush()
    return ai_config(db)


def runs(db: Session, conversation_id: uuid.UUID | None, limit: int, before: datetime | None) -> list[AiRun]:
    q = select(AiRun)
    if conversation_id:
        q = q.where(AiRun.conversation_id == conversation_id)
    if before:
        q = q.where(AiRun.started_at < before)
    return list(db.scalars(q.order_by(AiRun.started_at.desc()).limit(limit)))


def tool_calls(db: Session, run_id: uuid.UUID | None, tool_name: str | None, status: str | None, limit: int,
               before: datetime | None) -> list[AiToolCall]:
    q = select(AiToolCall)
    if run_id:
        q = q.where(AiToolCall.run_id == run_id)
    if tool_name:
        q = q.where(AiToolCall.tool_name == tool_name)
    if status:
        q = q.where(AiToolCall.status == status)
    if before:
        q = q.where(AiToolCall.created_at < before)
    return list(db.scalars(q.order_by(AiToolCall.created_at.desc()).limit(limit)))


def admin_conversations(db: Session) -> list[Conversation]:
    return list(db.scalars(select(Conversation).where(Conversation.kind != "dm")
                           .order_by(Conversation.kind, Conversation.name)))
