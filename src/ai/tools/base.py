"""Tool protocol shared by every AI tool. See contracts/tool-interface.md."""
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolResult:
    ok: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]
    required_scope: str

    def execute(self, args: dict[str, Any], ctx: Any) -> ToolResult: ...
