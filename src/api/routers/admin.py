"""admin: AI configuration, per-conversation switch, audit log, project rename (spec 2.2, 3.4, 3.5)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from api import serializers
from api.auth import DB, Admin
from api.models import Conversation
from api.schemas import contract as c
from api.services import admin, tasks
from api.services import conversations as convs
from api.services.common import get_or_404

router = APIRouter(prefix="/admin", tags=["admin"])
Limit = Annotated[int, Query(ge=1, le=200)]


@router.get("/ai", response_model=c.AiConfig)
def get_ai_config(user: Admin, db: DB):
    return admin.ai_config(db)


@router.patch("/ai", response_model=c.AiConfig)
def update_ai_config(body: c.AiConfigUpdate, user: Admin, db: DB):
    return admin.update_ai(db, body.scopes, body.active)


@router.get("/conversations", response_model=list[c.Conversation])
def admin_list_conversations(user: Admin, db: DB):
    return serializers.conversations(db, user, admin.admin_conversations(db))


@router.patch("/conversations/{conversation_id}/ai", response_model=c.Conversation)
def set_conversation_ai(conversation_id: uuid.UUID, body: c.ConversationAiUpdate, user: Admin, db: DB):
    conv = convs.set_ai_enabled(db, user, get_or_404(db, Conversation, conversation_id, "Conversation"),
                                body.ai_enabled)
    return serializers.conversation(db, user, conv)


@router.get("/ai/runs", response_model=list[c.AiRun])
def list_ai_runs(user: Admin, db: DB, conversation_id: uuid.UUID | None = None, limit: Limit = 50,
                 before: datetime | None = None):
    return serializers.ai_runs(db, admin.runs(db, conversation_id, limit, before))


@router.get("/ai/tool-calls", response_model=list[c.AiToolCall])
def list_ai_tool_calls(user: Admin, db: DB, run_id: uuid.UUID | None = None, tool_name: str | None = None,
                       status: Literal["executed", "denied", "failed", "stubbed"] | None = None, limit: Limit = 50,
                       before: datetime | None = None):
    return serializers.tool_calls(admin.tool_calls(db, run_id, tool_name, status, limit, before))


@router.post("/projects/rename", response_model=c.ProjectRenameResult)
def rename_project(body: c.ProjectRename, user: Admin, db: DB):
    return {"updated": tasks.rename_project(db, user, body.from_, body.to)}
