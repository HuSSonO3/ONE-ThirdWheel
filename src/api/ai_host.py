"""Hosts the AI worker's polling loop inside the API process.

Running in-process lets proposals reach the browser live: `realtime.dispatch` fans out through
the same in-memory hub that serves the WebSockets. Opt in with AI_WORKER_ENABLED=true; the model
is configured from RUNPOD_API_KEY / RUNPOD_ENDPOINT_ID / AI_MODEL (see ai/README.md).
"""

import logging
import threading

from api import config, db, realtime

log = logging.getLogger(__name__)
IDLE_STATES = {"idle", "busy", "waiting", "paused", "failed"}


def _loop(model, stop: threading.Event) -> None:
    from ai.worker import run_once

    while not stop.is_set():
        result = "failed"
        try:
            with db.session_factory() as session:
                result = run_once(session, model, debounce_seconds=config.AI_DEBOUNCE_SECONDS)
                session.commit()
                realtime.dispatch(session)
        except Exception:
            log.exception("AI worker iteration failed")
        log.info("AI worker: %s", result)
        # Poll rapidly while there is backlog; back off otherwise.
        stop.wait(config.AI_POLL_SECONDS if result in IDLE_STATES else 0)


def start() -> tuple[threading.Thread, threading.Event] | None:
    if not config.AI_WORKER_ENABLED:
        return None
    from ai.model import NativeModel, load_env

    load_env()
    try:
        model = NativeModel()
    except ValueError as exc:
        log.warning("AI worker not started: %s", exc)
        return None
    stop = threading.Event()
    thread = threading.Thread(target=_loop, args=(model, stop), name="ai-worker", daemon=True)
    thread.start()
    log.info("AI worker started in-process")
    return thread, stop
