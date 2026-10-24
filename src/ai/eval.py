"""Replay shared fixtures through the real dispatcher with a recording write boundary.

python -m ai.eval                         # no-action baseline, no network
python -m ai.eval --live                  # actual model evaluation (billable)
python -m ai.eval --responses calls.json  # explicit saved tool calls by message id
"""

import argparse
import json
import uuid
from collections import Counter
from pathlib import Path

from ai.context import Context, event_messages
from ai.model import Call, NativeModel, RecordedModel
from ai.storage import RecordingBackend
from ai.tools.base import DEFAULT_SCOPES, ToolContext
from ai.worker import process

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def fixture_events() -> list[tuple[dict, dict, str]]:
    """Replay input built only from fixtures, independent of expected labels."""
    from api.text import extract

    stream = []
    for message in load("messages"):
        body = message["edits"][0]["prior_body_md"] if message["edits"] else message["body_md"]
        payload = {k: message[k] for k in ("seq", "parent_id", "author_id")}
        payload.update(message_id=message["id"], body_md=body, mentions=extract(body)[0], refs=extract(body)[1])
        base = {"type": "message.created", "actor_id": message["author_id"],
                "created_at": message["created_at"], "payload": payload}
        stream.append((message, base, "message"))
        for i, edit in enumerate(message["edits"]):
            body = message["edits"][i + 1]["prior_body_md"] if i + 1 < len(message["edits"]) else message["body_md"]
            stream.append((message, {**base, "type": "message.updated", "created_at": edit["edited_at"],
                                    "payload": {**payload, "body_md": body, "prior_body_md": edit["prior_body_md"],
                                                "mentions": extract(body)[0], "refs": extract(body)[1]}},
                           "message.updated"))
        for reaction in message["reactions"]:
            stream.append((message, {**base, "type": "reaction.added", "actor_id": reaction["user_id"],
                                    "created_at": reaction["created_at"],
                                    "payload": {"message_id": message["id"], **reaction}},
                           "reaction:" + reaction["emoji"]))
        if message["deleted_at"]:
            stream.append((message, {**base, "type": "message.deleted", "created_at": message["deleted_at"],
                                    "payload": {"message_id": message["id"]}}, "message.deleted"))
    return sorted(stream, key=lambda item: item[1]["created_at"])


def replay(model_factory, *, verbose: bool = True) -> dict:
    """Labels are loaded only for scoring, never made available to the model."""
    convs = {c["id"]: c for c in load("conversations")}
    departments, users, tasks, suggestions = (load(n) for n in ("departments", "users", "tasks", "suggestions"))
    labels = {c["message_id"]: c for c in load("expected")["cases"]}
    backend, audits, histories = RecordingBackend(), [], {}
    tp = fp = fn = tool_correct = labelled = skipped = failures = 0
    for event_id, (message, event, trigger) in enumerate(fixture_events(), 1):
        event["id"] = event_id
        conv = convs[message["conversation_id"]]
        members = {m["user_id"] for m in conv["members"] if not m.get("left_at")}
        open_members = [m for m in conv["members"] if not m.get("left_at")]
        readable = (len(open_members) == 2 and all(m["ai_opt_in"] for m in open_members)) \
            if conv["kind"] == "dm" else conv["ai_enabled"]
        label = labels.get(message["id"])
        if label and label["trigger"] != trigger:
            label = None
        if not readable:
            skipped += 1
            if label:
                labelled += 1
                tool_correct += label["expected_tool"] is None
            continue
        history = histories.setdefault(conv["id"], [])
        history.append(event)
        if trigger == "message.deleted":
            continue
        directory = [{k: u.get(k) for k in ("id", "name", "job_title", "department_id", "manager_id", "timezone")}
                     | {"is_member": u["id"] in members} for u in users if u.get("active", True)]
        open_tasks = [{"task_id": t["id"], **t} for t in tasks
                      if t["source_conversation_id"] == conv["id"] and t["status"] in ("open", "in_progress")]
        pending = [{"kind": p["kind"], "payload": p["payload"]} for p in suggestions
                   if p["conversation_id"] == conv["id"] and p["status"] == "pending"]
        pending += [{"kind": p["kind"], "payload": p["payload"]} for p in backend.calls
                    if str(p["conversation_id"]) == conv["id"]]
        context = Context({"id": conv["id"], "kind": conv["kind"], "description": conv["description"]},
                          [event], event_messages(history), directory, open_tasks, pending,
                          sorted({t["project"] for t in tasks if t["project"]
                                  and t["source_conversation_id"] == conv["id"]}), departments)
        before = len(audits)
        try:
            process(context, model_factory(message["id"]), ToolContext(
                uuid.uuid4(), uuid.UUID(conv["id"]), DEFAULT_SCOPES, backend), audits.append)
        except (RuntimeError, ValueError):
            failures += 1
        chosen = audits[before:]
        predicted = sum(c["tool_name"] == "propose_task" for c in chosen)
        expected = 0 if not label or label["expected_tool"] != "propose_task" else \
            len(label["expected"].get("calls", [None]))
        tp += min(predicted, expected)
        fp += max(0, predicted - expected)
        fn += max(0, expected - predicted)
        if label:
            labelled += 1
            tool_correct += any(c["tool_name"] == label["expected_tool"] for c in chosen)
            if verbose:
                print(f"{label['case']:27} expected={label['expected_tool']:24} "
                      f"actual={','.join(c['tool_name'] + ':' + c['status'] for c in chosen) or 'error'}")
    report = {"messages": len(load("messages")), "skipped": skipped, "failed_inputs": failures,
              "task_precision": tp / (tp + fp) if tp + fp else 0.0,
              "task_recall": tp / (tp + fn) if tp + fn else 0.0,
              "labelled_tool_accuracy": tool_correct / labelled if labelled else 0.0,
              "tool_choices": dict(Counter(c["tool_name"] for c in audits)),
              "recorded_proposals": len(backend.calls)}
    if verbose:
        print(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true")
    group.add_argument("--responses", type=Path)
    args = parser.parse_args()
    if args.live:
        model = NativeModel()
        print("LIVE model evaluation; sends AI-readable fixture conversations to the configured provider.")
        replay(lambda _: model)
    else:
        saved = json.loads(args.responses.read_text()) if args.responses else {}
        print("RECORDED replay" if saved else "NO-ACTION BASELINE — pipeline smoke test, not model quality.")
        replay(lambda ident: RecordedModel([Call(c["name"], c["arguments"]) for c in saved.get(
            ident, [{"name": "no_action", "arguments": {"reason": "Offline baseline"}}])]))


if __name__ == "__main__":
    main()
