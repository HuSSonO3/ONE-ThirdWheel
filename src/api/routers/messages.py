"""messages, threads, reactions, files (spec 1.7, 1.8, 1.12–1.14)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse

from api import serializers
from api.auth import DB, CurrentUser
from api.errors import not_found
from api.models import Conversation
from api.schemas import contract as c
from api.serializers import thumbnail_path
from api.services import conversations as convs
from api.services import files, messages
from api.services.common import get_or_404

router = APIRouter()


@router.get("/conversations/{conversation_id}/messages", response_model=c.MessagePage, tags=["messages"])
def list_messages(conversation_id: uuid.UUID, user: CurrentUser, db: DB, before_seq: int | None = None,
                  after_seq: int | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50):
    conv = convs.readable(db, user, conversation_id)
    rows, has_more = messages.page(db, conv, before_seq, after_seq, limit)
    return {"items": serializers.messages(db, rows), "has_more": has_more}


@router.post("/conversations/{conversation_id}/messages", response_model=c.Message, status_code=201,
             tags=["messages"])
def create_message(conversation_id: uuid.UUID, body: c.MessageCreate, response: Response, user: CurrentUser, db: DB):
    conv = get_or_404(db, Conversation, conversation_id, "Conversation")
    m, created = messages.create(db, user, conv, body)
    if not created:
        response.status_code = 200
    return serializers.message(db, m)


@router.get("/messages/{message_id}", response_model=c.Message, tags=["messages"])
def get_message(message_id: uuid.UUID, user: CurrentUser, db: DB):
    return serializers.message(db, messages.readable_message(db, user, message_id))


@router.patch("/messages/{message_id}", response_model=c.Message, tags=["messages"])
def edit_message(message_id: uuid.UUID, body: c.MessageUpdate, user: CurrentUser, db: DB):
    m = messages.readable_message(db, user, message_id)
    return serializers.message(db, messages.edit(db, user, m, body))


@router.delete("/messages/{message_id}", status_code=204, tags=["messages"])
def delete_message(message_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    messages.remove(db, user, messages.readable_message(db, user, message_id))
    return Response(status_code=204)


@router.get("/messages/{message_id}/thread", response_model=c.Thread, tags=["messages"])
def get_thread(message_id: uuid.UUID, user: CurrentUser, db: DB):
    parent, replies = messages.thread(db, user, message_id)
    rendered = serializers.messages(db, [parent, *replies])
    return {"parent": rendered[0], "replies": rendered[1:]}


@router.put("/messages/{message_id}/reactions/{emoji}", response_model=list[c.ReactionSummary], tags=["reactions"])
def add_reaction(message_id: uuid.UUID, emoji: str, user: CurrentUser, db: DB):
    m = messages.readable_message(db, user, message_id)
    messages.react(db, user, m, emoji, add=True)
    return serializers.reaction_summaries(db, [m.id]).get(m.id, [])


@router.delete("/messages/{message_id}/reactions/{emoji}", response_model=list[c.ReactionSummary],
               tags=["reactions"])
def remove_reaction(message_id: uuid.UUID, emoji: str, user: CurrentUser, db: DB):
    m = messages.readable_message(db, user, message_id)
    messages.react(db, user, m, emoji, add=False)
    return serializers.reaction_summaries(db, [m.id]).get(m.id, [])


@router.post("/files", response_model=c.FileMeta, status_code=201, tags=["files"])
def upload_file(file: UploadFile, user: CurrentUser, db: DB,
                conversation_id: Annotated[uuid.UUID | None, Form()] = None,
                kind: Annotated[Literal["file", "image", "snippet", "avatar"], Form()] = "file",
                name: Annotated[str | None, Form()] = None, language: Annotated[str | None, Form()] = None):
    return serializers.file_meta(files.upload(db, user, file, conversation_id, kind, name, language))


@router.get("/files/{file_id}", tags=["files"], response_class=FileResponse)
def download_file(file_id: uuid.UUID, user: CurrentUser, db: DB, thumbnail: bool = False):
    f = files.readable(db, user, file_id)
    if thumbnail:
        if not thumbnail_path(f.id).exists():
            raise not_found("Thumbnail")
        return FileResponse(thumbnail_path(f.id), media_type="image/png")
    return FileResponse(files.path_of(f), media_type=f.mime, filename=f.name)


@router.get("/files/{file_id}/meta", response_model=c.FileMeta, tags=["files"])
def get_file_meta(file_id: uuid.UUID, user: CurrentUser, db: DB):
    return serializers.file_meta(files.readable(db, user, file_id))


@router.get("/files/{file_id}/preview", response_model=c.SnippetPreview, tags=["files"])
def get_snippet_preview(file_id: uuid.UUID, user: CurrentUser, db: DB,
                        lines: Annotated[int, Query(ge=1, le=200)] = 20):
    f = files.readable(db, user, file_id)
    text, truncated = files.preview(f, lines)
    return {"text": text, "truncated": truncated, "language": f.language}
