import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from ai.model import Call, RecordedModel
from ai.worker import run_once
from api.models import AiAgent, AiProposal, AiRun, AiToolCall, Conversation, Event, EventConsumer, Task
from api.schemas.contract import MessageCreate
from api.services import messages, suggestions
from tests.conftest import ids, requires_db

pytestmark = requires_db


def setup_event(session, *, conv="website", body="Dana Kim, please review the MVP"):
    from api.models import User

    cursor = session.get(EventConsumer, "ai")
    cursor.last_event_id = session.scalar(select(func.max(Event.id))) or 0
    conversation = session.get(Conversation, uuid.UUID(ids.conv(conv)))
    # Fixture Alice belongs to website.
    user = session.get(User, uuid.UUID(ids.user("alice")))
    message, _ = messages.create(session, user, conversation, MessageCreate(
        body_md=body, client_id=uuid.uuid4()))
    session.flush()
    return cursor, conversation, message, user


def task_call(message):
    return Call("propose_task", {"title": "Review the MVP", "description_md": "Review requested.",
                                 "source_message_ids": [str(message.id)], "suggested_assignee": "Dana Kim",
                                 "confidence": .9})


def test_seeded_worker_proposes_then_human_accepts(session):
    cursor, conv, msg, alice = setup_event(session)
    count = session.scalar(select(func.count()).select_from(Task))
    model = RecordedModel([task_call(msg)])
    assert run_once(session, model, debounce_seconds=0) == "processed"
    proposal = session.scalar(select(AiProposal).where(AiProposal.run_id.is_not(None))
                              .order_by(AiProposal.created_at.desc()))
    assert proposal and proposal.conversation_id == conv.id
    assert session.scalar(select(func.count()).select_from(Task)) == count
    audit = session.scalar(select(AiToolCall).where(AiToolCall.run_id == proposal.run_id))
    assert audit.status == "executed"
    assert cursor.last_event_id >= 774
    # Existing BE does the assignment checks, creates task and emits events.
    proposal, task = suggestions.accept(session, alice, proposal.id)
    assert proposal.status == "accepted" and task.created_by_ai and task.created_by == alice.id
    assert task.source_conversation_id == conv.id
    assert "password_hash" not in model.inputs[0] and "email" not in model.inputs[0]


def test_failure_rolls_back_proposal_but_keeps_audit_and_cursor(session):
    cursor, _, msg, _ = setup_event(session)
    before = cursor.last_event_id
    model = RecordedModel([task_call(msg), Call("unknown", {})])
    assert run_once(session, model, debounce_seconds=0) == "failed"
    assert cursor.last_event_id == before
    run = session.scalar(select(AiRun).order_by(AiRun.started_at.desc()))
    assert run.status == "failed"
    assert not session.scalar(select(AiProposal).where(AiProposal.run_id == run.id))
    assert len(session.scalars(select(AiToolCall).where(AiToolCall.run_id == run.id)).all()) == 2
    assert run_once(session, RecordedModel([task_call(msg)]), debounce_seconds=0) == "processed"


def test_disabled_channel_never_calls_model(session):
    cursor, conv, msg, _ = setup_event(session)
    conv.ai_enabled = False
    session.flush()
    model = RecordedModel([task_call(msg)])
    assert run_once(session, model, debounce_seconds=0) == "skipped"
    assert not model.inputs and cursor.last_event_id > 774


def test_debounce_does_not_advance_cursor(session):
    cursor, _, msg, _ = setup_event(session)
    before = cursor.last_event_id
    model = RecordedModel([task_call(msg)])
    assert run_once(session, model) == "waiting"
    assert cursor.last_event_id == before and not model.inputs


def test_missing_scope_is_terminal_audited_denial(session):
    cursor, _, msg, _ = setup_event(session)
    agent = session.scalar(select(AiAgent))
    agent.scopes = ["conversations:read"]
    session.flush()
    before = cursor.last_event_id
    assert run_once(session, RecordedModel([task_call(msg)]), debounce_seconds=0) == "processed"
    call = session.scalar(select(AiToolCall).order_by(AiToolCall.created_at.desc()))
    assert call.status == "denied" and cursor.last_event_id > before


def test_scope_revocation_during_model_call(session):
    _, _, msg, _ = setup_event(session)
    agent = session.scalar(select(AiAgent))

    class RevokingModel:
        def choose(self, prompt, tools):
            agent.scopes = ["conversations:read"]
            session.flush()
            return [task_call(msg)]

    assert run_once(session, RevokingModel(), debounce_seconds=0) == "processed"
    call = session.scalar(select(AiToolCall).order_by(AiToolCall.created_at.desc()))
    assert call.status == "denied"


def test_dm_double_opt_in(session):
    from api.models import ConversationMember

    cursor = session.get(EventConsumer, "ai")
    cursor.last_event_id = session.scalar(select(func.max(Event.id)))
    conv = session.scalar(select(Conversation).where(Conversation.kind == "dm"))
    members = session.scalars(select(ConversationMember).where(
        ConversationMember.conversation_id == conv.id, ConversationMember.left_at.is_(None))).all()
    members[0].ai_opt_in, members[1].ai_opt_in = True, False
    e = Event(type="message.created", conversation_id=conv.id, actor_id=members[0].user_id,
              subject_type="message", subject_id=uuid.uuid4(), created_at=datetime.now(UTC),
              payload={"message_id": str(uuid.uuid4()), "body_md": "Private secret"})
    session.add(e)
    session.flush()
    model = RecordedModel([Call("no_action", {"reason": "Nothing"})])
    assert run_once(session, model, debounce_seconds=0) == "skipped" and not model.inputs
    members[1].ai_opt_in = True
    session.flush()
    cursor.last_event_id = e.id - 1
    assert run_once(session, model, debounce_seconds=0) == "processed" and model.inputs
    assert json.loads(model.inputs[0])["conversation"]["kind"] == "dm"
