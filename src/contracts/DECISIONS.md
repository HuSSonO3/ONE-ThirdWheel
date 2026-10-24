# Phase 0 decisions

Where `feature_spec.md` and `plan.md` left a gap or disagreed, the contracts follow these. The spec is the
source of truth: each item here should be folded back into it (plan.md §7, "Spec changes").

| # | Decision | Why |
| --- | --- | --- |
| 1 | **`conversation_id` everywhere.** The spec mixes `channel_id` (messages, events, files, read cursors) with `conversations`. Every column and path uses `conversation_id` / `/conversations/{id}/…`. `tasks.source_channel_id` is `tasks.source_conversation_id`. The read-cursor table keeps the plan's name `channel_read_cursors`. | One name for one thing; DMs and department channels are conversations too. |
| 2 | **`message_mentions(message_id, kind, user_id, department_id)`** with `kind ∈ user, department, channel, here`. `@channel`/`@here` are stored as one row and expanded at notification time. | The spec row was truncated. Storing expansions would freeze membership at write time. |
| 3 | **Server-side sessions**: `sessions(id, user_id, created_at, expires_at)`, an opaque random id in an HttpOnly `session` cookie, argon2 password hashes. The WebSocket authenticates from the same cookie. | Simpler than JWT + refresh; logout and deactivation take effect immediately. |
| 4 | **Enums are `text` + `CHECK`**, not Postgres `ENUM` types. | Adding a value is a one-line migration with no type juggling. |
| 5 | **`conversations.last_seq`** allocates `messages.seq` (`UPDATE … SET last_seq = last_seq + 1 RETURNING`). | A gap-free per-conversation counter without sequences per conversation. |
| 6 | **`conversation_members` has its own `id`**; a partial unique index allows one *open* row per (conversation, user). Leaving closes the row; rejoining opens a new one. | Point-in-time access (2.7) needs the history of every membership period. |
| 7 | **`ai_proposals.kind` adds `status_change`** and the table gains `expires_at` (default now + 7 days). | `propose_status_change` (3.4) produces a suggestion too; expiry is in the spec (3.2). |
| 8 | **`ai_runs.agent_id`** references `ai_agent`. The migration inserts the single agent `assistant` with the three default scopes, and the `event_consumers` row `ai`. | These exist in every environment, not only seeded ones. |
| 9 | **WS replay cursor is per-conversation `event_id`**, not message `seq` (plan says "`last_seq` per conversation"). | Replay must cover reactions, tasks and suggestions, not only messages. `seq` still orders messages and drives unread counts and REST gap-fill (`after_seq`). |
| 10 | **Extra event types**: `conversation.updated`, `suggestion.created`, `suggestion.decided` are written to `events`. `actor_id` is null when the AI acted. | The WS needs them replayable, and the AI must see decisions to dedupe. |
| 11 | **`user_closure` triggers** also reject manager cycles (`check_violation`), in addition to the API's check. | The closure is wrong forever after one bad write; the database is the last line. |
| 12 | **Embeds never 403**: `GET /embeds` returns `{type: "forbidden"}` with no details. | The client renders the stub without treating it as an error. |
| 13 | **`files.kind` adds `image` and `avatar`**; `files.conversation_id` is null only for avatars. | Thumbnails and the profile avatar reuse the file pipeline (1.2, 1.14). |
| 14 | **Not in the schema yet**: `ai_feedback` (3.6), `message_embeddings` (3.7). | Both are "later"; each will be its own migration PR. |
| 15 | **Messages are unique on (`author_id`, `client_id`)** for idempotent send. | `client_id` is generated per author's client; retries collide only with themselves. |
| 16 | **Mentions in `body_md` are Markdown links with a `mention:` URL**: `[@Dana Kim](mention:user/<uuid>)`, `[@Design](mention:department/<uuid>)`; `@channel` and `@here` are plain text. Internal links are paths: `/c/<conversation>`, `/c/<conversation>/m/<message>`, `/t/<task>`. | Unambiguous to parse, readable to the AI and in any Markdown renderer, and there is no `handle` column to drift. |
| 17 | **Object storage in Compose is SeaweedFS (`s3` service, S3 API on :8333)**, not MinIO as plan.md §3 lists. | MinIO no longer publishes pullable community images. Any S3-compatible store fits the spec (1.14); dev uploads use local disk until slice B3. |
