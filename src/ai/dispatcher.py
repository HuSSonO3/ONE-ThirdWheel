"""Validate, authorize, execute and audit every native tool call, including failures."""

from collections.abc import Callable, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from ai.model import Call
from ai.tools.base import Tool, ToolContext, ToolResult


def dispatch(call: Call, tools: Mapping[str, Tool], ctx: ToolContext, audit: Callable[[dict], None]) -> ToolResult:
    tool = tools.get(call.name)
    scope_check = bool(tool and (tool.required_scope is None or tool.required_scope in ctx.scopes))
    if tool is None:
        result = ToolResult("failed", error="unknown_tool")
    elif not Draft202012Validator(tool.input_schema, format_checker=FormatChecker()).is_valid(call.arguments):
        result = ToolResult("failed", {"detail": "Arguments do not match the tool JSON schema."}, "invalid_arguments")
    elif not scope_check:
        result = ToolResult("denied", error="missing_scope")
    else:
        try:
            result = tool.execute(call.arguments, ctx)
        except Exception:
            result = ToolResult("failed", error="exception")
    audit({"tool_name": call.name, "arguments": call.arguments if isinstance(call.arguments, dict) else {},
           "scope_check": scope_check, "status": result.status,
           "result": {"output": result.output, "error": result.error}})
    return result
