# Tool interface

Implemented in `src/ai/tools/base.py`. A tool has `name`, `description`, `input_schema`
(JSON Schema), `required_scope`, and `execute(args, ctx) -> ToolResult`.

TODO (Phase 0 Day 2): scope names, dispatcher result shape.
