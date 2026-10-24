"""Access rules: the one place every feature asks "may this principal see or do this?".

Signatures and docstrings are the Phase 0 contract (plan.md §3 Day 1). Bodies are Phase 1 BE work;
each rule below gets its own test. Nothing here consults job titles, and being someone's superior
grants no conversation access (feature spec, Overview).
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from api.models import Conversation, Task, User


def is_member(db: Session, user: User, conversation: Conversation, at: datetime | None = None) -> bool:
    """True if `user` has a membership row in `conversation` that is open at time `at`.

    `at=None` means now: a row with `left_at IS NULL`. With `at` set, a row counts when
    `joined_at <= at` and (`left_at IS NULL` or `left_at > at`). Membership rows are never deleted,
    so this answers "was X in the channel when message M was posted" for point-in-time access (2.7).
    """
    raise NotImplementedError


def is_superior(db: Session, superior: User | uuid.UUID, subordinate: User | uuid.UUID) -> bool:
    """True if `superior` is strictly above `subordinate` in the org tree.

    A `user_closure` row exists with `ancestor_id = superior`, `descendant_id = subordinate`, `depth > 0`.
    Used only for the task dashboard (2.4) and `can_see`; never for conversation access.
    """
    raise NotImplementedError


def can_access(db: Session, user: User, conversation: Conversation, at: datetime | None = None) -> bool:
    """True if `user` may read `conversation` (spec 1.5).

    `(kind = 'channel' AND is_public) OR is_member(user, conversation, at)`. The user must be active.
    Archived conversations stay readable to whoever could read them before archiving.

    Every read path routes through this: message lists, threads, embeds (resolved for the viewer,
    not the author), search results, file downloads and conversation task tabs. Pass `at` when
    checking access to a specific message (its `created_at`), so someone who left keeps what was
    posted before they left and nothing after.
    """
    raise NotImplementedError


def can_see(db: Session, user: User, task: Task) -> bool:
    """True if `user` may see `task` (spec 2.3). Any of:

    - `user` is the assignee;
    - `is_superior(user, assignee)`;
    - `user.department_id = assignee.department_id` (the task is in their department channel);
    - `user` is currently a member of `task.source_conversation_id`.

    Seeing a task does not imply seeing its source message: the embed is checked separately with
    `can_access` and renders as the private stub when that fails.
    """
    raise NotImplementedError


def can_assign(db: Session, assigner: User, assignee: User, conversation: Conversation) -> bool:
    """True if `assigner` may give `assignee` a task spawned in `conversation` (spec 2.7).

    `is_member(assigner, conversation) AND (is_member(assignee, conversation)
    OR assignee.manager_id = assigner.id)`. The exception is the direct manager only (one level,
    not the closure). Called on task create, on assignee change, and on suggestion accept, where
    the assigner is the accepting human. The AI never assigns, so it gets no exception.
    """
    raise NotImplementedError


def ai_can_read(db: Session, conversation: Conversation) -> bool:
    """True if the AI worker may consume events from `conversation` (spec 3.5).

    `department` and `channel`: `conversation.ai_enabled`. `dm`: both members' open
    `conversation_members.ai_opt_in` are true. Skipped events are logged by the worker, not lost.
    """
    raise NotImplementedError
