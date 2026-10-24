"""Read cursors (spec 1.16), search (1.18) and access-checked embeds (1.15, 2.5)."""

import re
import uuid
from typing import Any

from sqlalchemy import exists, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api import realtime, serializers
from api.access import can_access, can_see, message_visible_clause
from api.errors import invalid
from api.models import ChannelReadCursor, Conversation, File, Message, Task, User
from api.services.common import now
from api.services.conversations import require_member

# ---------------------------------------------------------------- read cursors


def mark_read(db: Session, user: User, conv: Conversation, last_read_seq: int) -> ChannelReadCursor:
    """Cursors only move forward. The caller's other tabs hear about it."""
    require_member(db, user, conv)
    seq = min(last_read_seq, conv.last_seq)
    stmt = insert(ChannelReadCursor).values(user_id=user.id, conversation_id=conv.id, last_read_seq=seq,
                                            updated_at=now())
    db.execute(stmt.on_conflict_do_update(
        index_elements=["user_id", "conversation_id"],
        set_={"last_read_seq": func.greatest(ChannelReadCursor.last_read_seq, stmt.excluded.last_read_seq),
              "updated_at": stmt.excluded.updated_at}))
    cursor = db.get(ChannelReadCursor, (user.id, conv.id), populate_existing=True)
    realtime.push(db, [user.id], realtime.frame("read_cursor.updated", None, conv.id,
                                                {"last_read_seq": cursor.last_read_seq}))
    return cursor


def my_cursors(db: Session, user: User) -> list[ChannelReadCursor]:
    return list(db.scalars(select(ChannelReadCursor).where(ChannelReadCursor.user_id == user.id)))


# ---------------------------------------------------------------- search

def search(db: Session, user: User, q: str, author: uuid.UUID | None, conversation: uuid.UUID | None,
           has_file: bool | None, limit: int) -> list[dict[str, Any]]:
    query = func.websearch_to_tsquery("english", q)
    rank = func.ts_rank(Message.tsv, query).label("rank")
    headline = func.ts_headline("english", Message.body_md, query,
                                literal_column("'StartSel=**, StopSel=**, MaxFragments=2'")).label("headline")
    stmt = (select(Message, rank, headline)
            .where(Message.tsv.op("@@")(query), Message.deleted_at.is_(None), message_visible_clause(user))
            .order_by(rank.desc(), Message.created_at.desc()).limit(limit))
    if author:
        stmt = stmt.where(Message.author_id == author)
    if conversation:
        stmt = stmt.where(Message.conversation_id == conversation)
    if has_file is not None:
        attached = exists().where(File.message_id == Message.id)
        stmt = stmt.where(attached if has_file else ~attached)
    rows = db.execute(stmt).all()
    messages = serializers.messages(db, [r[0] for r in rows])
    refs = serializers.conversation_refs(db, {r[0].conversation_id for r in rows})
    return [{"message": m, "conversation": refs[r[0].conversation_id], "headline": r[2], "rank": float(r[1])}
            for m, r in zip(messages, rows, strict=True)]


# ---------------------------------------------------------------- embeds

UUID = r"([0-9a-fA-F-]{36})"
MESSAGE_LINK = re.compile(rf"/c/{UUID}/m/{UUID}/?$")
CHANNEL_LINK = re.compile(rf"/c/{UUID}/?$")
TASK_LINK = re.compile(rf"/t/{UUID}/?$")


def resolve_embed(db: Session, viewer: User, url: str) -> dict[str, Any]:
    """Resolve an internal link for the viewer (not the author). Every failed check is the same stub."""
    path = re.sub(r"^[a-z]+://[^/]+", "", url.strip()).split("?")[0].split("#")[0]
    forbidden = {"type": "forbidden"}
    not_found = {"type": "not_found"}
    try:
        if m := MESSAGE_LINK.search(path):
            message = db.get(Message, uuid.UUID(m.group(2)))
            if not message or message.conversation_id != uuid.UUID(m.group(1)) or message.deleted_at:
                return not_found
            conv = db.get(Conversation, message.conversation_id)
            if not can_access(db, viewer, conv, at=message.created_at):
                return forbidden
            author = db.get(User, message.author_id)
            return {"type": "message", "message": serializers.message(db, message),
                    "author": serializers.user_summary(author),
                    "conversation": serializers.conversation_refs(db, {conv.id})[conv.id]}
        if m := CHANNEL_LINK.search(path):
            conv = db.get(Conversation, uuid.UUID(m.group(1)))
            if not conv:
                return not_found
            if not can_access(db, viewer, conv):
                return forbidden
            return {"type": "channel", "conversation": serializers.conversation(db, viewer, conv)}
        if m := TASK_LINK.search(path):
            task = db.get(Task, uuid.UUID(m.group(1)))
            if not task:
                return not_found
            if not can_see(db, viewer, task):
                return forbidden
            return {"type": "task", "task": serializers.task(db, task)}
    except ValueError:
        return not_found
    raise invalid("url", "Not an internal message, channel or task link.")
