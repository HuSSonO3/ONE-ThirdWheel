"""Replay shared fixtures through the real dispatcher with a recording write boundary.

python -m ai.eval                         # no-action baseline, no network
python -m ai.eval --live                  # actual model evaluation (billable)
python -m ai.eval --responses calls.json  # explicit saved tool calls by message id
"""

import argparse
import json
import time
import uuid
from pathlib import Path

from ai.context import Context, batch_messages
from ai.model import Model, NativeModel, RecordedResponses
from ai.scoring import Scores
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


def tasks_at(tasks: list[dict], conversation_id: str, timestamp: str) -> list[dict]:
    """Reconstruct the fixture's task status before the signal being evaluated."""
    result = []
    for task in tasks:
        if task["source_conversation_id"] != conversation_id or task["created_at"] > timestamp:
            continue
        history = sorted(task.get("history", []), key=lambda h: h["changed_at"])
        changes = [h for h in history if h["field"] == "status"]
        status = changes[0]["old_value"] if changes else task["status"]
        for change in changes:
            if change["changed_at"] < timestamp:
                status = change["new_value"]
        if status in ("open", "in_progress"):
            result.append({"task_id": task["id"], "title": task["title"], "status": status,
                           "assignee_id": task["assignee_id"], "project": task["project"],
                           "source_message_ids": task["source_message_ids"]})
    return result


def replay(model_factory, *, verbose: bool = True, interval: float = 0, stop_on_failure: bool = False) -> dict:
    """Labels are loaded only for scoring, never made available to the model."""
    convs = {c["id"]: c for c in load("conversations")}
    departments, users, tasks, suggestions = (load(n) for n in ("departments", "users", "tasks", "suggestions"))
    labels = {c["message_id"]: c for c in load("expected")["cases"]}
    backend = RecordingBackend()
    audits: list[dict] = []
    histories: dict[str, list[dict]] = {}
    scores = Scores()
    skipped = failures = last_event_id = 0
    runs, skipped_events = [], []
    for event_id, (message, event, trigger) in enumerate(fixture_events(), 1):
        if interval:
            time.sleep(interval)
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
            skipped_events.append({"event_id": event_id, "conversation_id": conv["id"], "reason": "ai_cannot_read"})
            scores.observe(label, [], users, skipped=True)
            last_event_id = event_id
            continue
        history = histories.setdefault(conv["id"], [])
        history.append(event)
        if trigger == "message.deleted":
            last_event_id = event_id
            continue
        directory = [{k: u.get(k) for k in ("id", "name", "job_title", "department_id", "manager_id", "timezone")}
                     | {"is_member": u["id"] in members} for u in users if u.get("active", True)]
        open_tasks = tasks_at(tasks, conv["id"], event["created_at"])
        pending = [{"kind": p["kind"], "payload": p["payload"]} for p in suggestions
                   if p["conversation_id"] == conv["id"] and p["created_at"] <= event["created_at"]
                   and (p["status"] == "pending" or (p.get("decided_at") or "") > event["created_at"])
                   and p.get("expires_at", "9999") > event["created_at"]]
        pending += [{"kind": p["kind"], "payload": p["payload"]} for p in backend.calls
                    if str(p["conversation_id"]) == conv["id"]]
        context = Context({"id": conv["id"], "kind": conv["kind"], "description": conv["description"]},
                          [event], batch_messages(history, [event]), directory, open_tasks, pending,
                          sorted({t["project"] for t in tasks if t["project"]
                                  and t["source_conversation_id"] == conv["id"]}), departments)
        before = len(audits)
        writes_before = len(backend.calls)
        run_id = uuid.uuid4()
        status = "succeeded"
        try:
            process(context, model_factory(message["id"]), ToolContext(
                run_id, uuid.UUID(conv["id"]), DEFAULT_SCOPES, backend), audits.append)
        except (RuntimeError, ValueError):
            failures += 1
            status = "failed"
            del backend.calls[writes_before:]
        chosen = audits[before:]
        if status == "failed":
            for record in chosen:
                if record["status"] == "executed":
                    record["result"]["output"]["rolled_back"] = True
        runs.append({"run_id": str(run_id), "from_event_id": event_id, "to_event_id": event_id,
                     "status": status, "tool_calls": chosen})
        scores.observe(label, chosen, users)
        if status == "failed" and stop_on_failure:
            break
        if status == "succeeded":
            last_event_id = event_id
    report = {"messages": len(load("messages")), "skipped": skipped, "failed_inputs": failures,
              **scores.report(), "recorded_proposals": len(backend.calls),
              "last_event_id": last_event_id, "runs": runs, "skipped_events": skipped_events}
    if verbose:
        for row in scores.rows:
            print(f"{row['case']:27} expected={str(row['expected']):24} "
                  f"actual={','.join(row['actual']) or 'skipped'} arguments={row['arguments_correct']}")
        print(json.dumps({k: v for k, v in report.items() if k not in ("runs", "cases", "skipped_events")}, indent=2))
    return report


def markdown(report: dict, mode: str) -> str:
    """Compact PR-comment summary; visibility only, never a pass/fail gate."""
    lines = [f"### AI eval ({mode})", "",
             "| Metric | Value |", "| --- | --- |"]
    for key in ("task_precision", "task_recall", "labelled_tool_accuracy", "labelled_argument_accuracy"):
        lines.append(f"| {key.replace('_', ' ')} | {report[key]:.2f} |")
    for key in ("messages", "skipped", "failed_inputs", "recorded_proposals"):
        lines.append(f"| {key.replace('_', ' ')} | {report[key]} |")
    lines += ["", "| Tool | Calls |", "| --- | --- |"]
    lines += [f"| {name} | {count} |" for name, count in sorted(report["tool_choices"].items())]
    lines += ["", "| Case | Expected | Actual | Arguments |", "| --- | --- | --- | --- |"]
    for row in report["cases"]:
        actual = ", ".join(row["actual"]) or "skipped"
        correct = "yes" if row["arguments_correct"] else "no"
        lines.append(f"| {row['case']} | {row['expected']} | {actual} | {correct} |")
    if mode != "live":
        lines += ["", "_Recorded replay: measures the pipeline, not model quality._"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true")
    group.add_argument("--responses", type=Path)
    parser.add_argument("--output", type=Path, help="Write full run/tool/case results as JSON.")
    parser.add_argument("--markdown", type=Path, help="Write a PR-comment summary as Markdown.")
    args = parser.parse_args()
    model: Model
    if args.live:
        model = NativeModel()
        print("LIVE model evaluation; sends AI-readable fixture conversations to the configured provider.")
        report = replay(lambda _: model)
    else:
        model = RecordedResponses.from_path(args.responses) if args.responses else RecordedResponses({})
        print("RECORDED replay" if args.responses else "NO-ACTION BASELINE — pipeline smoke test, not model quality.")
        report = replay(lambda _: model)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        mode = "live" if args.live else "recorded" if args.responses else "no-action baseline"
        args.markdown.write_text(markdown(report, mode))


if __name__ == "__main__":
    main()
