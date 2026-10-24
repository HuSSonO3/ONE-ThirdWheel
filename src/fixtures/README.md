# Fixtures

Shared seed data for all three tiers (plan.md §3 Day 3). **Generated**: edit
`scripts/build_fixtures.py` and run it; CI fails if these files are stale (`build_fixtures.py --check`).
Changes go in their own PR to `main`.

All fixture users log in with password `password123`. Emails are `first.last@example.com`.
Grace Liu (`grace.liu@example.com`) is the admin. Company time is Asia/Kuala_Lumpur, and history
runs Mon 12 to Fri 23 Oct 2026.

| File | Contents |
| --- | --- |
| `departments.json` | 5 departments |
| `users.json` | 30 users, 3-level manager tree (CEO → 5 heads → ICs), top-down order |
| `conversations.json` | 5 department channels, 8 channels (public/private, one with `ai_enabled: false`), 15 DMs; each with `members` (incl. one closed membership) |
| `messages.json` | ~390 messages in `seq` order per conversation, with `mentions`, `refs`, `reactions`, `edits` and `file_ids` pre-extracted |
| `files.json` | 3 files (CSV, snippet, image) with their bytes inline |
| `tasks.json` | 20 tasks with `source_message_ids` and status `history` |
| `suggestions.json` | 11 AI proposals: pending, accepted, modified, rejected, expired, one `status_change` |
| `notifications.json`, `read_cursors.json` | Mentions/assignments; per-member cursors with some unread |
| `expected.json` | AI eval labels (see below) |

Body syntax (contracts/DECISIONS.md #16): mentions are `[@Name](mention:user/<uuid>)` /
`[@Dept](mention:department/<uuid>)`; internal links are `/c/<id>`, `/c/<id>/m/<id>`, `/t/<id>`.

## Planted scenarios

`expected.json` lists every planted case with the tool the AI should choose and its key arguments.
Messages in AI-readable conversations that are not listed expect `no_action`. Cases include: a clear
ask, task-sounding non-tasks, a non-member mention, "done, shipped it" closing a task, a ✅ reaction
closing a task, a one-sided DM opt-in and an AI-disabled channel (both must be skipped), a
department mention, "someone from design", two tasks in one message, an edit that turns a message
into a task, a thread ask, a self-commitment, and the three stub tools. `already_tracked_by`
marks cases an existing task or suggestion covers, so dedupe should create nothing new.

## Who uses them how

- **BE / demos:** `DATABASE_URL=... python scripts/seed.py --reset` loads everything in one
  transaction. It also writes the `events` log for this history in time order, and puts the file bytes
  under `$FILES_DIR` (default `src/.data/files`). The AI cursor is set to the end of the log; add
  `--ai-from-start` to replay history through the worker.
- **FE:** the MSW mock server imports these JSON files and serves them through the generated client
  (`web/src/api/`), shaping rows into the OpenAPI response schemas (e.g. a `Task` embeds its
  `assignee` `UserSummary`). Log in as any fixture user; the mock accepts `password123`.
- **AI:** the fixture event source turns `messages.json` (and the reactions and edits on it) into
  `events` rows with the payloads in `contracts/events-row.md`, ordered by `created_at` and emitted
  on a timer. The eval harness then compares the resulting tool calls with `expected.json`.
