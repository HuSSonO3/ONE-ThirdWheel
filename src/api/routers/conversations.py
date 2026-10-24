"""conversations, members, read cursors, and the per-conversation task and suggestion tabs."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from api import serializers
from api.auth import DB, CurrentUser
from api.models import Conversation
from api.schemas import contract as c
from api.services import conversations as convs
from api.services import reading, suggestions, tasks
from api.services.common import get_or_404

router = APIRouter()
Statuses = Annotated[list[Literal["open", "in_progress", "done", "cancelled"]] | None, Query()]
KIND_ORDER = {"department": 0, "channel": 1, "dm": 2}


def _sidebar_order(item: dict) -> tuple:
    if item["kind"] == "dm":  # DMs by recent activity
        last: datetime | None = item["last_message_at"] or item["created_at"]
        return (2, -last.timestamp(), "")
    return (KIND_ORDER[item["kind"]], 0, (item["name"] or "").lower())


@router.get("/conversations", response_model=list[c.Conversation], tags=["conversations"])
def list_conversations(user: CurrentUser, db: DB, scope: Literal["mine", "browse"] = "mine",
                       include_archived: bool = False):
    rows = convs.list_mine(db, user, include_archived) if scope == "mine" else convs.browse(db, user, include_archived)
    return sorted(serializers.conversations(db, user, rows), key=_sidebar_order)


@router.post("/conversations", response_model=c.Conversation, status_code=201, tags=["conversations"])
def create_conversation(body: c.ConversationCreate, response: Response, user: CurrentUser, db: DB):
    conv, created = convs.create(db, user, body)
    if not created:
        response.status_code = 200
    return serializers.conversation(db, user, conv)


@router.get("/conversations/{conversation_id}", response_model=c.Conversation, tags=["conversations"])
def get_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DB):
    return serializers.conversation(db, user, convs.readable(db, user, conversation_id))


@router.patch("/conversations/{conversation_id}", response_model=c.Conversation, tags=["conversations"])
def update_conversation(conversation_id: uuid.UUID, body: c.ConversationUpdate, user: CurrentUser, db: DB):
    conv = convs.update(db, user, convs.readable(db, user, conversation_id), body)
    return serializers.conversation(db, user, conv)


@router.post("/conversations/{conversation_id}/archive", response_model=c.Conversation, tags=["conversations"])
def archive_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DB):
    conv = convs.archive(db, user, convs.readable(db, user, conversation_id))
    return serializers.conversation(db, user, conv)


@router.post("/conversations/{conversation_id}/join", response_model=c.Member, tags=["members"])
def join_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DB):
    row = convs.join(db, user, get_or_404(db, Conversation, conversation_id, "Conversation"))
    return serializers.members(db, [row])[0]


@router.post("/conversations/{conversation_id}/leave", status_code=204, tags=["members"])
def leave_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    convs.leave(db, user, get_or_404(db, Conversation, conversation_id, "Conversation"))
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/members", response_model=list[c.Member], tags=["members"])
def list_members(conversation_id: uuid.UUID, user: CurrentUser, db: DB, include_former: bool = False):
    conv = convs.readable(db, user, conversation_id)
    return serializers.members(db, convs.members(db, conv, include_former))


@router.post("/conversations/{conversation_id}/members", response_model=list[c.Member], tags=["members"])
def add_members(conversation_id: uuid.UUID, body: c.AddMembersRequest, user: CurrentUser, db: DB):
    conv = convs.readable(db, user, conversation_id)
    return serializers.members(db, convs.invite(db, user, conv, body.user_ids))


@router.delete("/conversations/{conversation_id}/members/{user_id}", status_code=204, tags=["members"])
def remove_member(conversation_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    convs.remove(db, user, convs.readable(db, user, conversation_id), user_id)
    return Response(status_code=204)


@router.patch("/conversations/{conversation_id}/membership", response_model=c.Member, tags=["members"])
def update_my_membership(conversation_id: uuid.UUID, body: c.MembershipUpdate, user: CurrentUser, db: DB):
    conv = get_or_404(db, Conversation, conversation_id, "Conversation")
    return serializers.members(db, [convs.update_membership(db, user, conv, body)])[0]


@router.put("/conversations/{conversation_id}/read", response_model=c.ReadCursor, tags=["read-cursors"])
def mark_read(conversation_id: uuid.UUID, body: c.MarkReadRequest, user: CurrentUser, db: DB):
    cursor = reading.mark_read(db, user, get_or_404(db, Conversation, conversation_id, "Conversation"),
                               body.last_read_seq)
    return {"conversation_id": cursor.conversation_id, "last_read_seq": cursor.last_read_seq,
            "updated_at": cursor.updated_at}


@router.get("/conversations/{conversation_id}/tasks", response_model=list[c.Task], tags=["tasks"])
def list_conversation_tasks(conversation_id: uuid.UUID, user: CurrentUser, db: DB, project: str | None = None,
                            assignee: uuid.UUID | None = None, status: Statuses = None):
    conv = convs.readable(db, user, conversation_id)
    return serializers.tasks(db, tasks.for_conversation(db, conv, project, assignee, status))


@router.post("/conversations/{conversation_id}/tasks", response_model=c.Task, status_code=201, tags=["tasks"])
def create_task(conversation_id: uuid.UUID, body: c.TaskCreate, user: CurrentUser, db: DB):
    conv = get_or_404(db, Conversation, conversation_id, "Conversation")
    return serializers.task(db, tasks.create(db, user, conv, body))


@router.get("/conversations/{conversation_id}/suggestions", response_model=list[c.Suggestion],
            tags=["suggestions"])
def list_conversation_suggestions(conversation_id: uuid.UUID, user: CurrentUser, db: DB,
                                  status: Literal["pending", "accepted", "modified", "rejected", "expired"]
                                  | None = None):
    conv = get_or_404(db, Conversation, conversation_id, "Conversation")
    return serializers.suggestions(db, user, suggestions.for_conversation(db, user, conv, status))
