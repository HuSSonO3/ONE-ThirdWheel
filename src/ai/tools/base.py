"""Tool protocol shared by every AI tool. Contract: contracts/tool-interface.md."""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol


class Scope(StrEnum):
    CONVERSATIONS_READ = "conversations:read"
    SUGGESTIONS_CREATE = "suggestions:create"
    SUGGESTIONS_STATUS = "suggestions:status"
    LEAVE_REQUEST = "leave:request"
    CLAIMS_SUBMIT = "claims:submit"
    CALENDAR_CREATE = "calendar:create"


DEFAULT_SCOPES = frozenset({Scope.CONVERSATIONS_READ, Scope.SUGGESTIONS_CREATE, Scope.SUGGESTIONS_STATUS})

# Same values as ai_tool_calls.status.
ToolStatus = Literal["executed", "denied", "failed", "stubbed"]


@dataclass(frozen=True)
class ToolResult:
    status: ToolStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Backend(Protocol):
    """What tools may do to the rest of the system. Phase 1: a recording mock; later: api's service layer."""

    def create_proposal(
        self,
        *,
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        kind: Literal["task", "status_change"],
        payload: dict[str, Any],
        confidence: float | None,
    ) -> uuid.UUID: ...


@dataclass(frozen=True)
class ToolContext:
    run_id: uuid.UUID
    conversation_id: uuid.UUID
    scopes: frozenset[str]
    backend: Backend


class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]
    required_scope: Scope | None  # None only for no_action

    def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult: ...
