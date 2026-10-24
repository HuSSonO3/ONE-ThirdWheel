"""WebSocket fan-out and replay (spec 1.9, 1.17, 1.21). Contract: contracts/ws-events.md.

One process, in-memory: `user_id → connections`. Request threads call `dispatch` after their
transaction commits; frames are handed to each connection's event loop thread-safely and written
by that connection's writer task, so a socket never has two concurrent writers.
"""

import asyncio
import logging
import threading
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import serializers
from api.access import can_access
from api.models import (
    AiProposal,
    Conversation,
    ConversationMember,
    Event,
    File,
    Message,
    Task,
    User,
    UserClosure,
)

log = logging.getLogger(__name__)
REPLAY_LIMIT = 500
PRESENCE_GRACE_S = 10.0
# Events whose `data` object depends on who receives it.
PER_RECIPIENT = {"conversation.updated", "suggestion.created", "suggestion.decided"}


@dataclass(eq=False)
class Connection:
    user_id: uuid.UUID
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class Hub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conns: dict[uuid.UUID, set[Connection]] = defaultdict(set)
        self._grace: dict[uuid.UUID, asyncio.TimerHandle] = {}

    def connected(self) -> set[uuid.UUID]:
        with self._lock:
            return {u for u, conns in self._conns.items() if conns}

    def online(self) -> set[uuid.UUID]:
        with self._lock:
            return {u for u, conns in self._conns.items() if conns} | set(self._grace)

    def add(self, conn: Connection) -> bool:
        """Register a socket. True if the user just came online (not merely back within the grace period)."""
        with self._lock:
            handle = self._grace.pop(conn.user_id, None)
            if handle:
                handle.cancel()
            was_online = bool(self._conns[conn.user_id]) or handle is not None
            self._conns[conn.user_id].add(conn)
            return not was_online

    def remove(self, conn: Connection) -> None:
        """Unregister a socket; after the last one, announce offline once the grace period passes."""
        with self._lock:
            self._conns[conn.user_id].discard(conn)
            if self._conns[conn.user_id]:
                return
            self._grace[conn.user_id] = conn.loop.call_later(PRESENCE_GRACE_S, self._went_offline, conn.user_id)

    def _went_offline(self, user_id: uuid.UUID) -> None:
        with self._lock:
            if self._grace.pop(user_id, None) is None or self._conns[user_id]:
                return
        self.broadcast(frame("presence.changed", None, None, {"user_id": user_id, "online": False}))

    def send(self, user_ids: Iterable[uuid.UUID], message: dict[str, Any]) -> None:
        encoded = jsonable_encoder(message)
        with self._lock:
            targets = [c for u in set(user_ids) for c in self._conns.get(u, ())]
        for conn in targets:
            conn.loop.call_soon_threadsafe(conn.queue.put_nowait, encoded)

    def broadcast(self, message: dict[str, Any]) -> None:
        self.send(self.connected(), message)


hub = Hub()


def frame(type_: str, event_id: int | None, conversation_id: uuid.UUID | None, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": type_, "event_id": event_id, "conversation_id": conversation_id, "data": data}


def push(db: Session, user_ids: Iterable[uuid.UUID], message: dict[str, Any]) -> None:
    """Queue an ephemeral frame (notification, read cursor) to go out after this transaction commits."""
    db.info.setdefault("pending_frames", []).append((list(user_ids), message))


def dispatch(db: Session) -> None:
    """Fan out what the committed transaction queued. Never raises into the request."""
    event_ids = db.info.pop("pending_events", [])
    frames = db.info.pop("pending_frames", [])
    connected = hub.connected()
    if not connected or not (event_ids or frames):
        return
    try:
        for user_ids, message in frames:
            hub.send(user_ids, message)
        for event in db.scalars(select(Event).where(Event.id.in_(event_ids)).order_by(Event.id)):
            for user_id, message in deliveries(db, event, connected):
                hub.send([user_id], message)
    except Exception:
        log.exception("real-time dispatch failed")
    finally:
        db.rollback()


# ---------------------------------------------------------------- audiences and frames

def open_members(db: Session, conversation_id: uuid.UUID | None) -> set[uuid.UUID]:
    if conversation_id is None:
        return set()
    return set(db.scalars(select(ConversationMember.user_id).where(
        ConversationMember.conversation_id == conversation_id, ConversationMember.left_at.is_(None))))


def audience(db: Session, event: Event) -> set[uuid.UUID]:
    """Who receives an event live (contracts/events-row.md, "Who reads what")."""
    users = open_members(db, event.conversation_id)
    if event.type.startswith("member."):
        users.add(uuid.UUID(event.payload["user_id"]))
    if event.type.startswith("task."):
        assignee = uuid.UUID(event.payload["assignee_id"])
        users.add(assignee)
        users |= set(db.scalars(select(UserClosure.ancestor_id).where(
            UserClosure.descendant_id == assignee, UserClosure.depth > 0)))
        department = event.payload.get("assignee_department_id")
        if department:
            dept_conv = db.scalar(select(Conversation.id).where(
                Conversation.kind == "department", Conversation.department_id == uuid.UUID(department)))
            users |= open_members(db, dept_conv)
    return users


def _extra(db: Session, event: Event, viewer: User) -> dict[str, Any]:
    """The full contract object a client needs to render the event without a REST call."""
    t, subject = event.type, event.subject_id
    if t in ("message.created", "message.updated"):
        return {"message": serializers.message(db, db.get(Message, subject))}
    if t.startswith("reaction."):
        return {"reactions": serializers.reaction_summaries(db, [subject]).get(subject, [])}
    if t.startswith("member."):
        row = db.scalars(select(ConversationMember).where(
            ConversationMember.conversation_id == event.conversation_id, ConversationMember.user_id == subject,
        ).order_by(ConversationMember.joined_at.desc()).limit(1)).first()
        return {"member": serializers.members(db, [row])[0] if row else None,
                "member_count": len(open_members(db, event.conversation_id))}
    if t == "conversation.updated":
        return {"conversation": serializers.conversation(db, viewer, db.get(Conversation, subject))}
    if t.startswith("task."):
        return {"task": serializers.task(db, db.get(Task, subject))}
    if t.startswith("suggestion."):
        return {"suggestion": serializers.suggestion(db, viewer, db.get(AiProposal, subject))}
    if t == "file.uploaded":
        return {"file": serializers.file_meta(db.get(File, subject))}
    return {}


def _client_payload(db: Session, event: Event) -> dict[str, Any]:
    """The events row minus what clients must not get: edit history (AI-only) and text of deleted messages."""
    payload = {k: v for k, v in event.payload.items() if k != "prior_body_md"}
    if event.type in ("message.created", "message.updated"):
        m = db.get(Message, event.subject_id)
        if m is None or m.deleted_at is not None:
            payload.update(body_md="", mentions=[], refs=[])
    return payload


def frame_for(db: Session, event: Event, viewer: User, cache: dict[str, Any] | None = None) -> dict[str, Any]:
    if cache is not None and event.type not in PER_RECIPIENT:
        if "extra" not in cache:
            cache["extra"] = _extra(db, event, viewer)
        extra = cache["extra"]
    else:
        extra = _extra(db, event, viewer)
    return frame(event.type, event.id, event.conversation_id, {**_client_payload(db, event), **extra})


def deliveries(db: Session, event: Event, connected: set[uuid.UUID]) -> list[tuple[uuid.UUID, dict[str, Any]]]:
    targets = audience(db, event) & connected
    if not targets:
        return []
    cache: dict[str, Any] = {}
    viewers = db.scalars(select(User).where(User.id.in_(targets))).all()
    return [(v.id, frame_for(db, event, v, cache)) for v in viewers]


def replay(db: Session, viewer: User, cursors: dict[str, int | None]) -> list[dict[str, Any]]:
    """Frames for `subscribe`: events after each cursor, per accessible conversation, then `subscribed`."""
    frames, subscribed = [], []
    for raw_id, cursor in cursors.items():
        try:
            conversation = db.get(Conversation, uuid.UUID(raw_id))
        except ValueError:
            continue
        if not conversation or not can_access(db, viewer, conversation):
            continue  # inaccessible conversations are dropped silently
        subscribed.append(conversation.id)
        if cursor is None:
            continue
        events = db.scalars(select(Event).where(Event.conversation_id == conversation.id, Event.id > cursor)
                            .order_by(Event.id).limit(REPLAY_LIMIT + 1)).all()
        if len(events) > REPLAY_LIMIT:
            frames.append(frame("resync_required", None, conversation.id, {"reason": "gap_too_large"}))
            continue
        frames += [frame_for(db, e, viewer) for e in events]
    frames.append(frame("subscribed", None, None, {"conversation_ids": subscribed}))
    return frames


def max_event_id(db: Session) -> int:
    return db.scalar(select(func.coalesce(func.max(Event.id), 0))) or 0
