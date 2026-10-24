# Tool interface

The AI acts only through tools (spec 3.4). This document is the contract. `ai/tools/base.py` is its
code form, and the two must agree.

## `Tool`

| Member | Type | Meaning |
| --- | --- | --- |
| `name` | `str` | Unique, snake_case. Passed to the model as the tool name. |
| `description` | `str` | Shown to the model. States when to use the tool and when not to. |
| `input_schema` | `dict` (JSON Schema, draft 2020-12) | The model's arguments. `additionalProperties: false`. |
| `required_scope` | `Scope` | Checked by the dispatcher before `execute`. |
| `execute(args, ctx)` | `-> ToolResult` | Runs the action through the service layer (`ctx.backend`), never by writing tables directly. |

Tools are stateless; everything they need arrives in `args` and `ctx`.

## `ToolContext`

| Field | Meaning |
| --- | --- |
| `run_id` | The `ai_runs.id` of the batch being processed. |
| `conversation_id` | The conversation the batch came from. Tools never act elsewhere. |
| `scopes` | The agent's current scopes (`ai_agent.scopes`). |
| `backend` | A `Backend` implementation. Phase 1 uses a recording mock; after Merge One it is the real service layer. Switching is a config change. |

## Dispatcher

For each tool call the model returns, the dispatcher:

1. looks up the tool by name (unknown name → `failed`, `error = "unknown_tool"`);
2. validates `args` against `input_schema` (invalid → `failed`, `error = "invalid_arguments"`, with the
   validation message in `output.detail`);
3. checks that `required_scope` is in `ctx.scopes` (missing → `denied`, never retried);
4. calls `execute`; an exception becomes `failed` with `error = "exception"`;
5. writes one `ai_tool_calls` row for every call, including denials and failures:
   `tool_name`, `arguments`, `scope_check` (the step 3 result), `status`, `result = {output, error}`.

### Result shape

```json
{ "status": "executed | denied | failed | stubbed", "output": { }, "error": "string | null" }
```

`status` values match `ai_tool_calls.status`. `stubbed` is returned by tools whose target system does
not exist yet: the call is recorded and nothing else happens.

## Scopes

| Scope | Granted by default | Used by |
| --- | --- | --- |
| `conversations:read` | yes | the worker's event consumption (not a tool) |
| `suggestions:create` | yes | `propose_task` |
| `suggestions:status` | yes | `propose_status_change` |
| `leave:request` | no | `request_leave` (stub) |
| `claims:submit` | no | `submit_claim` (stub) |
| `calendar:create` | no | `schedule_meeting` (stub) |

`no_action` needs no scope (`required_scope = None`). Choosing it is itself the measured outcome.

## Prototype tools

| Tool | Scope | Arguments (summary) | Effect |
| --- | --- | --- | --- |
| `propose_task` | `suggestions:create` | `title`, `description_md`, `source_message_ids[]`, `suggested_assignee` (free text: `@handle`, name, or department), `due_at?`, `project?`, `confidence` | Resolves the assignee (spec 3.3), dedupes, then creates an `ai_proposals` row (`kind = task`). |
| `propose_status_change` | `suggestions:status` | `task_id`, `new_status`, `source_message_ids[]`, `confidence` | Creates an `ai_proposals` row (`kind = status_change`). |
| `no_action` | none | `reason` | Nothing. Records that the model chose to do nothing. |
| `request_leave` | `leave:request` | `user_hint`, `start_date`, `end_date`, `reason?` | `stubbed` |
| `submit_claim` | `claims:submit` | `user_hint`, `amount`, `currency`, `description` | `stubbed` |
| `schedule_meeting` | `calendar:create` | `attendee_hints[]`, `title`, `start?`, `duration_minutes?` | `stubbed` |

The full JSON Schemas live with each tool in `ai/tools/`. They are written in Phase 1, and changing
one is a contract change.
