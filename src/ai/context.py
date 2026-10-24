"""Provider-neutral context; only this conversation's event snapshots reach the model."""

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Context:
    conversation: dict
    events: list[dict]
    messages: list[dict]
    users: list[dict]
    tasks: list[dict]
    proposals: list[dict]
    projects: list[str]
    departments: list[dict] = field(default_factory=list)

    @property
    def source_ids(self) -> set[str]:
        """Only live messages actually included in the model input can be cited."""
        return {m["message_id"] for m in self.messages}

    def prompt(self, max_bytes: int = 24000) -> str:
        """A byte cap is deterministic and conservative (~24k tokens worst case).

        Drop oldest history, proposals, tasks, directory entries, then descriptions.
        Never truncate JSON or silently remove the triggering events. Oversized new
        input fails closed and remains retryable rather than losing a message.
        """
        data: dict[str, Any] = {
            "conversation": self.conversation, "new_events": self.events,
            "messages": list(self.messages), "participants": list(self.users),
            "open_tasks": list(self.tasks), "pending_suggestions": list(self.proposals),
            "existing_projects": self.projects, "departments": self.departments,
        }
        triggering = {e["payload"].get("message_id") for e in self.events}
        while len((encoded := json.dumps(data, ensure_ascii=True)).encode()) > max_bytes:
            history = next((i for i, m in enumerate(data["messages"]) if m["message_id"] not in triggering), None)
            if history is not None:
                data["messages"].pop(history)
            elif data["pending_suggestions"]:
                data["pending_suggestions"].pop(0)
            elif data["open_tasks"]:
                data["open_tasks"].pop(0)
            elif data["participants"]:
                data["participants"].pop(0)
            elif data["conversation"].get("description"):
                data["conversation"] = {**data["conversation"], "description": ""}
            else:
                raise ValueError("context_too_large")
        return encoded


def event_messages(events: list[dict], limit: int = 30) -> list[dict]:
    """Fold create/edit/delete snapshots without looking at future event payloads."""
    messages = {}
    for event in events:
        payload = event["payload"]
        ident = payload.get("message_id")
        if event["type"] in ("message.created", "message.updated"):
            messages[ident] = {**messages.get(ident, {}), **payload}
        elif event["type"] == "message.deleted":
            messages.pop(ident, None)
    return sorted(messages.values(), key=lambda m: m.get("seq", 0))[-limit:]
