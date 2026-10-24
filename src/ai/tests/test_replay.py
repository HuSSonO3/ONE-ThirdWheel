import json
import uuid
from pathlib import Path

import pytest

from ai import eval as evaluation
from ai.model import Call, RecordedResponses
from ai.scoring import Scores, arguments_match


def test_recording_keys_do_not_reuse_created_calls_for_edits():
    ident = str(uuid.uuid4())
    model = RecordedResponses({ident: [{"name": "request_leave", "arguments": {"user_hint": "A"}}]})
    tools: list[dict] = []
    created = json.dumps({"new_events": [{"type": "message.created", "payload": {"message_id": ident}}]})
    edited = json.dumps({"new_events": [{"type": "message.updated", "payload": {"message_id": ident}}]})
    assert model.choose(created, tools)[0].name == "request_leave"
    assert model.choose(edited, tools)[0].name == "no_action"


def test_bad_recordings_rejected(tmp_path):
    path = tmp_path / "responses.json"
    path.write_text('{"source": "not calls"}')
    with pytest.raises(ValueError, match="list"):
        RecordedResponses.from_path(path)


def call(assignee, *, due_at=None):
    payload = {"assignee_id": assignee, "due_at": due_at}
    return {"tool_name": "propose_task", "status": "executed", "arguments": {},
            "result": {"output": {"proposal": payload}}}


def test_argument_scoring_catches_wrong_assignee_date_and_double_count():
    scores = Scores()
    label = {"case": "two", "expected_tool": "propose_task",
             "expected": {"calls": [{"assignee_id": "A", "due_at": "2026-10-22"}, {"assignee_id": "B"}]}}
    scores.observe(label, [call("A", due_at="2026-10-22T10:00:00Z"), call("A")], [])
    report = scores.report()
    assert report["task_precision"] == .5 and report["task_recall"] == .5
    assert report["labelled_argument_accuracy"] == 0
    assert not arguments_match({"due_at": "2026-10-23"}, call("A", due_at="2026-10-22T10:00:00Z"), [])


def test_fixture_task_status_is_not_future_final_status():
    tasks = [{"id": "task", "source_conversation_id": "conv", "created_at": "2026-10-20T00:00:00Z",
              "status": "done", "title": "Review", "assignee_id": "A", "project": None,
              "source_message_ids": ["source"], "history": [
                  {"field": "status", "old_value": "open", "new_value": "done",
                   "changed_at": "2026-10-23T00:00:00Z"}]}]
    assert not evaluation.tasks_at(tasks, "conv", "2026-10-19T00:00:00Z")
    assert evaluation.tasks_at(tasks, "conv", "2026-10-22T00:00:00Z")[0]["status"] == "open"
    assert not evaluation.tasks_at(tasks, "conv", "2026-10-24T00:00:00Z")


def test_full_fixture_worker_replay_records_every_call_and_timed_source(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(evaluation.time, "sleep", sleeps.append)
    report = evaluation.replay(lambda _: RecordedResponses({}), verbose=False, interval=.001)
    assert report["messages"] == 387 and report["failed_inputs"] == 0
    assert len(sleeps) == len(evaluation.fixture_events())
    assert report["last_event_id"] == len(evaluation.fixture_events())
    assert len(report["cases"]) == 24
    assert sum(len(r["tool_calls"]) for r in report["runs"]) == report["tool_choices"]["no_action"]


def test_recorded_source_makes_real_proposal_with_no_model_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ident = "6a44d87e-b3e4-5ce5-b882-63a192dcf5d3"
    model = RecordedResponses({ident: [{"name": "propose_task", "arguments": {
        "title": "Update GA4 analytics snippet on landing page", "description_md": "The GA4 tag is outdated.",
        "source_message_ids": [ident], "suggested_assignee": "Ethan Novak", "confidence": .9,
    }}]})
    report = evaluation.replay(lambda _: model, verbose=False)
    assert report["failed_inputs"] == 0
    assert report["tool_choices"]["propose_task"] == 1
    assert report["recorded_proposals"] == 1
    row = next(r for r in report["cases"] if r["case"] == "non_member")
    assert row["arguments_correct"]


def test_fixture_failure_rolls_back_and_stops_cursor():
    class BrokenModel:
        def choose(self, prompt, tools):
            return [Call("unknown_tool", {})]

    report = evaluation.replay(lambda _: BrokenModel(), verbose=False, stop_on_failure=True)
    assert report["failed_inputs"] == 1
    assert report["last_event_id"] < report["runs"][-1]["from_event_id"]
    assert report["runs"][-1]["tool_calls"][0]["result"]["error"] == "unknown_tool"


def test_reference_calls_cover_all_tools_and_old_reaction_source():
    model = RecordedResponses.from_path(Path(__file__).parent / "data" / "reference_calls.json")
    report = evaluation.replay(lambda _: model, verbose=False)
    assert report["failed_inputs"] == 0
    assert set(report["tool_choices"]) == {
        "propose_task", "propose_status_change", "no_action", "request_leave", "submit_claim", "schedule_meeting"}
    assert report["task_precision"] == 1
    for name in ("two_tasks", "clear_ask", "non_member", "closes_task", "reaction_closes_task",
                 "leave_request", "expense_claim", "meeting"):
        assert next(r for r in report["cases"] if r["case"] == name)["arguments_correct"], name


def test_markdown_summary_lists_metrics_tools_and_cases():
    model = RecordedResponses.from_path(Path(__file__).parent / "data" / "reference_calls.json")
    text = evaluation.markdown(evaluation.replay(lambda _: model, verbose=False), "recorded")
    assert "| task precision | 1.00 |" in text
    assert "| schedule_meeting | 1 |" in text
    assert "| reaction_closes_task | propose_status_change |" in text
    assert "not model quality" in text
