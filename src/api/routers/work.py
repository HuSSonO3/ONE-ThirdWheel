"""tasks, suggestions, projects, embeds, search, notifications, read cursors, commands."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from api import serializers
from api.auth import DB, CurrentUser
from api.errors import not_found
from api.models import AiProposal, Conversation
from api.schemas import contract as c
from api.services import admin, notifications, reading, suggestions, tasks
from api.services.common import get_or_404
from api.services.conversations import require_member

router = APIRouter()


@router.get("/tasks/{task_id}", response_model=c.Task, tags=["tasks"])
def get_task(task_id: uuid.UUID, user: CurrentUser, db: DB):
    return serializers.task(db, tasks.visible(db, user, task_id))


@router.patch("/tasks/{task_id}", response_model=c.Task, tags=["tasks"])
def update_task(task_id: uuid.UUID, body: c.TaskUpdate, user: CurrentUser, db: DB):
    return serializers.task(db, tasks.update_task(db, user, tasks.visible(db, user, task_id), body))


@router.get("/tasks/{task_id}/history", response_model=list[c.TaskHistoryEntry], tags=["tasks"])
def get_task_history(task_id: uuid.UUID, user: CurrentUser, db: DB):
    return [{"actor_id": h.actor_id, "field": h.field, "old_value": h.old_value, "new_value": h.new_value,
             "changed_at": h.changed_at} for h in tasks.history(db, tasks.visible(db, user, task_id))]


@router.get("/projects", response_model=list[str], tags=["tasks"])
def list_projects(user: CurrentUser, db: DB):
    return tasks.projects(db, user)


@router.get("/me/suggestions", response_model=list[c.Suggestion], tags=["suggestions"])
def list_my_suggestions(user: CurrentUser, db: DB):
    return serializers.suggestions(db, user, suggestions.for_me(db, user))


def _decision(db, user, p: AiProposal, task) -> dict:
    return {"suggestion": serializers.suggestion(db, user, p), "task": serializers.task(db, task) if task else None}


@router.post("/suggestions/{suggestion_id}/accept", response_model=c.SuggestionDecision, tags=["suggestions"])
def accept_suggestion(suggestion_id: uuid.UUID, user: CurrentUser, db: DB):
    p, task = suggestions.accept(db, user, suggestion_id)
    return _decision(db, user, p, task)


@router.post("/suggestions/{suggestion_id}/modify", response_model=c.SuggestionDecision, tags=["suggestions"])
def modify_and_accept_suggestion(suggestion_id: uuid.UUID, body: c.TaskCreate, user: CurrentUser, db: DB):
    p, task = suggestions.modify(db, user, suggestion_id, body)
    return _decision(db, user, p, task)


@router.post("/suggestions/{suggestion_id}/reject", response_model=c.SuggestionDecision, tags=["suggestions"])
def reject_suggestion(suggestion_id: uuid.UUID, user: CurrentUser, db: DB):
    return _decision(db, user, suggestions.reject(db, user, suggestion_id), None)


@router.get("/embeds", response_model=c.Embed, tags=["embeds"])
def resolve_embed(url: str, user: CurrentUser, db: DB):
    return reading.resolve_embed(db, user, url)


@router.get("/search", response_model=list[c.SearchHit], tags=["search"])
def search(user: CurrentUser, db: DB, q: Annotated[str, Query(min_length=1)],
           from_: Annotated[uuid.UUID | None, Query(alias="from")] = None,
           in_: Annotated[uuid.UUID | None, Query(alias="in")] = None, has_file: bool | None = None,
           limit: Annotated[int, Query(ge=1, le=100)] = 30):
    return reading.search(db, user, q, from_, in_, has_file, limit)


@router.get("/me/read-cursors", response_model=list[c.ReadCursor], tags=["read-cursors"])
def list_my_read_cursors(user: CurrentUser, db: DB):
    return [{"conversation_id": r.conversation_id, "last_read_seq": r.last_read_seq, "updated_at": r.updated_at}
            for r in reading.my_cursors(db, user)]


@router.get("/notifications", response_model=list[c.Notification], tags=["notifications"])
def list_notifications(user: CurrentUser, db: DB, unread_only: bool = False,
                       limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return serializers.notifications(db, notifications.list_for(db, user, unread_only, limit))


@router.post("/notifications/{notification_id}/read", status_code=204, tags=["notifications"])
def mark_notification_read(notification_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    if not notifications.mark_read(db, user, notification_id):
        raise not_found("Notification")
    return Response(status_code=204)


@router.post("/notifications/read-all", status_code=204, tags=["notifications"])
def mark_all_notifications_read(user: CurrentUser, db: DB) -> Response:
    notifications.mark_all_read(db, user)
    return Response(status_code=204)


@router.post("/commands", response_model=c.CommandResult, tags=["commands"])
def run_command(body: c.CommandRequest, user: CurrentUser, db: DB):
    require_member(db, user, get_or_404(db, Conversation, body.conversation_id, "Conversation"))
    return admin.run_command(db, user, body.conversation_id, body.text)
