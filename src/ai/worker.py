"""Standalone polling worker. Run from src: python -m ai.worker --once."""

import argparse
import logging
import math
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.context import Context
from ai.dispatcher import dispatch
from ai.model import Model, NativeModel, RecordedResponses
from ai.storage import assemble
from ai.tools.base import ToolContext
from ai.tools.registry import registry
from api.access import ai_can_read
from api.models import AiAgent, AiRun, AiToolCall, Conversation, Event, EventConsumer
from api.services.suggestions import ServiceBackend

log = logging.getLogger(__name__)
TRIGGERS = ("message.created", "message.updated", "reaction.added", "reaction.removed")


def process(context: Context, model: Model, ctx: ToolContext, audit, authorize=None) -> None:
    tools = registry(context)
    offered = [{"type": "function", "function": {
        "name": t.name, "description": t.description, "parameters": t.input_schema,
    }} for t in tools.values()]
    calls = model.choose(context.prompt(), offered)
    if authorize:
        ctx = authorize(ctx)
    if not calls or len(calls) > 16:
        raise ValueError("invalid_tool_call_count")
    failed = False
    for call in calls:
        result = dispatch(call, tools, ctx, audit)
        failed |= result.status == "failed"
    if failed:
        raise RuntimeError("tool_call_failed")


def run_once(db: Session, model: Model, *, debounce_seconds: float = 45, batch_size: int = 100) -> str:
    """Process one contiguous same-conversation prefix; never jump over an event.

    The consumer lock serializes workers. Proposal, audit and cursor success commit
    atomically. On failure, proposals roll back while audit and failed run persist.
    Caller owns commit/rollback, making in-process integration and tests straightforward.
    """
    consumer = db.scalar(select(EventConsumer).where(EventConsumer.name == "ai")
                         .with_for_update(skip_locked=True))
    if consumer is None:
        return "busy"
    agent = db.scalar(select(AiAgent).where(AiAgent.name == "assistant"))
    if agent is None or not agent.active or "conversations:read" not in agent.scopes:
        return "paused"
    events = list(db.scalars(select(Event).where(Event.id > consumer.last_event_id)
                             .order_by(Event.id).limit(batch_size)))
    if not events:
        return "idle"
    batch = []
    for event in events:
        if event.conversation_id != events[0].conversation_id:
            break
        batch.append(event)
    conv = db.get(Conversation, batch[0].conversation_id) if batch[0].conversation_id else None
    readable = conv is not None and conv.archived_at is None and ai_can_read(db, conv)
    triggers = [e for e in batch if e.type in TRIGGERS and e.actor_id is not None]
    if readable and triggers:
        assert conv is not None
        latest = db.scalar(select(func.max(Event.created_at)).where(
            Event.conversation_id == conv.id, Event.type.in_(TRIGGERS)))
        if latest and (datetime.now(UTC) - latest).total_seconds() < debounce_seconds:
            return "waiting"
    run = AiRun(agent_id=agent.id, conversation_id=conv.id, from_event_id=batch[0].id,
                to_event_id=batch[-1].id) if conv else None
    if run:
        db.add(run)
        db.flush()
    records: list[dict] = []
    try:
        if readable and triggers:
            assert conv is not None and run is not None
            with db.begin_nested():
                context = assemble(db, conv, batch)
                def authorize(ctx):
                    db.refresh(agent)
                    db.refresh(conv)
                    if (not agent.active or "conversations:read" not in agent.scopes
                            or conv.archived_at is not None or not ai_can_read(db, conv)):
                        raise RuntimeError("access_revoked")
                    return replace(ctx, scopes=frozenset(agent.scopes))

                ctx = ToolContext(run.id, conv.id, frozenset(agent.scopes), ServiceBackend(db))
                process(context, model, ctx, records.append, authorize)
        elif run:
            # Log metadata only; do not load bodies for a non-consenting conversation.
            reason = "ai_cannot_read" if not readable else "not_actionable"
            log.info("Skipped AI events %s..%s: %s", batch[0].id, batch[-1].id, reason)
        if run:
            run.status, run.finished_at = "succeeded", datetime.now(UTC)
        consumer.last_event_id, consumer.updated_at = batch[-1].id, datetime.now(UTC)
        outcome = "processed" if readable and triggers else "skipped"
    except Exception as exc:
        # No provider errors or arbitrary exception strings in persistent logs.
        if run:
            run.status, run.finished_at = "failed", datetime.now(UTC)
            run.error = str(exc) if str(exc) in ("tool_call_failed", "access_revoked", "context_too_large") else \
                type(exc).__name__
        outcome = "failed"
        for record in records:
            if record["status"] == "executed":
                record["result"]["output"]["rolled_back"] = True
        db.info.pop("pending_events", None)  # savepoint rolled back its events too
        db.info.pop("pending_frames", None)  # notifications from rolled-back proposals
    if run:
        db.add_all(AiToolCall(run_id=run.id, **record) for record in records)
    db.flush()
    return outcome


def main() -> None:
    from api.db import session_factory

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--source", choices=("postgres", "fixtures"), default="postgres")
    parser.add_argument("--model", choices=("native", "recorded"), default="native")
    parser.add_argument("--responses", type=Path, help="Saved calls for --model recorded; otherwise no_action.")
    parser.add_argument("--fixture-interval", type=float, default=0, help="Seconds between fixture events.")
    parser.add_argument("--debounce", type=float, default=45)
    parser.add_argument("--poll", type=float, default=2)
    args = parser.parse_args()
    if (not all(math.isfinite(v) for v in (args.debounce, args.poll, args.fixture_interval))
            or args.debounce < 0 or args.poll <= 0 or args.fixture_interval < 0):
        parser.error("debounce/fixture-interval must be non-negative and poll positive; all must be finite")
    if args.responses and args.model != "recorded":
        parser.error("--responses requires --model recorded")
    logging.basicConfig(level=logging.INFO)
    model = (RecordedResponses.from_path(args.responses) if args.responses else RecordedResponses({})) \
        if args.model == "recorded" else NativeModel()
    if args.source == "fixtures":
        from ai.eval import replay

        print("Fixture source + recording proposal backend; no product writes.")
        report = replay(lambda _: model, interval=args.fixture_interval, stop_on_failure=True)
        if report["failed_inputs"]:
            raise SystemExit(1)
        return
    while True:
        with session_factory() as db:
            result = run_once(db, model, debounce_seconds=args.debounce)
            db.commit()
        log.info("AI worker: %s", result)
        if args.once:
            if result == "failed":
                raise SystemExit(1)
            return
        # A separate process persists replayable WS events; it cannot reach API's in-memory hub.
        time.sleep(args.poll if result in ("idle", "busy", "waiting", "paused", "failed") else 0)


if __name__ == "__main__":
    main()
