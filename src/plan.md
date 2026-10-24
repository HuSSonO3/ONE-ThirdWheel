# Build Plan — Company Chat + AI Task Assistant

Oct 24, 2026

## 1. Overview

Three people build the prototype in two phases. This plan assumes the feature spec is settled; it says who does what, in what order, and what has to be true before each step starts.

**Phase 0 — Contracts (together, \~3 days).** Agree on and commit the things everyone depends on: repository layout, the database schema, the API and WebSocket contracts, the `events` row, the `Tool` interface, and one shared set of fixtures. Nothing else is written until these exist.

**Phase 1 — Skeletons (split by tier, \~2–3 weeks).** One person each on the frontend shell, the backend skeleton and the AI worker, building against the Phase 0 contracts and the shared fixtures rather than each other's code. Each skeleton has a definition of done below.

**Merge One (together, 1–2 days).** The three skeletons are reconciled into one running system against the real database. Every disagreement with the contracts is resolved here, once. On exit, the contracts, schema and fixtures are frozen: from then on they change only by small PRs to `main`.

**Phase 2 — Vertical slices (split by feature, the rest of the build).** Work is assigned by feature. Whoever owns a feature does its frontend, backend and DB. Branches stay short; everyone rebases on `main` daily and merges each piece when it is done. There is no second big merge.

**Why two phases.** The skeleton phase gets three people productive on day one without stepping on each other, and gives each of them a tour of their own tier. The vertical phase is where features get built, and features are the unit that can be demoed, tested and owned. The cost of staying horizontal for the whole build is an integration tax on every feature; the cost of going vertical from day one is three people fighting over an empty repository. Two phases avoid both.

**Roles in Phase 1.** `FE` = frontend shell owner. `BE` = backend skeleton owner. `AI` = AI worker owner (the author of this plan's AI sections). Roles dissolve after Merge One.

## 2. Repository layout and ownership

One repository, one `main` branch, one Docker Compose file that brings up the whole system.

```
repo/
  contracts/        shared · OpenAPI spec, WS event types, events row, Tool interface
  migrations/       shared · Alembic migrations (the schema)
  fixtures/         shared · seed data used by all three tiers
  web/              FE     · React + TypeScript app (Vite)
  api/              BE     · FastAPI app: models, services, routers, WebSocket
  ai/               AI     · worker, context assembly, tools, dispatcher
  scripts/          shared · seed, dev helpers, eval runner
  docker-compose.yml, README.md, .github/workflows/
```

| Directory | Owner in Phase 1 | Rule after Merge One |
| --- | --- | --- |
| `web/` | FE | Owned by whoever is working on the feature. |
| `api/` | BE | Same. |
| `ai/` | AI | Same. |
| `contracts/` | all three | Change only by a small PR to `main`, reviewed by at least one other person, then everyone rebases. Never changed inside a feature branch. |
| `migrations/` | BE merges | Same rule. One person (BE) merges migration PRs so numbering never collides. No migration lives in a branch for more than a day. |
| `fixtures/` | all three | Same rule. Adding a fixture is a PR to `main`. |
| `scripts/` | all three | Ordinary review. |

**What "shared" means in practice.** If your feature needs a new endpoint, a new column, or a new seed row, you open a PR that touches only `contracts/`, `migrations/` or `fixtures/`, get it merged first, rebase, and then build the feature on top. This is the single rule that keeps Phase 2 merges trivial: feature branches are disjoint by directory, and the files everyone depends on only ever change on `main`.

**Python packaging.** `api/` and `ai/` are two packages in one workspace (one `pyproject.toml` at the root with both as members, or two with `ai` depending on `api`). `ai` imports `api`'s SQLAlchemy models, `can_access`, and the service layer; `api` never imports `ai`. This keeps the dependency one-directional and lets the worker run as a separate process later with no code change.

**TypeScript client.** `web/src/api/` is generated from `contracts/openapi.yaml` by a script in `scripts/`; it is committed, and CI fails if regenerating it produces a diff. Nobody hand-writes a fetch call.

## 3. Phase 0 — Contracts (together, \~3 days)

Done in one room (or one call), in this order, because each item depends on the one before. The output is a commit on `main` that Phase 1 branches from.

### Day 1 — Repository and schema

- [ ] Create the repository with the layout in §2, Docker Compose (`web`, `api`, `postgres`, `minio`), a `README` with one-command setup, and CI that runs lint + tests for all three tiers.
- [ ] Write the full schema as Alembic migrations from the DB rows in the feature spec: `users`, `user_closure` (+ triggers), `departments`, `conversations`, `conversation_members`, `messages`, `message_edits`, `message_mentions`, `message_refs`, `reactions`, `files`, `channel_read_cursors`, `notifications`, `tasks`, `task_sources`, `task_history`, `events`, `event_consumers`, `ai_agent`, `ai_runs`, `ai_proposals`, `ai_tool_calls`. Write all of it now, even tables nobody will touch for weeks; adding a table later is a PR, but discovering a missing relationship later is a redesign.
- [ ] Write the SQLAlchemy models for every table in `api/models/`.
- [ ] Decide and write down the three access functions as signatures with docstrings (bodies can be stubs): `can_access(user, conversation)`, `can_see(user, task)`, `can_assign(assigner, assignee, channel)`.

### Day 2 — API and real-time contracts

- [ ] `contracts/openapi.yaml`: every endpoint named in the feature spec, with request/response schemas. Resources: auth, users, departments, conversations, members, messages, threads, reactions, files, embeds, search, read-cursors, notifications, tasks, suggestions, admin (AI config, audit). Error shape agreed once.
- [ ] `contracts/ws-events.md` (or a JSON schema file): every server→client event (`message.created/updated/deleted`, `reaction.added/removed`, `member.joined/left`, `presence.changed`, `typing`, `read_cursor.updated`, `task.created/updated`, `suggestion.created/decided`, `notification.created`) and the two client→server frames (`subscribe` with `last_seq` per conversation, `typing`).
- [ ] `contracts/events-row.md`: the `events` table row — `id`, `type`, `conversation_id`, `actor_id`, `subject_type`, `subject_id`, `payload` — and the exact `payload` for each type. This is the AI's input, so AI writes this one and BE reviews.
- [ ] `contracts/tool-interface.md` + `ai/tools/base.py`: the `Tool` protocol (`name`, `description`, `input_schema`, `required_scope`, `execute`), the dispatcher's result shape, and the scope names.
- [ ] Generate the TypeScript client; commit it; add the CI diff check.

### Day 3 — Fixtures

- [ ] `fixtures/` as JSON (or YAML): \~30 users across 4–5 departments with a 3-level manager tree; one department channel per department; \~8 channels (public and private, some with members from several departments); \~15 DMs; \~400 messages with realistic threads, `@mentions`, code blocks and a few file references; \~20 planted tasks and \~10 planted suggestions in various states. Include at least: a message that clearly asks someone to do something, one that sounds like a task but isn't, one that mentions a non-member, one that closes a task ("done, shipped it"), and one DM where only one side has opted in.
- [ ] `scripts/seed.py` loads the fixtures into Postgres (used by BE, by Merge One, and by every demo).
- [ ] A note in `fixtures/README.md` on how FE serves them through its mock server and how AI replays them as an event stream.

**Exit criterion.** `docker compose up` brings up an empty but migrated database; `scripts/seed.py` fills it; `GET /health` answers; the TypeScript client compiles; the three contract files are merged. Everyone branches from this commit.

## 4. Phase 1 — Skeletons (split by tier, \~2–3 weeks)

Each person builds against the Phase 0 contracts and fixtures only. Nobody blocks on anybody. The goal is breadth, not polish: every screen, endpoint and worker stage exists and is wired, even if it is thin.

### 4.1 FE — frontend shell (`web/`)

Built against a mock server (MSW) serving the fixtures through the generated client. No real backend.

- App shell: auth state, routing, the two primary tabs (Chat, Task dashboard), admin route gated by role.
- Chat layout: sidebar with the three sections (department channel, channels, DMs) and unread badges; conversation header with Messages and Tasks tabs.
- Message list with virtualisation, thread panel, composer with the rich-text editor emitting Markdown (bold/italic/code/lists/code blocks with language), `@mention` autocomplete, emoji picker, file drop zone (uploads to the mock).
- Reaction pills, message embeds (message, channel, task) including the "private content" stub.
- Tasks tab (both modes: department and spawned-here), task dialog with the assignee rule from 2.7 expressed in the picker, Project and User filters.
- Task dashboard tab with the subordinate picker; suggestion card with Accept / Modify and accept / Reject and the "isn't in this channel" state.
- Admin page: AI scopes, per-channel switch, tool-call log table. DM header "Allow AI" toggle.
- WebSocket client module that connects, subscribes with `last_seq`, reconnects with backoff, and applies events to the store (tested against a fake socket).

**Done when** every screen in the feature spec can be reached and shows fixture data; the WebSocket client passes its reconnect tests; the mock server implements the OpenAPI spec and CI type-checks the generated client against it.

### 4.2 BE — backend skeleton (`api/`)

Real Postgres, seeded from fixtures. No frontend; tested with pytest and HTTP.

- Auth: login/logout/me, session cookie, password hashing, admin dependency.
- Users, departments, `user_closure` triggers verified by tests (move a manager, assert the closure).
- `can_access`, `can_see`, `can_assign` implemented and unit-tested against fixture cases, including the direct-manager exception and `joined_at`/`left_at`.
- Conversations and members for all three kinds, DM find-or-create, department channel auto-membership.
- Messages: create (idempotent on `client_id`, server `seq`), edit (with `message_edits`), soft delete, threads, mentions extracted into `message_mentions`, internal links into `message_refs`.
- Reactions, files (local disk in dev, access-checked download), read cursors, notifications, Postgres full-text search filtered by `can_access`.
- Tasks: list per conversation with the department/spawned-here split, create with `can_assign`, patch, history, `task_sources`. Suggestions: list/accept/modify/reject endpoints writing `ai_proposals`.
- `events` writer: every mutating service writes its row in the same transaction. Verified by a test that performs every mutation and asserts the event log.
- WebSocket endpoint: in-process connection registry, fan-out to members, replay after cursor from the `events` table, presence on connect/disconnect, typing relay.
- Embed resolver for message/channel/task links.

**Done when** every endpoint in `openapi.yaml` is implemented and conformance-tested; the access functions have a test per rule; the event-log test passes; a scripted two-client WebSocket test sees a message delivered and replayed after reconnect.

### 4.3 AI — worker (`ai/`)

Real code end to end, with two mocks at the boundary: an event source that replays fixture messages as `events` rows on a timer, and a task/suggestion API client that records calls instead of hitting `api/`.

- Worker loop: cursor in `event_consumers`, batch by conversation, debounce window, `ai_runs` row per batch, failure handling (a run that errors is recorded and the cursor does not advance past it).
- `ai_can_read` check: channel `ai_enabled`, DM double opt-in; skipped events are logged, not lost.
- Context assembly: new messages, thread or preceding N messages, conversation description, open tasks and pending suggestions, profiles of participants and mentioned users (name, title, department, manager). Hard cap on token size with a documented truncation order.
- Model client wrapper with the tool-calling API, retries, and a recorded-response mode for tests.
- Tool registry and dispatcher: schema validation, scope check, execution, `ai_tool_calls` row for every call including denials.
- Tools: `propose_task`, `propose_status_change`, `no_action`; stubs `request_leave`, `submit_claim`, `schedule_meeting`.
- Assignment resolution (mention → name match → department → manager → unassigned) and the non-member flag.
- Dedupe against open tasks and pending suggestions.
- Eval harness: run the worker over the fixtures, compare proposals to the planted expected tasks, print precision/recall and a table of tool choices.

**Done when** the worker runs over the full fixture set end to end; the eval harness prints numbers; every tool call is recorded; swapping the two mocks for the live backend is a config change, demonstrated by an integration test that runs against a seeded `api/` in Docker.

## 5. Merge One (together, 1–2 days)

The one scheduled convergence. Its job is to make the three skeletons one system and to freeze what everyone depends on. It is not a code review; it is a reconciliation.

**Before the session.** Each person rebases their branch on `main` and confirms their own definition of done still holds. FE records every place the mock server had to deviate from `openapi.yaml`; AI records every assumption about `events` payloads and task endpoints that the mocks encoded. Those two lists are the agenda.

**During the session, in order:**

1. Merge BE first. The backend is the ground truth for the contracts; everything else is reconciled against a running `api/`.
2. Point FE at the real backend. Walk every screen. Each mismatch is resolved one of two ways: the contract was right and the implementation is fixed, or the contract was wrong and it gets a PR to `contracts/` (merged on the spot) plus the fix on both sides. No third option; in particular, no client-side workaround that papers over a backend difference.
3. Swap AI's mocks for the live `api/` and the real `events` table. Run the worker over the seeded database. Resolve mismatches the same way.
4. Run the first end-to-end flow (§8, Milestone 1) with all three people watching.
5. Merge FE and AI.

**Exit checklist.**

- [ ] `docker compose up` + `scripts/seed.py` gives a system where you can log in as a fixture user, see your channels, post a message, see it on another browser, open a task tab, and see a suggestion the worker produced.
- [ ] `contracts/openapi.yaml` matches what `api/` serves (conformance test green) and what `web/` calls (generated client, diff check green).
- [ ] `contracts/ws-events.md` matches what the server emits and the client handles.
- [ ] `contracts/events-row.md` matches what `api/` writes and `ai/` reads.
- [ ] All migrations applied on a clean database with no manual steps.
- [ ] The access functions have one test per rule and all pass against the real database.
- [ ] CI runs lint, type-check and tests for all three tiers on every PR, and the conformance and client-diff checks.

**What is frozen on exit.** `contracts/`, `migrations/`, `fixtures/`. Frozen means: changes are allowed, but only as their own small PR to `main`, reviewed by one other person, merged before any feature that needs them, and followed by everyone rebasing. Phase 1 roles end here.

## 6. Phase 2 — Vertical slices

After Merge One, work is a backlog of slices. A slice is a feature or a coherent part of one, small enough to merge within a few days, and its owner does the frontend, backend and DB for it. Skeleton work from Phase 1 means most slices are "make this real and tested" rather than "build from nothing".

Slices are grouped by what they depend on. Within a group, slices can run in parallel across the three people; groups are roughly sequential. Feature-spec section numbers in brackets.

### Group A — make the core real (first)

| Slice | Covers | Depends on |
| --- | --- | --- |
| A1 Messages end to end | Send/edit/delete, threads, optimistic UI, reconnect gap-fill, events written
1.7,1.8,1.9
| — |
| A2 Rich text and code | Editor polish, Markdown rendering, code highlighting, snippets
1.10,1.13
| A1 |
| A3 Conversations and membership | Create/join/leave/invite, DM find-or-create, department auto-membership, archive, sidebar sections
1.5,1.6
| — |
| A4 Tasks core | Task tab in both modes, create/edit with `can_assign`, status, history, dashboard with subordinate picker
2.3,2.4,2.7
| A3 |
| A5 Suggestions end to end | Worker → `propose_task` → card in channel and on dashboard → accept/modify/reject → task
3.1–3.5
| A1, A4 |

Group A is the first end-to-end milestone (§8 M1). Suggested owners: A1+A2 to the Phase 1 FE person, A3+A4 to the BE person, A5 to the AI person — each starts in the tier they know and crosses into the others.

### Group B — the rest of the chat

| Slice | Covers |
| --- | --- |
| B1 Mentions and notifications | `@user` / `@department`, notification list, browser notifications, mute
1.11,1.19
|
| B2 Reactions and emoji | Picker, pills, events, reaction signals available to the AI
1.12
|
| B3 Files | Upload, thumbnails, access-checked download, attach to messages
1.14
|
| B4 Embeds | Message, channel and task links with access check and private stub
1.15,2.5
|
| B5 Read cursors and presence | Unread badges, new-messages divider, online dots, typing
1.16,1.17,1.21
|
| B6 Search | Full-text search with filters, results through `can_access`
1.18
|
| B7 Projects and filters | `tasks.project`, autocomplete, rename, Project/User filters everywhere
2.2
|
| B8 Slash commands | `/task`, `/invite`, `/leave`
1.20
|

### Group C — AI depth

| Slice | Covers |
| --- | --- |
| C1 Context quality | Thread-aware context, open-task awareness, truncation order, prompt iteration against the eval harness
3.1,3.2
|
| C2 Assignment resolution | Name matching, department narrowing, manager fallback, non-member flag; measured on the fixtures
3.3
|
| C3 Status-change proposals | `propose_status_change` from "done" messages and ✅ reactions
3.4
|
| C4 Tool-selection measurement | Stub tools registered; eval report of which tool was chosen per fixture message; admin audit page real
3.4,3.5
|
| C5 DM opt-in and admin | Double opt-in enforced, per-channel switch, scopes page
3.5
|

### Group D — admin and hardening

| Slice | Covers |
| --- | --- |
| D1 Users and departments admin | Create/deactivate users, set manager (closure rebuild), departments and their channels
1.2–1.4
|
| D2 Point-in-time access | `joined_at`/`left_at` honoured by embeds and search; tests for leave-then-view
2.7
|
| D3 Seed and demo data | A second, richer fixture set for demos; reset script |
| D4 Deployment | One VM, Compose in production mode, backups, basic logging |

**Deferred (not scheduled):** 3.6 evaluation feedback buttons, 3.7 embeddings, custom emoji, external link unfurls, interactive message blocks, pins.

## 7. Working rules

These apply from Merge One onward. They are short on purpose; the point is that nobody has to think about them.

**Branches.** One branch per slice, named `<initials>/<slice-id>-<short-name>` (`ab/a4-tasks-core`). Branch from `main`, rebase on `main` at least daily, delete after merge. No branch lives longer than a week; if a slice is taking longer, split it and merge the finished part.

**Shared directories.** A change to `contracts/`, `migrations/` or `fixtures/` is its own PR, touching nothing else, titled with the slice it serves. It is reviewed by one other person and merged before the slice branch is rebased onto it. Migration PRs are merged by one person (the Phase 1 BE owner keeps this job) so revision ids never collide. A feature PR that contains a migration or a contract change is sent back.

**Pull requests.** Small, one slice or part of one. Every PR has: a one-line summary, a checklist of which spec sections it covers, and tests. One approval from either other person. The author merges (rebase-and-merge, no merge commits), then deletes the branch.

**Reviews.** Reviewed within one working day. Review for correctness against the spec and the access rules first, style last. If a reviewer and author disagree about the spec, the spec is wrong or unclear: fix the spec doc, then the code.

**CI on every PR.** Lint and type-check for `web/`, `api/`, `ai/`; unit tests for all three; `api/` conformance test against `openapi.yaml`; TypeScript client regeneration diff check; migrations applied to a clean database; the AI eval harness run over the fixtures with its numbers posted as a PR comment (no threshold gate yet, visibility only).

**Local flow.** `docker compose up` for Postgres and MinIO; `api/` and `ai/` run from the shell with hot reload; `web/` with Vite. `scripts/seed.py --reset` restores the fixture state. Everyone can run the whole system locally at all times.

**Cadence.** A 15-minute sync every day: what merged, what is next, anything touching shared directories today. A 30-minute demo at the end of each week where someone other than the owner drives each merged slice. No other standing meetings.

**Spec changes.** The feature spec is the source of truth. A decision made in chat or a sync is written into the spec the same day by whoever made it, before any code depends on it.

## 8. Milestones and acceptance checks

Each milestone is a scripted walkthrough someone other than the owners can perform on a freshly seeded system. Durations are estimates for three people working on this most of the time; they are there to notice slippage, not to hold anyone to.

| # | Milestone | Acceptance check | When |
| --- | --- | --- | --- |
| M0 | Contracts committed | Phase 0 exit criterion (§3) | End of week 1 |
| M1 | Skeletons merged | Merge One exit checklist (§5) | End of week 4 |
| M2 | First end-to-end flow (Group A) | Log in as a fixture user. Post a message in a channel mentioning a colleague. Within the debounce window a suggestion card appears in the channel and on the colleague's dashboard. Accept it. The task appears in the channel's Tasks tab, in the colleague's department channel, and on their dashboard. Their manager opens the dashboard via the subordinate picker and sees it. A non-member assignee is correctly blocked for everyone except their direct manager. | End of week 7 |
| M3 | Chat complete (Group B) | Every Part 1 feature in the spec can be exercised: mentions and notifications, reactions, files, embeds including the private stub, unread and presence, search, projects and filters, slash commands. Two browsers stay in sync through a forced disconnect. | End of week 10 |
| M4 | AI measured (Group C) | The eval harness reports precision and recall for task proposals over the fixtures and a per-message table of tool choices including stubs. DM double opt-in is enforced. The admin page shows scopes, per-channel switches and the audit log. | End of week 12 |
| M5 | Pilot-ready (Group D) | Admin can create real users and departments; the system runs on one VM from Compose with backups; a second fixture set exists for demos; point-in-time access tests pass. | End of week 14 |

**What "done" means for the prototype.** M4 is the MVP as defined in the spec: the AI reads chat and picks the right tool with the right arguments, demonstrably, with humans in the loop. M5 is what lets \~100 real people use it.

**Risks to watch.**

- Merge One slipping because a skeleton isn't at its definition of done. Cut scope in the skeleton, not the contracts; merge on the date.
- The rich-text editor eating weeks. Timebox A2 to the Markdown subset in the spec; everything else is deferred.
- The AI worker tuned only against the fixtures. Add real (consented) conversations to a second fixture set as soon as the pilot users exist.
- Shared-directory discipline eroding under deadline pressure. The daily sync's third question ("touching shared directories today?") is the early warning.


