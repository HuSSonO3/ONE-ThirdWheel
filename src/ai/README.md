# AI task-assistant MVP

This package implements spec 3.1–3.5 without owning the frontend, backend endpoints,
schema or shared fixtures. It builds on the service layer already on
`Ahmed/AI-Integration`. `api` never imports `ai` unless the API owner opts into
hosting its polling loop.

## What it does

- Polls `events`, locks the `ai` consumer, waits for 45 seconds of conversation
  quiet, and processes contiguous same-conversation prefixes.
- Checks the AI principal's read scope and channel switch / DM double opt-in
  **before loading content**, and rechecks consent and scopes after inference.
- Builds context from message event snapshots, threads/recent history, profiles,
  conversation-local open tasks and pending proposals. No passwords or emails
  enter prompts. Deleted messages are excluded even during historical replay.
- Offers six native function tools: `propose_task`, `propose_status_change`,
  `no_action`, and leave/claim/meeting stubs. All tools remain visible even if their
  scopes are absent: selecting a denied tool is a measurable result.
- Validates JSON Schema and scopes, resolves assignees, checks source/task IDs,
  deduplicates, and calls `ServiceBackend.create_proposal`. It **never creates or
  edits tasks**. Existing BE accept/modify/reject endpoints remain the human gate.
- Persists `ai_runs`, every tool-call result, and the consumer cursor. A failed
  batch rolls back proposals and leaves the cursor unchanged while retaining the
  failed run and audit (successful calls from that attempt are marked rolled back).

## Run

From `src/`, run `uv sync`. Configure `DATABASE_URL` and `OPENAI_API_KEY` in your
environment's secrets manager; never commit or paste credentials into a command.
Optional settings: `AI_MODEL` (default `gpt-4.1-mini`) and `AI_BASE_URL` (default
OpenAI's HTTPS `/v1` URL). The provider must support native chat-completion tool
calls. This code does not provision a model account or call a model during tests.

```sh
uv run python -m ai.worker --once --debounce 0
uv run python -m ai.worker
uv run python -m ai.worker --source fixtures --model recorded --fixture-interval 0.01
uv run python -m ai.worker --source postgres --model recorded --responses saved.json --once --debounce 0
uv run pytest ai/tests
uv run python -m ai.eval
uv run python -m ai.eval --live
uv run python -m ai.eval --responses ai/tests/data/reference_calls.json
```

`--source fixtures` swaps the event source for timed shared-fixture replay and
the write boundary for `RecordingBackend`; it never writes product data. Use
`--model recorded` for deterministic tests without a provider key; pass
`--responses` for saved native tool calls. The same `process`/tools/dispatcher
execute in both modes. `--source postgres` selects the real event consumer and
existing `ServiceBackend`, without changing code. A failed fixture-worker input
rolls back recorded proposals and stops before advancing its in-memory cursor.

The default seed places the cursor at the end of history. To replay seed messages,
use the existing `scripts/seed.py --reset --ai-from-start` on a **disposable dev
database only**. A normal run processes new messages after the stored cursor.

### Backend integration

`run_once(session, model)` leaves transaction ownership to the caller. An in-process
API host can run it in a background thread, commit, then call
`api.realtime.dispatch(session)` in the same API process, following the existing
request lifecycle. Poll rapidly while it returns `processed`/`skipped`; back off
for `idle`/`busy`/`waiting`/`paused`/`failed`. Do not block FastAPI's event loop.

**Standalone mode does not deliver into the API process's in-memory WebSocket
hub.** Suggestions, notifications and replayable events are persisted and visible
via REST/reconnect. Immediate live push requires that in-process integration or a
future shared pub/sub layer. No backend lifecycle or Compose changes are bundled
in this AI-only PR.

### Evaluation

`ai.eval` replays all shared fixture messages, edits, deletions and reactions through
the same tools, using a recording proposal backend. It prints task-selection
precision/recall, labelled tool and argument accuracy, per-case outcomes, statuses
and counts. `--output report.json` saves every run, tool call, and skip reason.
Labels are used only for scoring; the model never receives `expected.json`.

Default mode is deliberately a **no-action baseline**, not evidence of model
quality. `ai/tests/data/reference_calls.json` is a small hand-authored regression
sample exercising all six tools, multi-task extraction, old-source reactions and
non-member assignment; it is **not** a recording of native-provider performance.
`--responses saved.json` replays explicitly saved calls, keyed by source
message ID, e.g. `{"<id>":[{"name":"no_action","arguments":{"reason":"FYI"}}]}`.
Use `<id>:message.updated` or `<id>:reaction.added` for an event-specific response;
bare message-ID recordings apply only to `message.created`, never to later edits
or reactions.
`--live` makes billable requests to the configured model; fixture consent rules
still apply. Tool-selection scores include stub scope denials as correct selections
when appropriate. Task precision/recall uses one-to-one matches of executed proposal
arguments (before dedupe): wrong assignees or dates count as false positives and
misses, and repeated calls cannot cover multiple tasks. Argument checks also cover
non-member flags, projects, status targets, leave dates, amounts/currencies and
meeting attendees/duration. The fixture source reconstructs task status from its
history before each signal, so final `done` state does not hide completion cases.
This remains a synthetic fixture evaluation, not a calibrated production benchmark.

### Plan §4.3 verification

- `pytest ai/tests`: schemas/scopes/stubs, assignment and non-member flags,
  dedupe, failure/cursor behavior, consent, native provider request/retry parsing,
  full timed fixture replay, source/model configuration and argument scoring.
- Existing seeded Postgres tests exercise the real backend service boundary.
- `ai/tests/test_api_boundary.py` is an opt-in check against the **unchanged**
  API in Docker: HTTP message → recorded-config worker → suggestion visible via
  HTTP → human acceptance. It requires `AI_DOCKER_TEST_API_URL` and `DATABASE_URL`
  for the **same disposable test deployment**; it creates and accepts a test task.
  It is skipped in ordinary runs and never changes API code or startup.
- Live-model extraction quality still requires a configured `OPENAI_API_KEY`.
  Recorded test results are never presented as native-model accuracy.

## Deliberate limits

- No embeddings, autonomous task creation, UI, external leave/claims/calendar
  integrations, migrations or contract changes.
- One consumer is serialized across inference. A busy conversation can delay
  later conversations rather than let a global cursor skip unprocessed events.
  Contiguous prefixes are bounded at 100 events; interleaved conversations can
  produce multiple model calls after a quiet window.
- Context is capped at 24,000 ASCII JSON bytes, a conservative input-token upper
  bound for the default tokenizer (not a provider token quota). Truncation order:
  oldest non-trigger history, pending suggestions, open tasks, directory entries,
  conversation description. Oversized triggering input fails closed; it is never
  silently discarded.
- Ambiguous people/departments stay unassigned for the accepting human instead
  of selecting an arbitrary employee. Non-member assignees are flagged, never
  invited automatically. Projects are limited to labels already visible in the
  source conversation and named in source text.
- Exhausted provider retries or invalid calls stop that batch. Inspect `ai_runs`
  and fix the provider/configuration/input before retrying; there is no automatic
  dead-letter skip or cursor-reset command.
- Tests use recorded model calls and a real migrated/seeded Postgres boundary.
  Live-provider quality and browser delivery are not validated by these tests.
