import json
import uuid
from dataclasses import replace

import pytest

from ai.context import Context, event_messages
from ai.dispatcher import dispatch
from ai.model import Call, RecordedModel
from ai.storage import RecordingBackend
from ai.tools.base import DEFAULT_SCOPES, Scope, ToolContext
from ai.tools.registry import registry
from ai.worker import process

MID, UID, CID, TID = [str(uuid.uuid4()) for _ in range(4)]


@pytest.fixture
def context():
    message = {"message_id": MID, "seq": 1, "author_id": UID, "body_md": "Dana Kim, review the launch",
               "mentions": [{"kind": "user", "user_id": UID}], "parent_id": None}
    return Context({"id": CID, "kind": "channel", "description": ""},
                   [{"type": "message.created", "actor_id": UID, "payload": message}],
                   [message], [{"id": UID, "name": "Dana Kim", "is_member": True, "manager_id": None}],
                   [], [], [])


@pytest.fixture
def args():
    return {"title": "Review the launch", "description_md": "", "source_message_ids": [MID],
            "suggested_assignee": "Dana Kim", "confidence": .9}


def execute(context, call, scopes=DEFAULT_SCOPES):
    backend = RecordingBackend()
    audit: list[dict] = []
    result = dispatch(call, registry(context), ToolContext(uuid.uuid4(), uuid.UUID(CID), scopes, backend), audit.append)
    assert len(audit) == 1
    return result, backend, audit[0]


def test_proposal_not_task(context, args):
    result, backend, audit = execute(context, Call("propose_task", args))
    assert result.status == "executed" and audit["scope_check"]
    payload = backend.calls[0]["payload"]
    assert payload["assignee_id"] == UID and payload["assignee_is_member"]
    assert backend.calls[0]["kind"] == "task"


@pytest.mark.parametrize("changes", [
    {"confidence": 2}, {"title": ""}, {"source_message_ids": ["bad"]},
    {"due_at": "Friday"}, {"unknown": True}, {"suggested_assignee": 123},
])
def test_schema_validation(context, args, changes):
    result, backend, audit = execute(context, Call("propose_task", args | changes))
    assert result.error == "invalid_arguments" and not backend.calls
    assert audit["status"] == "failed"


@pytest.mark.parametrize("call,error", [
    (Call("missing", {}), "unknown_tool"),
    (Call("propose_task", None), "invalid_arguments"),
    (Call("no_action", []), "invalid_arguments"),
])
def test_all_invalid_calls_audited(context, call, error):
    assert execute(context, call)[0].error == error


def test_scope_denial(context, args):
    result, backend, audit = execute(context, Call("propose_task", args), frozenset())
    assert result.status == "denied" and not backend.calls and not audit["scope_check"]


def test_stub_denied_then_stubbed(context):
    call = Call("request_leave", {"user_hint": "Dana", "start_date": "2026-11-03", "end_date": "2026-11-05"})
    assert execute(context, call)[0].status == "denied"
    result, backend, _ = execute(context, call, frozenset({Scope.LEAVE_REQUEST}))
    assert result.status == "stubbed" and not backend.calls


def test_non_member_kept_for_human(context, args):
    context.users[0]["is_member"] = False
    _, backend, _ = execute(context, Call("propose_task", args))
    assert backend.calls[0]["payload"]["assignee_is_member"] is False


def test_dedupe_within_run(context, args):
    backend = RecordingBackend()
    audit: list[dict] = []
    process(context, RecordedModel([Call("propose_task", args)] * 2),
            ToolContext(uuid.uuid4(), uuid.UUID(CID), DEFAULT_SCOPES, backend), audit.append)
    assert len(backend.calls) == 1 and len(audit) == 2
    assert audit[-1]["result"]["output"]["deduplicated"]


def test_two_tasks_same_source_not_collapsed(context, args):
    other = str(uuid.uuid4())
    context.users.append({"id": other, "name": "Bob Lee", "is_member": True})
    context.messages[0]["mentions"].append({"kind": "user", "user_id": other})
    _, backend, _ = execute(context, Call("propose_task", args))
    assert len(backend.calls) == 1
    _, backend, _ = execute(context, Call("propose_task", args | {
        "suggested_assignee": "Bob Lee", "title": "Write test coverage"}))
    assert len(backend.calls) == 1


def test_hallucinated_source_rejected(context, args):
    result, backend, _ = execute(context, Call("propose_task", args | {"source_message_ids": [str(uuid.uuid4())]}))
    assert result.error == "invalid_source" and not backend.calls


def test_no_history_only_actions(context, args):
    context.events = []
    assert execute(context, Call("propose_task", args))[0].error == "no_new_evidence"


def test_project_requires_existing_and_named(context, args):
    context.projects = ["launch"]
    _, backend, _ = execute(context, Call("propose_task", args | {"project": "other"}))
    assert backend.calls[0]["payload"]["project"] is None


def test_status_change_does_not_update_task(context):
    context.tasks = [{"task_id": TID, "title": "Review", "status": "open",
                      "source_message_ids": [MID], "assignee_id": UID}]
    args = {"task_id": TID, "new_status": "done", "source_message_ids": [MID], "confidence": .95}
    result, backend, _ = execute(context, Call("propose_status_change", args))
    assert result.status == "executed" and backend.calls[0]["kind"] == "status_change"
    assert context.tasks[0]["status"] == "open"
    assert execute(context, Call("propose_status_change", args))[0].output["deduplicated"]


def test_foreign_task_rejected(context):
    call = Call("propose_status_change", {
        "task_id": TID, "new_status": "done", "source_message_ids": [MID], "confidence": .9})
    assert execute(context, call)[0].error == "invalid_task"


def test_context_cap_and_snapshot_fold(context):
    prompt = context.prompt(5000)
    assert len(prompt.encode()) <= 5000 and json.loads(prompt)["new_events"]
    with pytest.raises(ValueError, match="context_too_large"):
        replace(context, events=[{"payload": {"body_md": "x" * 10000}}]).prompt(1000)
    events = [{"type": "message.created", "payload": {"message_id": MID, "body_md": "old", "seq": 1}},
              {"type": "message.updated", "payload": {"message_id": MID, "body_md": "new"}},
              {"type": "message.deleted", "payload": {"message_id": MID}}]
    assert event_messages(events[:-1])[0]["body_md"] == "new" and not event_messages(events)
