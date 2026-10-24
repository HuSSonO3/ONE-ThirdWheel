"""Messages, threads and reactions (spec 1.7, 1.8, 1.10–1.12)."""

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api import events
from api.access import can_access, message_visible_clause
from api.errors import conflict, forbidden, invalid
from api.models import Conversation, File, Message, MessageEdit, MessageMention, MessageRef, Reaction, User
from api.schemas import contract as c
from api.services import notifications
from api.services.common import get_or_404, now
from api.services.conversations import require_member, require_writable
from api.text import Mention, Ref, extract


def readable_message(db: Session, user: User, message_id: uuid.UUID) -> Message:
    """A message the viewer may read, point-in-time (spec 2.7)."""
    m = get_or_404(db, Message, message_id, "Message")
    if not can_access(db, user, db.get(Conversation, m.conversation_id), at=m.created_at):
        raise forbidden()
    return m


def page(db: Session, conv: Conversation, before_seq: int | None, after_seq: int | None,
         limit: int) -> tuple[list[Message], bool]:
    """Top-level messages (plus replies sent to the channel) in seq order, and whether more exist."""
    q = select(Message).where(Message.conversation_id == conv.id,
                              (Message.parent_id.is_(None)) | Message.also_in_channel)
    if after_seq is not None:
        rows = list(db.scalars(q.where(Message.seq > after_seq).order_by(Message.seq).limit(limit + 1)))
        return rows[:limit], len(rows) > limit
    if before_seq is not None:
        q = q.where(Message.seq < before_seq)
    rows = list(db.scalars(q.order_by(Message.seq.desc()).limit(limit + 1)))
    return list(reversed(rows[:limit])), len(rows) > limit


def thread(db: Session, user: User, message_id: uuid.UUID) -> tuple[Message, list[Message]]:
    m = readable_message(db, user, message_id)
    parent = db.get(Message, m.parent_id) if m.parent_id else m  # older than any reply, so also readable
    # Point-in-time per reply: someone who left sees the thread only up to when they left (2.7).
    replies = list(db.scalars(select(Message).where(Message.parent_id == parent.id, message_visible_clause(user))
                              .order_by(Message.seq)))
    return parent, replies


def _resolve(db: Session, body: str) -> tuple[list[Mention], list[Ref]]:
    """Parse and keep only mentions of real users/departments (refs are checked when resolved)."""
    from api.models import Department

    mentions, refs = extract(body)
    user_ids = {x["user_id"] for x in mentions if x["user_id"]}
    dept_ids = {x["department_id"] for x in mentions if x["department_id"]}
    known_users = {str(i) for i in db.scalars(select(User.id).where(User.id.in_(user_ids)))} if user_ids else set()
    known_depts = {str(i) for i in db.scalars(select(Department.id).where(Department.id.in_(dept_ids)))} \
        if dept_ids else set()
    mentions = [x for x in mentions if (x["user_id"] is None or x["user_id"] in known_users)
                and (x["department_id"] is None or x["department_id"] in known_depts)]
    return mentions, refs


def _store_extracted(db: Session, m: Message, mentions: list[Mention], refs: list[Ref]) -> None:
    db.execute(delete(MessageMention).where(MessageMention.message_id == m.id))
    db.execute(delete(MessageRef).where(MessageRef.message_id == m.id))
    def u(value: str | None) -> uuid.UUID | None:
        return uuid.UUID(value) if value else None

    db.add_all([MessageMention(message_id=m.id, kind=x["kind"], user_id=u(x["user_id"]),
                               department_id=u(x["department_id"])) for x in mentions])
    db.add_all([MessageRef(message_id=m.id, target_type=x["target_type"], target_id=u(x["target_id"]))
                for x in refs])


def create(db: Session, user: User, conv: Conversation, body: c.MessageCreate) -> tuple[Message, bool]:
    """Returns (message, created). A retry with the same client_id returns the original (spec 1.7)."""
    require_member(db, user, conv)
    require_writable(conv)
    existing = db.scalar(select(Message).where(Message.author_id == user.id, Message.client_id == body.client_id))
    if existing:
        return existing, False
    text = body.body_md
    if text.lstrip().startswith("/"):
        raise invalid("body_md", "Slash commands go to POST /commands.")

    parent = None
    if body.parent_id:
        parent = db.get(Message, body.parent_id)
        if not parent or parent.conversation_id != conv.id or parent.parent_id is not None:
            raise invalid("parent_id", "Replies must point at a top-level message in this conversation.")
        if parent.deleted_at is not None:
            raise conflict("conflict", "That message was deleted.")

    files = []
    for file_id in dict.fromkeys(body.file_ids or []):
        f = db.get(File, file_id)
        if not f or f.uploader_id != user.id or f.message_id is not None or \
                (f.conversation_id not in (None, conv.id)) or f.kind == "avatar":
            raise invalid("file_ids", "Attach only your own unattached uploads for this conversation.")
        files.append(f)

    seq = db.execute(update(Conversation).where(Conversation.id == conv.id)
                     .values(last_seq=Conversation.last_seq + 1).returning(Conversation.last_seq)).scalar_one()
    m = Message(conversation_id=conv.id, author_id=user.id, parent_id=parent.id if parent else None, seq=seq,
                body_md=text, client_id=body.client_id, also_in_channel=bool(parent and body.also_in_channel))
    db.add(m)
    db.flush()
    mentions, refs = _resolve(db, text)
    _store_extracted(db, m, mentions, refs)
    if parent:
        parent.reply_count += 1
        parent.last_reply_at = m.created_at
    for f in files:
        f.message_id, f.conversation_id = m.id, conv.id
    db.flush()

    events.message_created(db, m, mentions, refs, [f.id for f in files])
    for f in files:
        events.file_uploaded(db, f)
    notifications.for_message(db, m, conv, mentions)
    return m, True


def edit(db: Session, user: User, m: Message, body: c.MessageUpdate) -> Message:
    if m.author_id != user.id:
        raise forbidden("Only the author can edit a message.")
    if m.deleted_at is not None:
        raise conflict("conflict", "That message was deleted.")
    conv = db.get(Conversation, m.conversation_id)
    require_member(db, user, conv)  # someone who left can't rewrite history they no longer see
    require_writable(conv)
    if body.body_md == m.body_md:
        return m
    before = {x for x in db.scalars(select(MessageMention.user_id).where(
        MessageMention.message_id == m.id, MessageMention.user_id.is_not(None)))}
    prior = m.body_md
    db.add(MessageEdit(message_id=m.id, prior_body_md=prior))
    m.body_md, m.edited_at = body.body_md, now()
    mentions, refs = _resolve(db, m.body_md)
    _store_extracted(db, m, mentions, refs)
    db.flush()
    events.message_updated(db, m, prior, mentions, refs)
    after = {uuid.UUID(x["user_id"]) for x in mentions if x["user_id"]}
    notifications.for_message(db, m, conv, mentions, only_new_direct=after - before)
    return m


def remove(db: Session, user: User, m: Message) -> None:
    if m.author_id != user.id and user.role != "admin":
        raise forbidden("Only the author or an admin can delete a message.")
    if user.role != "admin":
        require_member(db, user, db.get(Conversation, m.conversation_id))
    if m.deleted_at is not None:
        return
    m.deleted_at = now()
    if m.parent_id:
        parent = db.get(Message, m.parent_id)
        parent.reply_count = max(0, parent.reply_count - 1)
    events.message_deleted(db, m, user)


def react(db: Session, user: User, m: Message, emoji: str, add: bool) -> None:
    require_member(db, user, db.get(Conversation, m.conversation_id))  # reading a public channel isn't joining it
    if m.deleted_at is not None:
        raise conflict("conflict", "That message was deleted.")
    if not emoji or len(emoji) > 32:
        raise invalid("emoji", "Not an emoji.")
    if add:
        inserted = db.execute(insert(Reaction).values(message_id=m.id, user_id=user.id, emoji=emoji)
                              .on_conflict_do_nothing().returning(Reaction.emoji)).first()
        changed = inserted is not None
    else:
        changed = db.execute(delete(Reaction).where(Reaction.message_id == m.id, Reaction.user_id == user.id,
                                                    Reaction.emoji == emoji)).rowcount > 0
    if changed:
        events.reaction(db, add, m, user, emoji)
