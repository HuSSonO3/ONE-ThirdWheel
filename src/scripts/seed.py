"""Load src/fixtures/*.json into Postgres (plan.md §3 Day 3).

    DATABASE_URL=... python scripts/seed.py [--reset] [--ai-from-start]

Runs in one transaction. Refuses to load into a non-empty database unless --reset, which truncates
every data table first (the AI agent row and consumer cursors are kept, the cursor is rewound).
Besides the fixture rows it writes the `events` log for the seeded history, in time order, so WS
replay and the AI have something to read. By default the AI cursor is set to the end of that log so
the worker reacts only to new activity; --ai-from-start leaves it at 0 to replay everything.
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from sqlalchemy import Connection, Table, func, insert, select, text, update

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.db import engine  # noqa: E402
from api.models import (  # noqa: E402
    AiProposal,
    Base,
    ChannelReadCursor,
    Conversation,
    ConversationMember,
    Department,
    Event,
    EventConsumer,
    File,
    Message,
    MessageEdit,
    MessageMention,
    MessageRef,
    Notification,
    Reaction,
    Task,
    TaskHistory,
    TaskSource,
    User,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FILES_DIR = Path(os.environ.get("FILES_DIR", Path(__file__).resolve().parent.parent / ".data" / "files"))
PASSWORD = "password123"  # every fixture user; documented in fixtures/README.md
KEEP = {"ai_agent", "event_consumers", "alembic_version"}


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def rows(table: Table, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only real columns and parse timestamps, so fixtures can carry extra keys."""
    cols = {c.name: c for c in table.columns}
    out = []
    for item in items:
        row = {}
        for k, v in item.items():
            if k in cols:
                row[k] = ts(v) if isinstance(v, str) and k.endswith("_at") else v
        out.append(row)
    return out


def put(conn: Connection, model: type[Base], items: list[dict[str, Any]]) -> None:
    if items:
        conn.execute(insert(model.__table__), rows(model.__table__, items))


def reset(conn: Connection) -> None:
    tables = [t.name for t in Base.metadata.sorted_tables if t.name not in KEEP]
    conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    conn.execute(update(EventConsumer).values(last_event_id=0, updated_at=func.now()))


def seed(conn: Connection, ai_from_start: bool) -> dict[str, int]:
    departments = load("departments.json")
    users = load("users.json")
    conversations = load("conversations.json")
    messages = load("messages.json")
    files = load("files.json")
    tasks = load("tasks.json")
    suggestions = load("suggestions.json")
    events: list[dict[str, Any]] = []

    def event(type_: str, at: str, conversation_id: str | None, actor_id: str | None, subject_type: str,
              subject_id: str, payload: dict[str, Any]) -> None:
        events.append({"type": type_, "created_at": at, "conversation_id": conversation_id, "actor_id": actor_id,
                       "subject_type": subject_type, "subject_id": subject_id, "payload": payload})

    put(conn, Department, departments)

    # Managers before reports, so the closure trigger always finds the manager's ancestors.
    password_hash = PasswordHasher().hash(PASSWORD)
    placed: set[str] = set()
    pending = list(users)
    while pending:
        ready = [u for u in pending if u["manager_id"] is None or u["manager_id"] in placed]
        if not ready:
            raise SystemExit("users.json has a manager cycle or a missing manager")
        put(conn, User, [{**u, "password_hash": password_hash} for u in ready])
        placed |= {u["id"] for u in ready}
        pending = [u for u in pending if u["id"] not in placed]

    for c in conversations:
        member_key = ":".join(sorted(m["user_id"] for m in c["members"])) if c["kind"] == "dm" else None
        put(conn, Conversation, [{**c, "member_key": member_key}])
        put(conn, ConversationMember, [{**m, "conversation_id": c["id"]} for m in c["members"]])
        for m in c["members"]:
            via = "department_sync" if c["kind"] == "department" else "create"
            event("member.joined", m["joined_at"], c["id"], c["created_by"] or m["user_id"], "user", m["user_id"],
                  {"user_id": m["user_id"], "role": m["role"], "via": via, "by_user_id": c["created_by"]})
            if m["left_at"]:
                event("member.left", m["left_at"], c["id"], m["user_id"], "user", m["user_id"],
                      {"user_id": m["user_id"], "role": m["role"], "via": "leave", "by_user_id": None})

    for m in sorted(messages, key=lambda m: (m["created_at"], m["seq"])):  # parents first
        put(conn, Message, [m])
        put(conn, MessageEdit, [{**e, "message_id": m["id"]} for e in m["edits"]])
        put(conn, MessageMention, [{**x, "message_id": m["id"]} for x in m["mentions"]])
        put(conn, MessageRef, [{**x, "message_id": m["id"]} for x in m["refs"]])
        put(conn, Reaction, [{**r, "message_id": m["id"]} for r in m["reactions"]])

        original = m["edits"][0]["prior_body_md"] if m["edits"] else m["body_md"]
        event("message.created", m["created_at"], m["conversation_id"], m["author_id"], "message", m["id"], {
            "message_id": m["id"], "seq": m["seq"], "parent_id": m["parent_id"],
            "also_in_channel": m["also_in_channel"], "author_id": m["author_id"], "body_md": original,
            "mentions": [] if m["edits"] else m["mentions"], "refs": [] if m["edits"] else m["refs"],
            "file_ids": m["file_ids"], "created_at": m["created_at"],
        })
        for e in m["edits"]:
            event("message.updated", e["edited_at"], m["conversation_id"], m["author_id"], "message", m["id"], {
                "message_id": m["id"], "seq": m["seq"], "parent_id": m["parent_id"], "body_md": m["body_md"],
                "prior_body_md": e["prior_body_md"], "mentions": m["mentions"], "refs": m["refs"],
                "edited_at": e["edited_at"],
            })
        if m["deleted_at"]:
            event("message.deleted", m["deleted_at"], m["conversation_id"], m["author_id"], "message", m["id"],
                  {"message_id": m["id"], "seq": m["seq"], "parent_id": m["parent_id"], "deleted_at": m["deleted_at"]})
        for r in m["reactions"]:
            event("reaction.added", r["created_at"], m["conversation_id"], r["user_id"], "message", m["id"],
                  {"message_id": m["id"], "user_id": r["user_id"], "emoji": r["emoji"]})

    for f in files:
        put(conn, File, [{**f, "size": len(file_bytes(f))}])
        event("file.uploaded", f["created_at"], f["conversation_id"], f["uploader_id"], "file", f["id"], {
            "file_id": f["id"], "message_id": f["message_id"], "uploader_id": f["uploader_id"], "kind": f["kind"],
            "name": f["name"], "mime": f["mime"], "size": len(file_bytes(f)), "language": f["language"],
        })

    dept_of = {u["id"]: u["department_id"] for u in users}
    applied_by = {s["applied_task_id"]: s["id"] for s in suggestions if s["applied_task_id"]}
    for t in tasks:
        put(conn, Task, [{**t, "updated_at": (t["history"][-1]["changed_at"] if t["history"] else t["created_at"])}])
        put(conn, TaskSource, [{"task_id": t["id"], "message_id": mid} for mid in t["source_message_ids"]])
        put(conn, TaskHistory, [{**h, "task_id": t["id"]} for h in t["history"]])
        event("task.created", t["created_at"], t["source_conversation_id"], t["created_by"], "task", t["id"], {
            "task_id": t["id"], "title": t["title"], "description_md": t["description_md"],
            "assignee_id": t["assignee_id"], "assignee_department_id": dept_of[t["assignee_id"]],
            "created_by": t["created_by"], "created_by_ai": t["created_by_ai"],
            "suggestion_id": applied_by.get(t["id"]),
            "project": t["project"], "status": "open", "priority": t["priority"], "due_at": t["due_at"],
            "source_conversation_id": t["source_conversation_id"], "source_message_ids": t["source_message_ids"],
        })
        for h in t["history"]:
            event("task.updated", h["changed_at"], t["source_conversation_id"], h["actor_id"], "task", t["id"], {
                "task_id": t["id"], "assignee_id": t["assignee_id"],
                "assignee_department_id": dept_of[t["assignee_id"]], "status": h["new_value"],
                "changes": {h["field"]: [h["old_value"], h["new_value"]]},
            })

    for s in suggestions:
        put(conn, AiProposal, [s])
        event("suggestion.created", s["created_at"], s["conversation_id"], None, "suggestion", s["id"], {
            "suggestion_id": s["id"], "run_id": None, "kind": s["kind"], "proposal": s["payload"],
            "confidence": s["confidence"],
        })
        if s["decided_at"]:
            event("suggestion.decided", s["decided_at"], s["conversation_id"], s["decided_by"], "suggestion", s["id"],
                  {"suggestion_id": s["id"], "status": s["status"], "applied_task_id": s["applied_task_id"]})

    put(conn, Notification, load("notifications.json"))
    put(conn, ChannelReadCursor, load("read_cursors.json"))

    # Derived columns: per-conversation seq allocator and thread counters on parents.
    conn.execute(text("""
        UPDATE conversations c SET last_seq = m.max_seq
        FROM (SELECT conversation_id, max(seq) AS max_seq FROM messages GROUP BY conversation_id) m
        WHERE m.conversation_id = c.id
    """))
    conn.execute(text("""
        UPDATE messages p SET reply_count = r.n, last_reply_at = r.last_at
        FROM (SELECT parent_id, count(*) AS n, max(created_at) AS last_at FROM messages
              WHERE parent_id IS NOT NULL AND deleted_at IS NULL GROUP BY parent_id) r
        WHERE r.parent_id = p.id
    """))

    events.sort(key=lambda e: e["created_at"])
    put(conn, Event, events)
    if not ai_from_start:
        last = conn.execute(select(func.coalesce(func.max(Event.id), 0))).scalar_one()
        conn.execute(update(EventConsumer).where(EventConsumer.name == "ai").values(last_event_id=last))

    write_files(files)
    return {"users": len(users), "conversations": len(conversations), "messages": len(messages),
            "tasks": len(tasks), "suggestions": len(suggestions), "events": len(events)}


def file_bytes(f: dict[str, Any]) -> bytes:
    return f["content"].encode() if "content" in f else base64.b64decode(f["content_b64"])


def write_files(files: list[dict[str, Any]]) -> None:
    for f in files:
        path = FILES_DIR / f["storage_key"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes(f))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="truncate all data tables first")
    parser.add_argument("--ai-from-start", action="store_true", help="leave the AI cursor at 0")
    args = parser.parse_args()

    with engine.begin() as conn:
        if args.reset:
            reset(conn)
        elif conn.execute(select(func.count()).select_from(User)).scalar_one():
            sys.exit("database already has users; run with --reset to replace them")
        counts = seed(conn, args.ai_from_start)
    print("seeded " + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
