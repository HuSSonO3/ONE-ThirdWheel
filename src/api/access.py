"""Access rules. Signatures are the contract (plan.md §3 Day 1); bodies are Phase 1 BE work."""


def can_access(user, conversation) -> bool:
    """True if `user` may read `conversation` (membership honouring joined_at/left_at)."""
    raise NotImplementedError


def can_see(user, task) -> bool:
    """True if `user` may see `task` (assignee, creator, channel member, or manager chain)."""
    raise NotImplementedError


def can_assign(assigner, assignee, channel) -> bool:
    """True if `assigner` may assign a task in `channel` to `assignee`.

    Assignee must be a channel member, except the assigner may assign to a direct report.
    """
    raise NotImplementedError
