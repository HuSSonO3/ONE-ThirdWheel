"""ORM rows → contract shapes (contracts/openapi.yaml components). Batch functions, so lists stay O(1) queries.

Returned dicts are validated against the generated contract models by FastAPI's `response_model`.
"""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from api import config
from api.models import (
    AiProposal,
    AiRun,
    AiToolCall,
    ChannelReadCursor,
    Conversation,
    ConversationMember,
    Department,
    File,
    Message,
    MessageMention,
    Notification,
    Reaction,
    Task,
    TaskSource,
    User,
)
from api.text import preview

Json = dict[str, Any]


# ---------------------------------------------------------------- users & departments

def user_summary(u: User) -> Json:
    return {"id": u.id, "name": u.name, "job_title": u.job_title, "department_id": u.department_id,
            "avatar_file_id": u.avatar_file_id, "active": u.active}


def user_summaries(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Json]:
    if not ids:
        return {}
    return {u.id: user_summary(u) for u in db.scalars(select(User).where(User.id.in_(ids)))}


def users(db: Session, rows: list[User]) -> list[Json]:
    departments = dict(db.execute(select(Department.id, Department.name)).tuples().all())
    managers = dict(db.execute(
        select(User.id, User.name).where(User.id.in_({u.manager_id for u in rows if u.manager_id}))
    ).tuples().all())
    return [{
        **user_summary(u), "email": u.email, "role": u.role,
        "department_name": departments.get(u.department_id), "manager_id": u.manager_id,
        "manager_name": managers.get(u.manager_id), "timezone": u.timezone, "created_at": u.created_at,
    } for u in rows]


def user(db: Session, u: User) -> Json:
    return users(db, [u])[0]


def user_profile(db: Session, u: User) -> Json:
    reports = db.scalars(select(User).where(User.manager_id == u.id).order_by(User.name)).all()
    return {**user(db, u), "direct_reports": [user_summary(r) for r in reports]}


def departments(db: Session, rows: list[Department]) -> list[Json]:
    ids = [d.id for d in rows]
    channels = dict(db.execute(select(Conversation.department_id, Conversation.id).where(
        Conversation.kind == "department", Conversation.department_id.in_(ids))).tuples().all())
    counts = dict(db.execute(select(User.department_id, func.count()).where(
        User.department_id.in_(ids), User.active).group_by(User.department_id)).tuples().all())
    return [{"id": d.id, "name": d.name, "conversation_id": channels[d.id], "member_count": counts.get(d.id, 0)}
            for d in rows]


# ---------------------------------------------------------------- conversations

def conversation_refs(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Json]:
    if not ids:
        return {}
    rows = db.execute(select(Conversation.id, Conversation.kind, Conversation.name).where(Conversation.id.in_(ids)))
    return {i: {"id": i, "kind": k, "name": n} for i, k, n in rows}


def conversations(db: Session, viewer: User, rows: list[Conversation]) -> list[Json]:
    if not rows:
        return []
    ids = [c.id for c in rows]
    cm, m = ConversationMember, Message
    open_members = db.execute(select(cm).where(cm.conversation_id.in_(ids), cm.left_at.is_(None))).scalars().all()
    by_conv: dict[uuid.UUID, list[ConversationMember]] = defaultdict(list)
    for row in open_members:
        by_conv[row.conversation_id].append(row)

    last_at = dict(db.execute(select(m.conversation_id, func.max(m.created_at)).where(
        m.conversation_id.in_(ids), m.deleted_at.is_(None)).group_by(m.conversation_id)).tuples().all())

    cursor = func.coalesce(ChannelReadCursor.last_read_seq, 0)
    unread = (
        select(m.conversation_id, m.id)
        .outerjoin(ChannelReadCursor, and_(ChannelReadCursor.conversation_id == m.conversation_id,
                                           ChannelReadCursor.user_id == viewer.id))
        .where(m.conversation_id.in_(ids), m.seq > cursor, m.author_id != viewer.id, m.deleted_at.is_(None),
               or_(m.parent_id.is_(None), m.also_in_channel))
    ).subquery()
    unread_counts = dict(db.execute(select(unread.c.conversation_id, func.count()).group_by(
        unread.c.conversation_id)).tuples().all())
    mentions_me = or_(MessageMention.user_id == viewer.id, MessageMention.kind.in_(("channel", "here")),
                      and_(MessageMention.kind == "department", MessageMention.department_id == viewer.department_id))
    mention_counts = dict(db.execute(
        select(unread.c.conversation_id, func.count(func.distinct(unread.c.id)))
        .join(MessageMention, MessageMention.message_id == unread.c.id).where(mentions_me)
        .group_by(unread.c.conversation_id)
    ).tuples().all())

    peers = user_summaries(db, {r.user_id for c in rows if c.kind == "dm" for r in by_conv[c.id]})
    out = []
    for c in rows:
        members = by_conv[c.id]
        mine = next((r for r in members if r.user_id == viewer.id), None)
        peer = next((r.user_id for r in members if r.user_id != viewer.id), None) if c.kind == "dm" else None
        ai_active = c.ai_enabled if c.kind != "dm" else len(members) == 2 and all(r.ai_opt_in for r in members)
        out.append({
            "id": c.id, "kind": c.kind, "name": c.name, "description": c.description, "is_public": c.is_public,
            "department_id": c.department_id, "ai_enabled": c.ai_enabled, "ai_active": ai_active,
            "archived_at": c.archived_at, "created_at": c.created_at, "member_count": len(members),
            "last_seq": c.last_seq, "last_message_at": last_at.get(c.id),
            "unread_count": unread_counts.get(c.id, 0) if mine else 0,
            "mention_count": mention_counts.get(c.id, 0) if mine else 0,
            "membership": {"role": mine.role, "muted": mine.muted, "ai_opt_in": mine.ai_opt_in,
                           "joined_at": mine.joined_at} if mine else None,
            "dm_peer": peers.get(peer) if peer else None,
        })
    return out


def conversation(db: Session, viewer: User, c: Conversation) -> Json:
    return conversations(db, viewer, [c])[0]


def members(db: Session, rows: list[ConversationMember]) -> list[Json]:
    people = user_summaries(db, {r.user_id for r in rows})
    return [{"user": people[r.user_id], "role": r.role, "joined_at": r.joined_at, "left_at": r.left_at,
             "muted": r.muted, "ai_opt_in": r.ai_opt_in} for r in rows]


# ---------------------------------------------------------------- messages, files, reactions

def thumbnail_path(file_id: uuid.UUID):
    return config.FILES_DIR / "thumbnails" / f"{file_id}.png"


def file_meta(f: File) -> Json:
    return {"id": f.id, "uploader_id": f.uploader_id, "conversation_id": f.conversation_id,
            "message_id": f.message_id, "kind": f.kind, "name": f.name, "mime": f.mime, "size": f.size,
            "language": f.language, "has_thumbnail": thumbnail_path(f.id).exists(), "created_at": f.created_at}


def reaction_summaries(db: Session, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Json]]:
    grouped: dict[uuid.UUID, dict[str, list[uuid.UUID]]] = defaultdict(lambda: defaultdict(list))
    for r in db.scalars(select(Reaction).where(Reaction.message_id.in_(message_ids)).order_by(Reaction.created_at)):
        grouped[r.message_id][r.emoji].append(r.user_id)
    return {mid: [{"emoji": e, "count": len(u), "user_ids": u} for e, u in by_emoji.items()]
            for mid, by_emoji in grouped.items()}


def messages(db: Session, rows: list[Message]) -> list[Json]:
    if not rows:
        return []
    ids = [m.id for m in rows]
    mentions: dict[uuid.UUID, list[Json]] = defaultdict(list)
    for mm in db.scalars(select(MessageMention).where(MessageMention.message_id.in_(ids))):
        mentions[mm.message_id].append({"kind": mm.kind, "user_id": mm.user_id, "department_id": mm.department_id})
    files: dict[uuid.UUID, list[Json]] = defaultdict(list)
    for f in db.scalars(select(File).where(File.message_id.in_(ids)).order_by(File.created_at)):
        files[f.message_id].append(file_meta(f))
    reactions = reaction_summaries(db, ids)

    repliers: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    parents = [m.id for m in rows if m.reply_count]
    if parents:
        recent = (select(Message.parent_id, Message.author_id, func.max(Message.created_at).label("at"))
                  .where(Message.parent_id.in_(parents), Message.deleted_at.is_(None))
                  .group_by(Message.parent_id, Message.author_id).order_by(func.max(Message.created_at).desc()))
        for parent_id, author_id, _ in db.execute(recent):
            if len(repliers[parent_id]) < 5:
                repliers[parent_id].append(author_id)

    out = []
    for m in rows:
        deleted = m.deleted_at is not None
        out.append({
            "id": m.id, "conversation_id": m.conversation_id, "author_id": m.author_id, "parent_id": m.parent_id,
            "seq": m.seq, "body_md": "" if deleted else m.body_md, "client_id": m.client_id,
            "also_in_channel": m.also_in_channel, "reply_count": m.reply_count, "last_reply_at": m.last_reply_at,
            "reply_user_ids": repliers.get(m.id, []), "created_at": m.created_at, "edited_at": m.edited_at,
            "deleted_at": m.deleted_at, "mentions": [] if deleted else mentions.get(m.id, []),
            "reactions": reactions.get(m.id, []), "files": [] if deleted else files.get(m.id, []),
        })
    return out


def message(db: Session, m: Message) -> Json:
    return messages(db, [m])[0]


# ---------------------------------------------------------------- tasks & suggestions

def tasks(db: Session, rows: list[Task]) -> list[Json]:
    if not rows:
        return []
    ids = [t.id for t in rows]
    people = user_summaries(db, {t.assignee_id for t in rows})
    refs = conversation_refs(db, {t.source_conversation_id for t in rows})
    sources: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for task_id, message_id in db.execute(select(TaskSource.task_id, TaskSource.message_id).where(
            TaskSource.task_id.in_(ids))):
        sources[task_id].append(message_id)
    return [{
        "id": t.id, "title": t.title, "description_md": t.description_md, "status": t.status,
        "priority": t.priority, "project": t.project, "due_at": t.due_at, "assignee": people[t.assignee_id],
        "created_by": t.created_by, "created_by_ai": t.created_by_ai,
        "source_conversation": refs[t.source_conversation_id], "source_message_ids": sources.get(t.id, []),
        "created_at": t.created_at, "updated_at": t.updated_at, "completed_at": t.completed_at,
    } for t in rows]


def task(db: Session, t: Task) -> Json:
    return tasks(db, [t])[0]


def suggestions(db: Session, viewer: User, rows: list[AiProposal]) -> list[Json]:
    from api.services.suggestions import can_accept

    return [{
        "id": p.id, "conversation_id": p.conversation_id, "kind": p.kind, "payload": p.payload,
        "confidence": p.confidence, "status": p.status, "applied_task_id": p.applied_task_id,
        "decided_by": p.decided_by, "decided_at": p.decided_at, "expires_at": p.expires_at,
        "created_at": p.created_at, "can_accept": can_accept(db, viewer, p),
    } for p in rows]


def suggestion(db: Session, viewer: User, p: AiProposal) -> Json:
    return suggestions(db, viewer, [p])[0]


# ---------------------------------------------------------------- notifications & admin

def notifications(db: Session, rows: list[Notification]) -> list[Json]:
    by_type: dict[str, set[uuid.UUID]] = defaultdict(set)
    for n in rows:
        by_type[n.ref_type].add(n.ref_id)
    context: dict[uuid.UUID, tuple[uuid.UUID | None, uuid.UUID | None, str]] = {}
    if by_type["message"]:
        for m in db.scalars(select(Message).where(Message.id.in_(by_type["message"]))):
            context[m.id] = (m.conversation_id, m.author_id, "" if m.deleted_at else preview(m.body_md))
    if by_type["task"]:
        for t in db.scalars(select(Task).where(Task.id.in_(by_type["task"]))):
            context[t.id] = (t.source_conversation_id, t.created_by, t.title)
    if by_type["suggestion"]:
        for p in db.scalars(select(AiProposal).where(AiProposal.id.in_(by_type["suggestion"]))):
            title = p.payload.get("title") or f"Mark task {p.payload.get('new_status', 'done')}"
            context[p.id] = (p.conversation_id, None, f"Suggested: {title}")
    out = []
    for n in rows:
        conversation_id, actor_id, text = context.get(n.ref_id, (None, None, ""))
        out.append({"id": n.id, "type": n.type, "ref_type": n.ref_type, "ref_id": n.ref_id,
                    "conversation_id": conversation_id, "actor_id": actor_id, "preview": text,
                    "read_at": n.read_at, "created_at": n.created_at})
    return out


def ai_runs(db: Session, rows: list[AiRun]) -> list[Json]:
    refs = conversation_refs(db, {r.conversation_id for r in rows})
    counts = dict(db.execute(select(AiToolCall.run_id, func.count()).where(
        AiToolCall.run_id.in_([r.id for r in rows])).group_by(AiToolCall.run_id)).tuples().all())
    return [{"id": r.id, "conversation": refs[r.conversation_id], "from_event_id": r.from_event_id,
             "to_event_id": r.to_event_id, "started_at": r.started_at, "finished_at": r.finished_at,
             "status": r.status, "error": r.error, "tool_call_count": counts.get(r.id, 0)} for r in rows]


def tool_calls(rows: list[AiToolCall]) -> list[Json]:
    return [{"id": c.id, "run_id": c.run_id, "tool_name": c.tool_name, "arguments": c.arguments,
             "scope_check": c.scope_check, "result": c.result, "status": c.status,
             "source_message_ids": [s for s in (c.arguments or {}).get("source_message_ids", []) if _is_uuid(s)],
             "created_at": c.created_at} for c in rows]


def _is_uuid(value: object) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True
