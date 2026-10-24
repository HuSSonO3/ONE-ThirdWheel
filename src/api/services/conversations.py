"""Conversations and membership (spec 1.5, 1.6, 3.5). One model, three kinds."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import events
from api.access import ai_can_read, can_access, conversation_access_clause
from api.errors import ApiError, conflict, forbidden, invalid
from api.models import Conversation, ConversationMember, User
from api.schemas import contract as c
from api.services.common import get_or_404, now

# ---------------------------------------------------------------- membership primitives

def membership(db: Session, conversation_id: uuid.UUID, user_id: uuid.UUID) -> ConversationMember | None:
    return db.scalar(select(ConversationMember).where(
        ConversationMember.conversation_id == conversation_id, ConversationMember.user_id == user_id,
        ConversationMember.left_at.is_(None)))


def add_member(db: Session, conversation: Conversation, user_id: uuid.UUID, *, via: str, by: uuid.UUID | None,
               role: str = "member") -> ConversationMember:
    """Open a membership (idempotent). Rows are never reopened: a rejoin is a new row (DECISIONS #6)."""
    existing = membership(db, conversation.id, user_id)
    if existing:
        return existing
    row = ConversationMember(conversation_id=conversation.id, user_id=user_id, role=role, joined_at=now())
    db.add(row)
    db.flush()
    events.member(db, True, conversation.id, user_id, role, via, by)
    return row


def close_member(db: Session, conversation: Conversation, user_id: uuid.UUID, *, via: str,
                 by: uuid.UUID | None) -> bool:
    row = membership(db, conversation.id, user_id)
    if not row:
        return False
    row.left_at = now()
    events.member(db, False, conversation.id, user_id, row.role, via, by)
    return True


def department_conversation(db: Session, department_id: uuid.UUID) -> Conversation:
    return db.scalar(select(Conversation).where(Conversation.kind == "department",
                                                Conversation.department_id == department_id))


# ---------------------------------------------------------------- guards

def readable(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    conv = get_or_404(db, Conversation, conversation_id, "Conversation")
    if not can_access(db, user, conv):
        raise forbidden()
    return conv


def require_member(db: Session, user: User, conv: Conversation) -> ConversationMember:
    row = membership(db, conv.id, user.id)
    if not row:
        raise forbidden("You're not a member of this conversation.", code="not_a_member")
    return row


def require_writable(conv: Conversation) -> None:
    if conv.archived_at is not None:
        raise conflict("archived", "This conversation is archived.")


def require_channel(conv: Conversation, action: str) -> None:
    if conv.kind != "channel":
        raise conflict("conflict", f"You can't {action} a {conv.kind} conversation.")


def require_owner(db: Session, user: User, conv: Conversation) -> None:
    row = membership(db, conv.id, user.id)
    if user.role != "admin" and (row is None or row.role != "owner"):
        raise forbidden("Only the channel owner can do that.")


# ---------------------------------------------------------------- queries

def list_mine(db: Session, user: User, include_archived: bool) -> list[Conversation]:
    q = select(Conversation).join(ConversationMember, ConversationMember.conversation_id == Conversation.id).where(
        ConversationMember.user_id == user.id, ConversationMember.left_at.is_(None))
    if not include_archived:
        q = q.where(Conversation.archived_at.is_(None))
    return list(db.scalars(q))


def browse(db: Session, user: User, include_archived: bool) -> list[Conversation]:
    q = select(Conversation).where(Conversation.kind == "channel", Conversation.is_public,
                                   conversation_access_clause(user)).order_by(Conversation.name)
    if not include_archived:
        q = q.where(Conversation.archived_at.is_(None))
    return list(db.scalars(q))


def members(db: Session, conv: Conversation, include_former: bool) -> list[ConversationMember]:
    q = select(ConversationMember).where(ConversationMember.conversation_id == conv.id)
    if not include_former:
        q = q.where(ConversationMember.left_at.is_(None))
    return list(db.scalars(q.order_by(ConversationMember.joined_at)))


# ---------------------------------------------------------------- commands

def _active_users(db: Session, ids: list[uuid.UUID], field: str) -> list[User]:
    found = db.scalars(select(User).where(User.id.in_(ids), User.active)).all()
    if len(found) != len(set(ids)):
        raise invalid(field, "Unknown or inactive user.")
    return list(found)


def create(db: Session, user: User, body: c.ConversationCreate) -> tuple[Conversation, bool]:
    """Returns (conversation, created). A DM that already exists is returned with created=False."""
    ids = list(dict.fromkeys(body.member_ids or []))
    if body.kind == "dm":
        others = [i for i in ids if i != user.id]
        if len(others) != 1:
            raise invalid("member_ids", "A DM needs exactly one other person.")
        peer = _active_users(db, others, "member_ids")[0]
        key = ":".join(sorted((str(user.id), str(peer.id))))
        existing = db.scalar(select(Conversation).where(Conversation.kind == "dm", Conversation.member_key == key))
        if existing:
            return existing, False
        conv = Conversation(kind="dm", member_key=key, created_by=user.id)
        db.add(conv)
        db.flush()
        add_member(db, conv, user.id, via="create", by=user.id)
        add_member(db, conv, peer.id, via="create", by=user.id)
        return conv, True

    if not body.name or not body.name.strip():
        raise invalid("name", "A channel needs a name.")
    invited = _active_users(db, [i for i in ids if i != user.id], "member_ids")
    conv = Conversation(kind="channel", name=body.name.strip(), description=body.description,
                        is_public=True if body.is_public is None else body.is_public, created_by=user.id)
    db.add(conv)
    db.flush()
    add_member(db, conv, user.id, via="create", by=user.id, role="owner")
    for other in invited:
        add_member(db, conv, other.id, via="create", by=user.id)
    return conv, True


def update(db: Session, user: User, conv: Conversation, body: c.ConversationUpdate) -> Conversation:
    require_channel(conv, "edit")
    require_owner(db, user, conv)
    require_writable(conv)
    changes = {}
    for field in body.model_fields_set:
        value = getattr(body, field)
        if field == "name" and value is not None:
            value = value.strip()
        if getattr(conv, field) != value:
            changes[field] = [getattr(conv, field), value]
            setattr(conv, field, value)
    if changes:
        events.conversation_updated(db, conv.id, user.id, changes)
    return conv


def archive(db: Session, user: User, conv: Conversation) -> Conversation:
    require_channel(conv, "archive")
    require_owner(db, user, conv)
    if conv.archived_at is None:
        conv.archived_at = now()
        events.conversation_updated(db, conv.id, user.id, {"archived_at": [None, conv.archived_at]})
    return conv


def join(db: Session, user: User, conv: Conversation) -> ConversationMember:
    if not (conv.kind == "channel" and conv.is_public):
        raise forbidden("Only public channels can be joined.")
    require_writable(conv)
    return add_member(db, conv, user.id, via="join", by=None)


def leave(db: Session, user: User, conv: Conversation) -> None:
    if conv.kind != "channel":
        raise conflict("cannot_leave", f"You can't leave a {conv.kind} conversation.")
    if not close_member(db, conv, user.id, via="leave", by=None):
        raise forbidden("You're not a member of this conversation.", code="not_a_member")


def invite(db: Session, user: User, conv: Conversation, user_ids: list[uuid.UUID]) -> list[ConversationMember]:
    require_channel(conv, "invite people to")
    require_member(db, user, conv)
    require_writable(conv)
    for other in _active_users(db, list(dict.fromkeys(user_ids)), "user_ids"):
        add_member(db, conv, other.id, via="invite", by=user.id)
    return members(db, conv, include_former=False)


def remove(db: Session, user: User, conv: Conversation, target_id: uuid.UUID) -> None:
    require_channel(conv, "remove people from")
    require_owner(db, user, conv)
    if not close_member(db, conv, target_id, via="removed", by=user.id):
        raise ApiError(404, "not_found", "That person isn't a member.")


def update_membership(db: Session, user: User, conv: Conversation, body: c.MembershipUpdate) -> ConversationMember:
    row = require_member(db, user, conv)
    was_active = ai_can_read(db, conv)
    if body.muted is not None:
        row.muted = body.muted
    if body.ai_opt_in is not None:
        row.ai_opt_in = body.ai_opt_in
    db.flush()
    is_active = ai_can_read(db, conv)
    if was_active != is_active:
        events.conversation_updated(db, conv.id, user.id, {"ai_active": [was_active, is_active]})
    return row


def set_ai_enabled(db: Session, admin: User, conv: Conversation, enabled: bool) -> Conversation:
    if conv.kind == "dm":
        raise conflict("conflict", "DMs use per-member opt-in, not the admin switch.")
    if conv.ai_enabled != enabled:
        events.conversation_updated(db, conv.id, admin.id, {"ai_enabled": [conv.ai_enabled, enabled]})
        conv.ai_enabled = enabled
    return conv
