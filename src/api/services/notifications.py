"""In-app notifications (spec 1.19).

Written on a direct @mention, an @department/@channel/@here mention, a DM, a reply in a thread
you're in, a task assignment and a suggestion addressed to you. Never to the author. A muted
membership suppresses everything except a direct @user mention. One notification per user per
message: the most specific reason wins.
"""

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api import realtime, serializers
from api.models import Conversation, ConversationMember, Message, Notification, User
from api.services.common import now
from api.text import Mention

PRIORITY = ("mention", "dm", "thread_reply")


def notify(db: Session, user_ids: set[uuid.UUID], type_: str, ref_type: str, ref_id: uuid.UUID) -> None:
    for user_id in user_ids:
        n = Notification(user_id=user_id, type=type_, ref_type=ref_type, ref_id=ref_id)
        db.add(n)
        db.flush()
        data = serializers.notifications(db, [n])[0]
        realtime.push(db, [user_id], realtime.frame("notification.created", None, data["conversation_id"],
                                                    {"notification": data}))


def for_message(db: Session, m: Message, conversation: Conversation, mentions: list[Mention],
                only_new_direct: set[uuid.UUID] | None = None) -> None:
    """Notify everyone a new message concerns. With `only_new_direct` (an edit), only newly @mentioned users."""
    rows = db.scalars(select(ConversationMember).where(
        ConversationMember.conversation_id == conversation.id, ConversationMember.left_at.is_(None))).all()
    members = {r.user_id: r for r in rows}
    awake = {u for u, r in members.items() if not r.muted}
    reasons: dict[uuid.UUID, str] = {}

    def add(users: set[uuid.UUID], reason: str) -> None:
        for u in users - {m.author_id}:
            if u not in reasons or PRIORITY.index(reason) < PRIORITY.index(reasons[u]):
                reasons[u] = reason

    direct = {uuid.UUID(str(x["user_id"])) for x in mentions if x["kind"] == "user"}
    readable = direct if conversation.kind == "channel" and conversation.is_public else direct & set(members)
    active = set(db.scalars(select(User.id).where(User.id.in_(readable), User.active)))
    if only_new_direct is not None:
        add(active & only_new_direct, "mention")
    else:
        add(active, "mention")
        departments = {uuid.UUID(str(x["department_id"])) for x in mentions if x["kind"] == "department"}
        if departments:
            in_dept = set(db.scalars(select(User.id).where(User.department_id.in_(departments))))
            add(in_dept & awake, "mention")
        if any(x["kind"] in ("channel", "here") for x in mentions):
            add(awake, "mention")
        if conversation.kind == "dm":
            add(awake, "dm")
        if m.parent_id:
            parent = db.get(Message, m.parent_id)
            thread = {parent.author_id} | set(db.scalars(select(Message.author_id).where(
                Message.parent_id == m.parent_id, Message.deleted_at.is_(None))))
            add(thread & awake, "thread_reply")

    for reason in PRIORITY:
        notify(db, {u for u, r in reasons.items() if r == reason}, reason, "message", m.id)


def list_for(db: Session, user: User, unread_only: bool, limit: int) -> list[Notification]:
    q = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    return list(db.scalars(q.order_by(Notification.created_at.desc()).limit(limit)))


def mark_read(db: Session, user: User, notification_id: uuid.UUID) -> bool:
    """False if the notification doesn't exist or isn't the caller's."""
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        return False
    if n.read_at is None:
        n.read_at = now()
    return True


def mark_all_read(db: Session, user: User) -> None:
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
               .values(read_at=now()))
