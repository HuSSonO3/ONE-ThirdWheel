# Company Chat + AI Task Assistant — Feature Spec


Oct 24, 2026 · @Ahmed Ibrahim


## Overview


We are building a Slack-style company chat application with an AI layer that reads conversations and acts on them. The prototype targets one company of up to about 100 users, running as a single web app on one server.


**What it is.** A chat product with department channels, channels, direct messages, threads, rich text (including code), file and snippet attachments, emoji, reactions, and access-checked links to messages and channels. On top of the chat sits a task system. A department channel shows every task of every member of that department. Any other channel or DM shows only the tasks that were spawned in it. Every person has a personal task dashboard, a primary tab of the app, that aggregates everything assigned to them; their superiors can open that same dashboard.


**The goal.** The chat is the substrate; the product is the AI. The AI consumes the chat as a stream of events, works out what needs doing, and assigns tasks to the right person in the right channel, respecting the same access rules a human user is bound by. Task creation is the first tool the AI gets. The MVP's real deliverable is the tool-calling framework: the AI must pick the correct tool and make the correct API call from chat text. Later tools (leave requests, expense claims, calendar meetings) plug into that same framework without changing the chat or the AI's core loop.


**Who can see what.** Conversations follow Slack's rules: anyone can browse and join a public channel; private channels and DMs are visible to members only. Being someone's superior gives no extra access to any conversation. The org hierarchy (`users.manager_id`, expanded into `user_closure`) exists only in the database and is used for one thing: a user can open the personal task dashboard of anyone below them in the tree. Task visibility has three routes, combined with OR: you are in the assignee's department (the task is in your department channel); you are a member of the channel or DM the task was spawned in; or you are the assignee or one of their superiors (the dashboard).


One function, `can_access(user, resource)`, implements both rules and every feature in this document routes through it: channel links, message embeds, search results, file downloads, task lists and AI actions.


**Stack (decided).** React + TypeScript frontend; FastAPI (Python) backend serving REST and WebSockets from one process; PostgreSQL as the only database (full-text search and, later, `pgvector`); local disk or S3-compatible storage for files; a `jobs`/`events` table in Postgres instead of a message broker. Redis is added only when a second server process or a separate AI worker needs pub/sub. The AI layer is a Python package in the same repository sharing the backend's models and `can_access`.


**How to read this document.** Part 1 lists the features taken from Slack; Part 2 the features we add on top; Part 3 the AI features. Each feature is split into the work for the frontend, the backend and the database. Features Slack has that we are not building (Flannel, sharding, Kafka, multi-workspace, Slack Connect, huddles, Canvas, Workflow Builder, app directory, mobile apps, end-to-end encryption, SSO) are omitted here; the reasoning for dropping each is in the earlier chat and can be appended as an appendix if wanted.


**ERD alignment.** The ERD is being revised to match this document: `projects` and `project_members` are removed (project becomes a column on `tasks`), `department_groups` is removed, `user_departments` is replaced by `users.department_id` (one department per user), groups are merged into channels, and a single `conversations` table with three kinds (`department`, `channel`, `dm`) replaces separate channel and group tables (see 1.5).


## Part 1 — Features adopted from Slack


Each feature below is the 100-user version of what Slack does. Where Slack has infrastructure we are not replicating, the simpler substitute is stated.


### 1.1 Authentication and sessions


| Tier | Work |
| --- | --- |
| Frontend | Login page (email + password), logout, session persistence across reloads, redirect to login on 401. |
| Backend | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`. Server-side sessions in a signed cookie or short-lived JWT + refresh. Password hashing with argon2/bcrypt. WebSocket handshake authenticates from the same session. No SSO, no self-signup: admins create users. |
| DB | `users` gains `email` (unique), `password_hash`, `created_at`. `sessions` table if server-side sessions are chosen. |


### 1.2 User profiles


| Tier | Work |
| --- | --- |
| Frontend | Profile card on hover/click (name, job title, department, manager, direct reports). Edit-own-profile form. Avatar upload reusing the file pipeline (1.14). |
| Backend | `GET /users`, `GET /users/{id}`, `PATCH /users/{id}` (self or admin). Profile payload includes department name and manager so the client never joins. `job_title` is a label only; it carries no permissions. |
| DB | `users(id, name, job_title, manager_id → users.id, department_id → departments.id, role, email, password_hash, avatar_file_id, timezone, active, created_at)`. |


### 1.3 Roles and admin


| Tier | Work |
| --- | --- |
| Frontend | Admin panel: create/deactivate users, set manager, assign departments. Admin-only controls hidden by role. |
| Backend | Two roles for the prototype: `admin` and `member`. A `require_admin` dependency on admin routes. Deactivated users keep their messages but cannot log in; their rows stay for `user_closure` integrity. |
| DB | `users.role` enum (`admin`, `member`). |


### 1.4 Departments as mention targets


Slack's "user groups" (`@engineering`) are replaced by departments. There is no separate user-group entity: a department is a list of users, and ad-hoc groupings are conversations (1.5, 1.6).


| Tier | Work |
| --- | --- |
| Frontend | `@department` autocomplete in the composer alongside `@user`. Department management screen (admin): members and the department's channel(s). |
| Backend | `GET/POST/PATCH /departments`; a user's department is set on the user (`PATCH /users/{id}`). Creating a department creates its department channel; changing a user's department moves them between department channels. An `@department` mention expands to its current members for notifications and for the AI's assignment candidates. |
| DB | `departments(id, name)`; `users.department_id`. One department per user; the ERD's `user_departments` and `department_groups` are dropped. |


### 1.5 Conversations: department channels, channels, DMs


**One table, `conversations`, with a `kind` column.** Groups and channels are the same thing and are merged: a channel is any named conversation with a member list, public or private. Every kind shares the same messages, threads, reactions, files, read cursors, mentions, embeds and task tab; only the membership policy and the task-tab rule differ. Departments stay a separate table because a department is not a conversation; it owns one.


| Kind | Membership rule | Task tab shows | Sidebar |
| --- | --- | --- | --- |
| `department` | Synced from `users.department_id`; every member of the department, cannot leave. One per department. | Every task of every department member, with project and source-channel columns. | Pinned at top |
| `channel` | `is_public = true`: anyone can browse and join. `is_public = false`: invite only. Members can be added or removed at any time. Has a name. | Only tasks spawned in this channel. | Channels |
| `dm` | Exactly two users; find-or-create. No name. | Only tasks spawned in this DM. | Direct messages |


| Tier | Work |
| --- | --- |
| Frontend | Sidebar with three sections (department channel, channels, DMs) and unread badges; create-channel dialog (name, description, public/private, initial members); browse-and-join for public channels; conversation header with description, member count and the Tasks tab (2.3); archive action for channels. |
| Backend | One `Conversation` model and one set of endpoints. Membership endpoints enforce the per-kind rule above. `can_access(user, conversation)` = (`kind = channel` AND `is_public`) OR user is an active member. No hierarchy rule here. Creating a department (1.4) creates its `department` conversation. |
| DB | `conversations(id, kind ['department','channel','dm'], name, description, is_public, department_id nullable, created_by, archived_at, created_at)`. `conversation_members(conversation_id, user_id, joined_at, left_at, role ['owner','member'], muted, ai_opt_in)` — `left_at` kept for point-in-time access (2.7); `ai_opt_in` used for DMs (3.5). Unique index on a canonical `member_key` (sorted user ids) where `kind = dm`. |


### 1.6 Direct messages


| Tier | Work |
| --- | --- |
| Frontend | "New message" picker: one user opens (or creates) the DM with them; two or more users creates a private channel instead (1.5). DMs listed by recent activity. "Add people" on a DM creates a new private channel containing both plus the new people; the DM itself is unchanged. |
| Backend | `POST /conversations` with `kind = dm` finds-or-creates by the sorted member pair. Everything else (messages, threads, tasks, access) is inherited from 1.5. |
| DB | No new tables. The `member_key` unique index from 1.5. |


### 1.7 Messages (send, edit, delete)


| Tier | Work |
| --- | --- |
| Frontend | Virtualised message list with infinite scroll upward; optimistic send with a client-generated UUID; edit-in-place; delete with confirmation; "(edited)" marker. |
| Backend | `POST /channels/{id}/messages` (idempotent on `client_id`), `PATCH`, `DELETE` (soft). Server assigns `seq` (monotonic per channel) and broadcasts `message.created/updated/deleted` over WebSocket to connected members. Writes an `events` row (Part 2). |
| DB | `messages(id, channel_id, author_id, parent_id, seq, body_md, client_id, created_at, edited_at, deleted_at)`. `message_edits(message_id, prior_body_md, edited_at)` so the AI can see what changed. Index on `(channel_id, seq)`. |


### 1.8 Threads


| Tier | Work |
| --- | --- |
| Frontend | Reply count and participants under a message; thread panel on the right; "also send to channel" toggle. |
| Backend | A thread reply is a message with `parent_id` set. Thread fetch endpoint; reply count and last-reply timestamp maintained on the parent. Thread events broadcast to channel members. |
| DB | `messages.parent_id` (nullable, self-FK). `messages.reply_count`, `last_reply_at` on the parent. |


### 1.9 Real-time delivery (WebSocket)


| Tier | Work |
| --- | --- |
| Frontend | One WebSocket per tab; reconnect with exponential backoff; on reconnect, send `last_seq` per open channel and merge the gap; dedupe incoming events by message id. |
| Backend | WebSocket endpoint in the FastAPI process. In-memory map `user_id → set[websocket]`. Fan-out = loop over channel members' sockets. On connect, replay events after the client's cursor. This replaces Slack's message servers, consistent-hash routing and Kafka: one process, 100 connections. |
| DB | None beyond `messages.seq`. (Redis pub/sub only if a second process appears.) |


### 1.10 Rich text with code


| Tier | Work |
| --- | --- |
| Frontend | TipTap or Lexical editor configured to emit GitHub-flavoured Markdown: bold/italic/strike, links, bullet and numbered lists, blockquote, inline code, fenced code blocks with language picker and syntax highlighting (Shiki). Markdown renderer on the read side with the same highlighter. |
| Backend | Store Markdown as sent; sanitise rendered HTML server-side only if the server ever renders. Extract `@mentions`, `#channel` refs and message links at write time into join tables (1.11, 1.15). |
| DB | `messages.body_md` (text). No block-format JSON: Markdown is also what the AI reads. |


### 1.11 Mentions (@user, @group, @channel, @here)


| Tier | Work |
| --- | --- |
| Frontend | Autocomplete popup in the composer; mention chips rendered as links to profile/group; highlighted when the current user is mentioned. |
| Backend | Parse mentions on save; expand `@group` to members and `@channel` to all members; emit `mention` events used for unread badges and as the AI's primary assignment signal. |
| DB | \`message\_mentions(message\_id, user\_id |


### 1.12 Emoji and reactions


| Tier | Work |
| --- | --- |
| Frontend | Unicode emoji picker (off-the-shelf) in the composer and on message hover; reaction pills with counts and "who reacted" tooltip; toggle on click. |
| Backend | `PUT/DELETE /messages/{id}/reactions/{emoji}`; broadcast `reaction.added/removed`. Reactions are also written to `events` so the AI can treat ✅ / 👀 as status signals. Custom emoji deferred. |
| DB | `reactions(message_id, user_id, emoji, created_at)` with a unique constraint on the triple. |


### 1.13 Code snippets


| Tier | Work |
| --- | --- |
| Frontend | "Create snippet" dialog (title, language, body); rendered inline as a highlighted, collapsible block with copy and download. |
| Backend | A snippet is a file (1.14) with `kind = snippet` and `language` metadata; body stored as a text object; inline preview endpoint returns the first N lines. |
| DB | `files.kind`, `files.language`. |


### 1.14 File attachments


| Tier | Work |
| --- | --- |
| Frontend | Drag-and-drop and paste upload with progress; image thumbnails inline; generic file card (name, size, type) with download; multiple attachments per message. |
| Backend | `POST /files` (multipart) → stores to local disk or S3/MinIO under an opaque key, records metadata, returns `file_id`. `GET /files/{id}` checks `can_access` on the owning channel before streaming. Image resize for thumbnails as a background job. No public URLs. |
| DB | `files(id, uploader_id, channel_id, message_id, kind, name, mime, size, storage_key, language, created_at)`. |


### 1.15 Message links and channel links (access-checked embeds)


| Tier | Work |
| --- | --- |
| Frontend | Pasting an internal URL (`/c/{channel}/m/{message}` or `/c/{channel}`) renders an embed: quoted message with author/time, or channel card with name/description and a Join button. If the server returns `forbidden`, render a neutral "private content" stub with no details. |
| Backend | On save, detect internal links and record them. `GET /embeds?url=` resolves the target and runs `can_access(viewer, target)` for the requesting viewer, not the author. The same resolver later serves task links. |
| DB | `message_refs(message_id, target_type ['message','channel','task'], target_id)`. |


### 1.16 Unread tracking and read cursors


| Tier | Work |
| --- | --- |
| Frontend | Unread badge per channel; bold channel name; "new messages" divider; mark-as-read on scroll-to-bottom or focus. |
| Backend | `PUT /channels/{id}/read` sets the cursor; unread count = messages with `seq > cursor`. Broadcast cursor updates to the user's other tabs. |
| DB | `channel_read_cursors(user_id, channel_id, last_read_seq, updated_at)`. |


### 1.17 Presence


| Tier | Work |
| --- | --- |
| Frontend | Green/grey dot next to names, driven by `presence` events. |
| Backend | Online = has at least one open WebSocket. Broadcast `presence.changed` on first connect and last disconnect, with a 10-second grace on disconnect to absorb flaps. No heartbeat service, no Redis. |
| DB | None. |


### 1.18 Search


| Tier | Work |
| --- | --- |
| Frontend | Search box with results grouped by channel; filters for `from:`, `in:`, `has:file`; click jumps to the message in context. |
| Backend | `GET /search?q=` runs Postgres full-text search, then filters results through `can_access` for the searcher. Later: semantic search via `pgvector` (Part 3). |
| DB | `messages.tsv` (generated `tsvector` column) with a GIN index. |


### 1.19 In-app notifications


| Tier | Work |
| --- | --- |
| Frontend | Notification bell/list for mentions and task assignments; browser `Notification` API when the tab is unfocused; per-channel mute. No push, no email. |
| Backend | `notifications` written on mention, DM, thread reply you participate in, and task assignment. Mark-read endpoint. |
| DB | `notifications(id, user_id, type, ref_type, ref_id, read_at, created_at)`. `channel_members.muted` flag. |


### 1.20 Slash commands (mechanism only)


| Tier | Work |
| --- | --- |
| Frontend | `/` triggers a command palette; built-ins `/task`, `/invite`, `/leave`. |
| Backend | Composer text starting with `/` is routed to a command dispatcher instead of being saved as a message. `/task` creates a task in the current channel (Part 2) — a manual path alongside the AI. No installable third-party commands. |
| DB | None. |


### 1.21 Typing indicators


| Tier | Work |
| --- | --- |
| Frontend | "X is typing…" under the composer. |
| Backend | Ephemeral `typing` event over WebSocket with a 3-second TTL; never persisted. |
| DB | None. |


## Part 2 — Features added on top of Slack


These do not exist in Slack (or exist only as the generic "Lists" feature, which we replace). They are what the AI needs from the chat layer and what users need to see the AI's output.


### 2.1 Organisation hierarchy and closure table


The source of truth is `users.manager_id`. `user_closure` is derived and never written by application code.


| Tier | Work |
| --- | --- |
| Frontend | None. The hierarchy is never displayed. Its only visible effect is the list of subordinates a superior can pick from in the task dashboard (2.4). |
| Backend | `is_superior(a, b)` = row exists in `user_closure` with `ancestor_id = a, descendant_id = b, depth > 0`. `subordinates(me)` = all descendants. Used only by the task dashboard's permission check. Cycle check on `PATCH /users/{id}` when `manager_id` changes. |
| DB | Per the ERD: `user_closure(ancestor_id, descendant_id, depth)` with PK on the pair, index on `descendant_id`. Insert/update/delete triggers on `users.manager_id` rebuild the affected subtree. Self-rows (`depth = 0`) included. Source of truth is `users.manager_id`; application code never writes `user_closure`. |


### 2.2 Projects (a tag on tasks)


A project is not an entity. `tasks.project` is a nullable label: a task has zero or one project, tasks owned by different users can share one, and it exists to filter task lists. The ERD's `projects` and `project_members` tables are removed.


| Tier | Work |
| --- | --- |
| Frontend | Every task list (conversation tab, personal dashboard, subordinate view) gets two filters: **Project** (dropdown of values present in that list) and **User** (assignee). Project field in the task dialog with autocomplete over existing values to limit spelling drift. |
| Backend | `?project=` and `?assignee=` query parameters on every task endpoint. `GET /projects` returns distinct `tasks.project` values within the caller's visible scope. Admin endpoint to rename a project value across tasks. |
| DB | `tasks.project text null`, index on `project`. |


### 2.3 Tasks


A task always has an assignee, always points back to the message(s) it came from, and records the conversation it was spawned in (`source_channel_id`). Where a task appears depends on which kind of conversation is being viewed:


- **Department channel.** Shows every task of every member of that department, whoever created it and wherever it was spawned. Each row shows the project and the source channel so the department can see where its members' work is coming from. Visible to anyone in the department.
- **Any other channel, or a DM.** Shows only the tasks that were spawned there. Visible only to its members. A task spawned in `#website` and assigned to Bob (Engineering) appears in `#website` and in `#engineering`; it does not appear in `#marketing` even if the requester is in Marketing.
- **Personal task dashboard.** Everything assigned to the user, regardless of origin (2.4).


`can_see(user, task)` = user is the assignee OR `is_superior(user, assignee)` OR `user.department_id = assignee.department_id` OR user is a member of `task.source_channel_id`.


| Tier | Work |
| --- | --- |
| Frontend | Tasks tab inside every conversation. Columns: title, assignee, project, source channel, status, due, source message embed (1.15). Project and User filters (2.2). Manual create/edit dialog with the current conversation pre-filled as the source channel; the assignee picker lists channel members, plus the current user's direct reports who are not members (shown in a separate "Your reports" group). Inline status change. |
| Backend | `GET /conversations/{id}/tasks`: if the conversation is a `department`, return tasks whose assignee has that `department_id`; otherwise return tasks whose `source_channel_id` is this conversation. Both require `can_access(user, conversation)`. `POST /conversations/{id}/tasks` sets `source_channel_id = id` and enforces the assignment rule (2.7). `PATCH /tasks/{id}` re-checks the rule when the assignee changes. `GET /tasks/{id}` goes through `can_see`. Every change writes an `events` row (2.6), a `task_history` row, and a notification to the assignee (1.19). |
| DB | `tasks(id, assignee_id, created_by, created_by_ai boolean, source_channel_id → conversations.id, project text null, title, description_md, status ['open','in_progress','done','cancelled'], priority, due_at, created_at, updated_at, completed_at)`. `task_sources(task_id, message_id)`. `task_history(task_id, actor_id, field, old_value, new_value, changed_at)`. Indexes on `assignee_id`, `source_channel_id`, `project`, `status`. |


### 2.4 Personal task list ("My tasks")


| Tier | Work |
| --- | --- |
| Frontend | The task dashboard is a primary tab of the app, alongside the chat, not a sidebar entry. It lists everything assigned to the current user, grouped by source channel or due date, with Project and User filters and status controls. At the top, a person picker listing the user's subordinates (empty for most users); choosing one shows that person's dashboard in the same layout. Pending AI suggestions addressed to the user also surface here (3.2). |
| Backend | `GET /users/{id}/tasks` allowed when `id = me` OR `is_superior(me, id)`. `GET /me/subordinates` for the picker. Each task carries its source channel name; the source message embed obeys `can_access` and renders as the private stub when the viewer is not a member of that channel. |
| DB | No new tables; the `assignee_id` index and `user_closure` carry it. |


### 2.5 Task links (access-checked embeds)


| Tier | Work |
| --- | --- |
| Frontend | Pasting `/t/{task_id}` renders a task card (title, status, assignee, due) with the same forbidden stub as message links. |
| Backend | Extends the embed resolver (1.15) with `target_type = 'task'` using `can_access(viewer, task)`. |
| DB | `message_refs.target_type` already allows `'task'`. |


### 2.6 Event log (the AI's input)


An append-only record of everything that happened, in order. The AI reads this, never the UI and never the live tables directly.


| Tier | Work |
| --- | --- |
| Frontend | None (admin-only debug view of recent events is optional). |
| Backend | Every mutating endpoint writes one `events` row in the same transaction as its primary write: `message.created/updated/deleted`, `reaction.added/removed`, `member.joined/left`, `task.created/updated`, `file.uploaded`. Consumers track their position in `event_consumers`. The same rows drive WebSocket replay after reconnect (1.9), so one mechanism serves both. |
| DB | `events(id bigserial, type, channel_id, actor_id, subject_type, subject_id, payload jsonb, created_at)`. `event_consumers(name, last_event_id, updated_at)`. Index on `(channel_id, id)`. |


### 2.7 Assignment rule and source-message access


**The rule.** The *assigner* (whoever creates the task or accepts an AI suggestion) must always be a member of the channel the task is spawned in. The *assignee* must also be a member of that channel, with one exception: if the assigner is the assignee's direct manager (`users.manager_id`, one level only), the assignee may be outside the channel. There are no other exceptions, and the AI gets none: it only proposes, and the person accepting is the assigner.


The exception creates the one situation where a task's reader cannot read its source: a manager in `#website` assigns a task to their report Carol, who is not in `#website`. Carol's task cites Alice's message, which she cannot open.


| Tier | Work |
| --- | --- |
| Frontend | Task dialog and suggestion card enforce the rule before submit: a non-member assignee is only offered when the current user is their direct manager. Otherwise the card shows "\<name> isn't in this channel" with **Invite and accept** or **Reassign**. The embed component renders a "private content" stub when the server says no. |
| Backend | `can_assign(assigner, assignee, channel)` = `is_member(assigner, channel)` AND (`is_member(assignee, channel)` OR `assignee.manager_id = assigner.id`). Called on task create, on assignee change, and on suggestion accept. When the task is created under the exception (assignee not a member), the backend copies the source message text into `description_md` so the task is self-contained for the assignee; the embed is still attached. Separately, every time anyone opens a source embed, the resolver checks `can_access(viewer, source_channel)` for that viewer at that moment, using `conversation_members.joined_at` / `left_at`, so someone who later left the channel keeps access to messages from before they left and nothing after. Membership rows are never deleted, only closed with `left_at`. |
| DB | Covered by `conversation_members(joined_at, left_at)` from 1.5 and `users.manager_id`. |


## Part 3 — AI features


The AI is a Python package in the same repository as the backend. It runs as a background worker (inside the FastAPI process at first, a separate process later), consumes the event log, and acts only through the same REST layer and `can_access` function a human user goes through. It has no direct write access to chat or task tables. The MVP deliverable is 3.4: given chat text, the AI picks the right tool and makes the right call.


### 3.1 Event consumption and context assembly


| Tier | Work |
| --- | --- |
| Frontend | None. |
| Backend | Worker loop: read `events` after `event_consumers['ai'].last_event_id`, batch by channel, debounce (wait for a quiet period of \~30–60 s in a channel before analysing it so a half-typed thread is not acted on). For each batch assemble context: the new messages, the thread or last N messages before them, channel description, the channel's open tasks, and the profiles (name, title, department, manager) of everyone mentioned or participating. Advance the cursor only after the batch is fully processed. |
| DB | `event_consumers` row for `ai`. `ai_runs(id, channel_id, from_event_id, to_event_id, started_at, finished_at, status, error)` for observability and replay. |


### 3.2 Task extraction


**The AI never creates a task on its own.** Every candidate becomes a suggestion with all fields filled in, and a human turns it into a task.


| Tier | Work |
| --- | --- |
| Frontend | A suggestion card posted into the source conversation (visible only to its members) and surfaced on the proposed assignee's dashboard when they are a member. It shows title, description, assignee, project, due date and the source message embed. Buttons: **Accept** (creates the task as proposed), **Modify and accept** (opens the task dialog pre-filled; saving creates the task), **Reject**. Any member of the source conversation can act on it, and becomes the assigner; the assignment rule (2.7) decides whether Accept is enabled for that viewer with that assignee. |
| Backend | Prompt the model with the assembled context and a strict output schema: zero or more candidate tasks, each with `title`, `description`, `source_message_ids`, `suggested_assignee`, `due_at` (if stated), `confidence`. Dedupe against the conversation's open tasks and pending suggestions (same source message, similar title). Every candidate goes through the `propose_task` tool (3.4). `confidence` is stored for later evaluation, not used to gate anything. Accepting calls the normal task-create endpoint with `created_by = <accepting user>`, `created_by_ai = true`, `source_channel_id = <source conversation>`, which runs `can_assign`. Suggestions expire if untouched (default 7 days). |
| DB | `ai_proposals(id, run_id, conversation_id, kind ['task'], payload jsonb, confidence, status ['pending','accepted','modified','rejected','expired'], applied_task_id, decided_by, decided_at, created_at)` — every proposal is kept, for evaluation. |


### 3.3 Assignment resolution (right person, right channel)


| Tier | Work |
| --- | --- |
| Frontend | None beyond 3.2's suggestion card. |
| Backend | Resolve `suggested_assignee` to a user id in order: explicit `@mention` in the source message → named person in text matched against the user directory → `@department` expanded to its members and narrowed by the message ("someone from design") → fall back to the message author's manager or leave unassigned (the accepting user fills it in). `source_channel_id` is always the conversation the source message was posted in. The AI does not enforce the assignment rule itself; it records whether the resolved assignee is a member of the source channel so the card can show the right buttons (2.7). Set `project` only when the text names a project value that already exists. |
| DB | Reads `users` (incl. `department_id`, `manager_id`), `conversation_members`. No new tables. |


### 3.4 Tool-calling framework (the MVP)


This is the part that outlives the prototype. Task creation is the first tool; leave requests, expense claims and calendar meetings are later tools that register the same way.


| Tier | Work |
| --- | --- |
| Frontend | Admin page (3.5) listing tool calls: per run, which tool was chosen, the arguments, the result, and the source messages. Needed to judge whether the AI is picking correctly. |
| Backend | A `Tool` interface: `name`, `description`, JSON-schema `input`, `required_scope`, `execute(args)`. A registry the worker passes to the model as the available tool set, using the model provider's native tool-calling API. The dispatcher validates arguments against the schema, checks the AI's scopes (3.5), executes through the internal service layer, and records the outcome. Tools in the prototype: `propose_task`, `propose_status_change` (suggests marking a task done when the chat says so), `no_action`. Stub tools (`request_leave`, `submit_claim`, `schedule_meeting`) are registered with schemas but their `execute` only records the call, so tool selection can be measured before those systems exist. **No MCP in the prototype:** the tools and the worker are one Python process, so a plain registry is enough. The interface above is what MCP expects, so wrapping it in a local MCP server later is mechanical. |
| DB | `ai_tool_calls(id, run_id, tool_name, arguments jsonb, scope_check boolean, result jsonb, status ['executed','denied','failed','stubbed'], created_at)`. |


### 3.5 Access enforcement for AI actions


The AI is its own entity with its own permissions. It is not a user, not a Slack-style bot user, and it never acts in a human's name. One user holds the `admin` role (1.3) and is the only person who can see or change the AI's configuration.


| Tier | Work |
| --- | --- |
| Frontend | A simple admin page, reachable only by the admin user: the AI's scopes (checkboxes), a per-channel on/off switch (default on), and the audit log of runs and tool calls (3.4). For DMs, each member sees an "Allow AI in this conversation" toggle in the DM header; the AI reads the DM only when both have turned it on. |
| Backend | A principal type distinct from users. Scopes held by the AI in the prototype: `conversations:read`, `suggestions:create`, `suggestions:status`. Stub tools carry their own scopes (`leave:request`, `claims:submit`, `calendar:create`) so granting them later is a scope change. `ai_can_read(conversation)` = for `department` and `channel`: `conversations.ai_enabled`; for `dm`: both members' `conversation_members.ai_opt_in` are true. The worker skips events from conversations where this is false. The dispatcher (3.4) checks each tool's `required_scope`. Denied calls are logged, never retried. |
| DB | `ai_agent(id, name, scopes text[], active)`. `conversations.ai_enabled boolean default true` (channels and department channels). `conversation_members.ai_opt_in boolean default false` (DMs). `users.role = 'admin'` gates the page. `ai_tool_calls` records every action under the agent. |


### 3.6 Evaluation and feedback loop (later)


| Tier | Work |
| --- | --- |
| Frontend | On an AI-created task: "Not a task" and "Wrong assignee" buttons; on any message: "Make this a task" (which also records that the AI missed it). |
| Backend | Feedback writes to `ai_feedback` and, where applicable, updates the task. A small evaluation script replays a labelled set of channels through the worker and reports precision/recall for task extraction and tool selection. |
| DB | `ai_feedback(id, proposal_id, task_id, user_id, verdict ['correct','not_a_task','wrong_assignee','wrong_channel','missed'], note, created_at)`. |


### 3.7 Semantic search and embeddings (later)


| Tier | Work |
| --- | --- |
| Frontend | "Related messages" on a task; natural-language search alongside 1.18. |
| Backend | Embed messages asynchronously as a job; similarity query filtered through `can_access`. Used by 3.2 for dedupe and by 3.1 to pull relevant older context. |
| DB | `pgvector` extension; `message_embeddings(message_id, embedding vector, model, created_at)`. |


## Open items


Decisions that change the feature sections above once made.


- [ ] **Channel naming:** a private channel created from the "New message" picker with 3+ people has no obvious name. Auto-name it from the members (like a group DM) or require a name?
- [ ] **Suggestion expiry:** 7 days is a placeholder.
- [ ] **MCP:** not in the prototype (3.4). Revisit when a tool needs to live outside the backend process or another agent should reuse the same tools.


## Build plan


Three people. Two phases.


**Phase 1 — skeleton, split by tier.** One person per horizontal: frontend shell, backend skeleton, AI worker. Before anyone writes feature code, the three agree on and commit the contracts: the OpenAPI spec and generated TypeScript client, the WebSocket event types, the `events` row shape, the `Tool` interface, and a single `fixtures/` set (users with departments and managers, every conversation kind, a few hundred messages with mentions, planted tasks). The backend seed script loads the fixtures into Postgres; the frontend's mock server serves them; the AI replays them as an event stream. Each person then builds their skeleton against those contracts: routes, layout, sidebar, message list, task tab and dashboard with mock data; schema, migrations, auth, `can_access`, every endpoint returning seeded rows; worker loop, context assembly, tool registry, dispatcher, `propose_task` against a mocked task API. Phase 1 ends with one merge where the three skeletons are reconciled and the contracts are frozen.


**Phase 2 — features, split by vertical slice.** After the merge, work is assigned by feature, and the owner of a feature does its frontend, backend and DB. Directory ownership: `web/`, `api/`, `ai/` belong to whoever is working there; `contracts/`, `migrations/`, `fixtures/` change only by small PRs to main that everyone rebases onto. Rebase daily, merge each piece when done; no long-lived branches.


**First end-to-end milestone.** A message in a seeded channel mentions someone → `events` row → worker proposes a task → suggestion card appears in the channel and on the assignee's dashboard → accept → task shows in the channel's task tab, the assignee's department channel, and their dashboard.



