"""GET /ws: one socket per tab (contracts/ws-events.md)."""

import asyncio
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool

from api import auth, realtime
from api import db as db_module
from api.access import is_member
from api.models import Conversation
from api.realtime import Connection, frame, hub

router = APIRouter()
TYPING_INTERVAL_S = 2.0
_last_typing: dict[tuple[uuid.UUID, uuid.UUID], float] = {}


def _handshake(token: str | None) -> tuple[uuid.UUID, int] | None:
    with db_module.session_factory() as db:
        user = auth.user_for_token(db, token)
        return (user.id, realtime.max_event_id(db)) if user else None


def _replay(user_id: uuid.UUID, cursors: dict[str, int | None]) -> list[dict[str, Any]]:
    from api.models import User

    with db_module.session_factory() as db:
        return jsonable_encoder(realtime.replay(db, db.get(User, user_id), cursors))


def _typing_targets(user_id: uuid.UUID, conversation_id: uuid.UUID) -> set[uuid.UUID]:
    with db_module.session_factory() as db:
        conv = db.get(Conversation, conversation_id)
        if not conv or not is_member(db, user_id, conv):
            return set()
        return realtime.open_members(db, conv.id) - {user_id}


@router.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    await ws.accept()
    found = await run_in_threadpool(_handshake, ws.cookies.get(auth.COOKIE))
    if not found:
        await ws.close(code=4401)
        return
    user_id, max_event_id = found
    conn = Connection(user_id=user_id, loop=asyncio.get_running_loop())
    came_online = hub.add(conn)
    writer = asyncio.create_task(_writer(ws, conn))
    conn.queue.put_nowait(jsonable_encoder(frame("hello", None, None, {
        "user_id": user_id, "online_user_ids": sorted(hub.online(), key=str),
        "server_time": datetime.now(UTC), "max_event_id": max_event_id,
    })))
    if came_online:
        hub.broadcast(frame("presence.changed", None, None, {"user_id": user_id, "online": True}))
    try:
        while True:
            message = await ws.receive_json()
            await _handle(conn, message)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.remove(conn)
        writer.cancel()
        with suppress(asyncio.CancelledError):
            await writer


async def _writer(ws: WebSocket, conn: Connection) -> None:
    while True:
        await ws.send_json(await conn.queue.get())


def _error(code: str, message: str) -> dict[str, Any]:
    return frame("error", None, None, {"code": code, "message": message})


async def _handle(conn: Connection, message: Any) -> None:
    kind = message.get("type") if isinstance(message, dict) else None
    if kind == "subscribe":
        cursors = message.get("conversations")
        if not isinstance(cursors, dict) or not all(v is None or isinstance(v, int) for v in cursors.values()):
            conn.queue.put_nowait(_error("validation_error", "conversations must map ids to an event id or null."))
            return
        for f in await run_in_threadpool(_replay, conn.user_id, cursors):
            conn.queue.put_nowait(f)
    elif kind == "typing":
        try:
            conversation_id = uuid.UUID(str(message.get("conversation_id")))
        except ValueError:
            conn.queue.put_nowait(_error("validation_error", "conversation_id must be a UUID."))
            return
        key, now = (conn.user_id, conversation_id), time.monotonic()
        if now - _last_typing.get(key, 0.0) < TYPING_INTERVAL_S:
            return
        _last_typing[key] = now
        targets = await run_in_threadpool(_typing_targets, conn.user_id, conversation_id)
        hub.send(targets, frame("typing", None, conversation_id,
                                {"user_id": conn.user_id, "parent_id": message.get("parent_id")}))
    else:
        conn.queue.put_nowait(_error("validation_error", "Unknown frame type."))
