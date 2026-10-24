"""Access rules: the one place every feature asks "may this principal see or do this?".

Nothing here consults job titles, and being someone's superior grants no conversation access
(feature spec, Overview). Each rule has its own test in tests/test_access.py. The `*_clause`
functions are the same rules as SQL, for lists and search that must filter in the query.
"""

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.orm import Session

from api.models import Conversation, ConversationMember, Message, Task, User, UserClosure


def _id(x: User | uuid.UUID) -> uuid.UUID:
    return x.id if isinstance(x, User) else x


def is_member(db: Session, user: User | uuid.UUID, conversation: Conversation, at: datetime | None = None) -> bool:
    """True if `user` has a membership row in `conversation` that is open at time `at`.

    `at=None` means now: a row with `left_at IS NULL`. With `at` set, a row counts when
    `joined_at <= at` and (`left_at IS NULL` or `left_at > at`).
    """
    cm = ConversationMember
    cond = [cm.conversation_id == conversation.id, cm.user_id == _id(user)]
    cond += [cm.left_at.is_(None)] if at is None else [cm.joined_at <= at, or_(cm.left_at.is_(None), cm.left_at > at)]
    return bool(db.scalar(select(exists().where(*cond))))


def is_superior(db: Session, superior: User | uuid.UUID, subordinate: User | uuid.UUID) -> bool:
    """True if `superior` is strictly above `subordinate` in the org tree (`user_closure.depth > 0`).

    Used only for the task dashboard (2.4) and `can_see`; never for conversation access.
    """
    return bool(db.scalar(select(exists().where(
        UserClosure.ancestor_id == _id(superior), UserClosure.descendant_id == _id(subordinate), UserClosure.depth > 0,
    ))))


def can_access(db: Session, user: User, conversation: Conversation, at: datetime | None = None) -> bool:
    """True if `user` may read `conversation` (spec 1.5), or with `at`, content posted at time `at` (2.7).

    `(kind = 'channel' AND is_public) OR` a membership that is open now (`at=None`), or with `at`,
    a membership that is open or was closed after `at`. So current members read the whole history,
    and someone who left keeps what was posted before they left and nothing after. The user must
    be active.

    Every read path routes through this: message lists, threads, embeds (resolved for the viewer,
    not the author), search results, file downloads and conversation task tabs.
    """
    if not user.active:
        return False
    if conversation.kind == "channel" and conversation.is_public:
        return True
    cm = ConversationMember
    cond = [cm.conversation_id == conversation.id, cm.user_id == user.id]
    cond.append(cm.left_at.is_(None) if at is None else or_(cm.left_at.is_(None), cm.left_at > at))
    return bool(db.scalar(select(exists().where(*cond))))


def can_see(db: Session, user: User, task: Task) -> bool:
    """True if `user` may see `task` (spec 2.3). Any of:

    - `user` is the assignee;
    - `is_superior(user, assignee)`;
    - `user.department_id = assignee.department_id` (the task is in their department channel);
    - `user` is currently a member of `task.source_conversation_id`.

    Seeing a task does not imply seeing its source message: the embed is checked separately with
    `can_access` and renders as the private stub when that fails.
    """
    if not user.active:
        return False
    return bool(db.scalar(select(exists().where(Task.id == task.id, task_visible_clause(user)))))


def can_assign(db: Session, assigner: User, assignee: User, conversation: Conversation) -> bool:
    """True if `assigner` may give `assignee` a task spawned in `conversation` (spec 2.7).

    `is_member(assigner, conversation) AND (is_member(assignee, conversation)
    OR assignee.manager_id = assigner.id)`. The exception is the direct manager only (one level,
    not the closure). Called on task create, on assignee change, and on suggestion accept, where
    the assigner is the accepting human. The AI never assigns, so it gets no exception.
    """
    if not (assigner.active and assignee.active) or not is_member(db, assigner, conversation):
        return False
    return is_member(db, assignee, conversation) or assignee.manager_id == assigner.id


def ai_can_read(db: Session, conversation: Conversation) -> bool:
    """True if the AI worker may consume events from `conversation` (spec 3.5).

    `department` and `channel`: `conversation.ai_enabled`. `dm`: both members' open
    `conversation_members.ai_opt_in` are true.
    """
    if conversation.kind != "dm":
        return conversation.ai_enabled
    opt_ins = db.scalars(select(ConversationMember.ai_opt_in).where(
        ConversationMember.conversation_id == conversation.id, ConversationMember.left_at.is_(None),
    )).all()
    return len(opt_ins) == 2 and all(opt_ins)


# ---------------------------------------------------------------- the same rules as SQL

def member_clause(user_id: uuid.UUID, conversation_id: ColumnElement) -> ColumnElement[bool]:
    """An open membership of `user_id` in the conversation given by the column `conversation_id`."""
    cm = ConversationMember
    return exists().where(cm.conversation_id == conversation_id, cm.user_id == user_id, cm.left_at.is_(None))


def conversation_access_clause(user: User) -> ColumnElement[bool]:
    """`can_access(user, Conversation)` for the current moment, over the `conversations` table."""
    public = and_(Conversation.kind == "channel", Conversation.is_public)
    return or_(public, member_clause(user.id, Conversation.id))


def message_visible_clause(user: User) -> ColumnElement[bool]:
    """`can_access(user, message.conversation, at=message.created_at)` over `messages` (point-in-time)."""
    cm = ConversationMember
    public = exists().where(Conversation.id == Message.conversation_id, Conversation.kind == "channel",
                            Conversation.is_public)
    membership = exists().where(cm.conversation_id == Message.conversation_id, cm.user_id == user.id,
                                or_(cm.left_at.is_(None), cm.left_at > Message.created_at))
    return or_(public, membership)


def task_visible_clause(user: User) -> ColumnElement[bool]:
    """`can_see(user, Task)` over the `tasks` table."""
    superior = exists().where(UserClosure.ancestor_id == user.id, UserClosure.descendant_id == Task.assignee_id,
                              UserClosure.depth > 0)
    clauses = [Task.assignee_id == user.id, superior, member_clause(user.id, Task.source_conversation_id)]
    if user.department_id:
        assignee_department = select(User.department_id).where(User.id == Task.assignee_id).scalar_subquery()
        clauses.append(assignee_department == user.department_id)
    return or_(*clauses)
