"""The six prototype tools. All mutations go through Backend.create_proposal."""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from ai.context import Context
from ai.tools.base import Scope, ToolContext, ToolResult


def schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1, "maxLength": 4000}
SOURCES = {"type": "array", "items": {"type": "string", "format": "uuid"}, "minItems": 1,
           "maxItems": 20, "uniqueItems": True}
CONFIDENCE = {"type": "number", "minimum": 0, "maximum": 1}


def normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def resolve(hint: str | None, messages: list[dict], context: Context) -> dict | None:
    users = {u["id"]: u for u in context.users}
    hint = (hint or "").strip("@ ").casefold()
    mentioned = [users[m["user_id"]] for msg in messages for m in msg.get("mentions", [])
                 if m["kind"] == "user" and m.get("user_id") in users]
    # Multiple asks in a single message: use the model hint to disambiguate mentions.
    exact = [u for u in mentioned if hint in (u["name"].casefold(), u["id"])]
    if len(exact) == 1:
        return exact[0]
    unique = {u["id"]: u for u in mentioned}
    if len(unique) == 1:
        return next(iter(unique.values()))
    if unique:
        return None
    named = [u for u in users.values() if hint and
             (hint in (u["name"].casefold(), u["name"].split()[0].casefold(), u["id"]))]
    if len(named) == 1:
        return named[0]
    # Match whole names in source text, not arbitrary directory substrings.
    body = " ".join(m.get("body_md", "") for m in messages).casefold()
    named = [u for u in users.values() if re.search(r"\b" + re.escape(u["name"].casefold()) + r"\b", body)]
    if len(named) == 1:
        return named[0]
    departments = {m["department_id"] for msg in messages for m in msg.get("mentions", [])
                   if m["kind"] == "department"}
    departments |= {d["id"] for d in context.departments if d["name"].casefold() == hint}
    candidates = [u for u in users.values() if u.get("department_id") in departments]
    members = [u for u in candidates if u.get("is_member")]
    if len(members or candidates) == 1:
        return (members or candidates)[0]
    # Do not arbitrarily assign a department's work to its first member.
    if departments:
        return None
    authors = {m.get("author_id") for m in messages}
    managers = {users[a].get("manager_id") for a in authors if a in users}
    return users.get(next(iter(managers))) if len(managers) == 1 else None


@dataclass
class PrototypeTool:
    name: str
    description: str
    input_schema: dict
    required_scope: Scope | None
    context: Context

    def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if self.name == "no_action":
            return ToolResult("executed", {"reason": args["reason"]})
        if self.name not in ("propose_task", "propose_status_change"):
            return ToolResult("stubbed", {"implemented": False})
        sources = set(args["source_message_ids"])
        if not sources <= self.context.source_ids:
            return ToolResult("failed", error="invalid_source")
        new_sources = {e["payload"].get("message_id") for e in self.context.events
                       if e["type"] in ("message.created", "message.updated", "reaction.added", "reaction.removed")}
        if not sources & new_sources:
            return ToolResult("failed", error="no_new_evidence")
        if self.name == "propose_task":
            messages = [m for m in self.context.messages if m["message_id"] in sources]
            assignee = resolve(args.get("suggested_assignee"), messages, self.context)
            payload = {k: args.get(k) for k in ("title", "description_md", "due_at", "project", "source_message_ids")}
            payload.update(assignee_id=assignee["id"] if assignee else None,
                           assignee_is_member=bool(assignee and assignee.get("is_member")))
            # A directory-known project is not enough: it must also be named in source.
            body = " ".join(m.get("body_md", "") for m in messages).casefold()
            if payload["project"] not in self.context.projects or payload["project"].casefold() not in body:
                payload["project"] = None
            candidates = self.context.tasks + [p["payload"] for p in self.context.proposals if p["kind"] == "task"]
            duplicate = any(
                set(p.get("source_message_ids", [])) & sources and
                SequenceMatcher(None, normalized(p.get("title", "")), normalized(payload["title"])).ratio() >= .8
                or (p.get("assignee_id") == payload["assignee_id"] and
                    normalized(p.get("title", "")) == normalized(payload["title"]))
                for p in candidates
            )
            kind = "task"
        else:
            task = next((t for t in self.context.tasks if t["task_id"] == args["task_id"]), None)
            if task is None:
                return ToolResult("failed", error="invalid_task")
            messages = [m for m in self.context.messages if m["message_id"] in sources]
            linked = bool(set(task["source_message_ids"]) & sources) or any(
                m.get("parent_id") in task["source_message_ids"] or
                any(r["target_type"] == "task" and r["target_id"] == task["task_id"]
                    for r in m.get("refs", [])) for m in messages)
            if not linked:
                return ToolResult("failed", error="unlinked_status_evidence")
            evidence = [e for e in self.context.events if e["payload"].get("message_id") in sources]
            if evidence and all(e["type"].startswith("reaction.") for e in evidence) and not any(
                    e["type"] == "reaction.added" and e["payload"].get("emoji") == "✅"
                    and e["actor_id"] == task["assignee_id"] for e in evidence):
                return ToolResult("failed", error="invalid_reaction_evidence")
            payload = {k: args[k] for k in ("task_id", "new_status", "source_message_ids")}
            duplicate = task["status"] == args["new_status"] or any(
                p["kind"] == "status_change" and p["payload"]["task_id"] == args["task_id"]
                and p["payload"]["new_status"] == args["new_status"] for p in self.context.proposals)
            kind = "status_change"
        if duplicate:
            return ToolResult("executed", {"deduplicated": True})
        ident = ctx.backend.create_proposal(run_id=ctx.run_id, conversation_id=ctx.conversation_id,
                                            kind=kind, payload=payload, confidence=args["confidence"])
        self.context.proposals.append({"kind": kind, "payload": payload})
        return ToolResult("executed", {"proposal_id": str(ident)})


def registry(context: Context) -> dict[str, PrototypeTool]:
    definitions = [
        ("propose_task", "Suggest a concrete new task for human approval; never create a task.",
         schema({"title": {**TEXT, "maxLength": 300}, "description_md": {"type": "string", "maxLength": 8000},
                 "source_message_ids": SOURCES, "suggested_assignee": {"type": ["string", "null"]},
                 "due_at": {"type": ["string", "null"], "format": "date-time"},
                 "project": {"type": ["string", "null"]}, "confidence": CONFIDENCE},
                ["title", "description_md", "source_message_ids", "suggested_assignee", "confidence"]),
         Scope.SUGGESTIONS_CREATE),
        ("propose_status_change", "Suggest changing an existing task based on linked completion evidence.",
         schema({"task_id": {"type": "string", "format": "uuid"},
                 "new_status": {"enum": ["open", "in_progress", "done", "cancelled"]},
                 "source_message_ids": SOURCES, "confidence": CONFIDENCE},
                ["task_id", "new_status", "source_message_ids", "confidence"]), Scope.SUGGESTIONS_STATUS),
        ("no_action", "No actionable work in the new events.", schema({"reason": TEXT}, ["reason"]), None),
        ("request_leave", "Record a leave request; stub, no leave system is connected.",
         schema({"user_hint": TEXT, "start_date": {"type": "string", "format": "date"},
                 "end_date": {"type": "string", "format": "date"}, "reason": TEXT},
                ["user_hint", "start_date", "end_date"]), Scope.LEAVE_REQUEST),
        ("submit_claim", "Record an expense claim; stub, no expense system is connected.",
         schema({"user_hint": TEXT, "amount": {"type": "number", "exclusiveMinimum": 0},
                 "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}, "description": TEXT},
                ["user_hint", "amount", "currency", "description"]), Scope.CLAIMS_SUBMIT),
        ("schedule_meeting", "Record a meeting request; stub, no calendar is connected.",
         schema({"attendee_hints": {"type": "array", "items": TEXT, "minItems": 1}, "title": TEXT,
                 "start": {"type": ["string", "null"], "format": "date-time"},
                 "duration_minutes": {"type": "integer", "minimum": 1, "maximum": 1440}},
                ["attendee_hints", "title"]), Scope.CALENDAR_CREATE),
    ]
    return {name: PrototypeTool(name, desc, inputs, scope, context) for name, desc, inputs, scope in definitions}
