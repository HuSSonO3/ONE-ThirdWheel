"""Parsing of message bodies: mentions and internal links (contracts/DECISIONS.md #16).

Shared by the message service and scripts/build_fixtures.py, so fixtures and live data agree.
"""

import re
from typing import TypedDict

MENTION_RE = re.compile(r"\[@[^\]]+\]\(mention:(user|department)/([0-9a-f-]{36})\)")
BROADCAST_RE = re.compile(r"(?<![\w\[])@(channel|here)\b")
REF_RE = re.compile(r"/c/([0-9a-f-]{36})(?:/m/([0-9a-f-]{36}))?|/t/([0-9a-f-]{36})")


class Mention(TypedDict):
    kind: str
    user_id: str | None
    department_id: str | None


class Ref(TypedDict):
    target_type: str
    target_id: str


def extract(body: str) -> tuple[list[Mention], list[Ref]]:
    """Mentions and internal links in `body`, in order of appearance, without duplicates."""
    mentions: list[Mention] = []
    for kind, ident in MENTION_RE.findall(body):
        m = Mention(kind=kind, user_id=ident if kind == "user" else None,
                    department_id=ident if kind == "department" else None)
        if m not in mentions:
            mentions.append(m)
    for kind in dict.fromkeys(BROADCAST_RE.findall(body)):
        mentions.append(Mention(kind=kind, user_id=None, department_id=None))

    refs: list[Ref] = []
    for conversation, message, task in REF_RE.findall(body):
        if task:
            ref = Ref(target_type="task", target_id=task)
        elif message:
            ref = Ref(target_type="message", target_id=message)
        else:
            ref = Ref(target_type="channel", target_id=conversation)
        if ref not in refs:
            refs.append(ref)
    return mentions, refs


def strip_mentions(body: str) -> str:
    """`body` with mention links removed and whitespace collapsed (used by slash commands)."""
    return " ".join(BROADCAST_RE.sub("", MENTION_RE.sub("", body)).split())


def preview(body: str, limit: int = 140) -> str:
    """Plain-ish one-line preview: mention links shown as their label, code fences dropped."""
    text = MENTION_RE.sub(lambda m: m.group(0)[1 : m.group(0).index("]")], body)
    text = re.sub(r"```.*?```", "[code]", text, flags=re.S)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
