# `events` row

The append-only log every mutation writes, in the same transaction as its primary write (spec 2.6).
It has two readers: the AI worker (its only input) and the WebSocket layer (replay after reconnect,
see `ws-events.md`). Owner: AI writes, BE reviews. Model: `api/models/events.py`.

## Columns

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `bigint` identity | Global, strictly increasing. The cursor for consumers and WS replay. |
| `type` | `text` | One of the types below. |
| `conversation_id` | `uuid` null | The conversation the event belongs to. Null only for events with no conversation (none yet). |
| `actor_id` | `uuid` null | The user who caused it. **Null when the AI acted** (`suggestion.created`). |
| `subject_type` | `text` | `message`, `user`, `task`, `file`, `suggestion`, `conversation`. |
| `subject_id` | `uuid` | Id of the subject row. |
| `payload` | `jsonb` | Exact shape per type below. Self-contained: a consumer never needs to re-read the row to act. |
| `created_at` | `timestamptz` | Commit-time clock. Ordering is by `id`, never by this. |

Rules:

- One event per mutation; a mutation that changes several things (e.g. a message with mentions and a
  file) writes one event whose payload carries all of it.
- Payloads are snapshots at write time. They never change after insert.
- Ids in payloads are strings (UUID text); timestamps are RFC 3339 strings.
- Adding a field to a payload is backwards compatible. Removing or renaming one is a contract change.

## Types and payloads

### `message.created`
`subject_type = message`. Also written for thread replies (`parent_id` set).

```json
{
  "message_id": "uuid",
  "seq": 42,
  "parent_id": "uuid | null",
  "also_in_channel": false,
  "author_id": "uuid",
  "body_md": "Can @dana.k review the PR by Friday?",
  "mentions": [{ "kind": "user", "user_id": "uuid", "department_id": null }],
  "refs": [{ "target_type": "message", "target_id": "uuid" }],
  "file_ids": ["uuid"],
  "created_at": "2026-10-24T09:00:00Z"
}
```

### `message.updated`
`subject_type = message`. `prior_body_md` lets the AI see what changed.

```json
{
  "message_id": "uuid",
  "seq": 42,
  "parent_id": "uuid | null",
  "body_md": "new text",
  "prior_body_md": "old text",
  "mentions": [],
  "refs": [],
  "edited_at": "2026-10-24T09:05:00Z"
}
```

### `message.deleted`
`subject_type = message`.

```json
{ "message_id": "uuid", "seq": 42, "parent_id": "uuid | null", "deleted_at": "2026-10-24T09:06:00Z" }
```

### `reaction.added` / `reaction.removed`
`subject_type = message`, `subject_id` = the message. The AI treats ✅ and 👀 as status signals.

```json
{ "message_id": "uuid", "user_id": "uuid", "emoji": "✅" }
```

### `member.joined` / `member.left`
`subject_type = user`, `subject_id` = the member.

```json
{
  "user_id": "uuid",
  "role": "member",
  "via": "join | invite | create | department_sync (joined) · leave | removed | department_sync (left)",
  "by_user_id": "uuid | null"
}
```

### `conversation.updated`
`subject_type = conversation`. Rename, description, visibility, archive, AI switch.

```json
{ "changes": { "name": ["old", "new"], "ai_enabled": [true, false], "archived_at": [null, "2026-10-24T10:00:00Z"] } }
```

### `task.created`
`subject_type = task`. `conversation_id` = the task's `source_conversation_id`.

```json
{
  "task_id": "uuid",
  "title": "Review the payments PR",
  "description_md": "",
  "assignee_id": "uuid",
  "assignee_department_id": "uuid | null",
  "created_by": "uuid",
  "created_by_ai": true,
  "suggestion_id": "uuid | null",
  "project": "payments | null",
  "status": "open",
  "priority": "normal",
  "due_at": "2026-10-31T17:00:00Z | null",
  "source_conversation_id": "uuid",
  "source_message_ids": ["uuid"]
}
```

### `task.updated`
`subject_type = task`. `changes` maps each changed field to `[old, new]`; the current assignee and
status are always included so consumers need no lookup.

```json
{
  "task_id": "uuid",
  "assignee_id": "uuid",
  "assignee_department_id": "uuid | null",
  "status": "done",
  "changes": { "status": ["in_progress", "done"] }
}
```

### `file.uploaded`
`subject_type = file`. Written when the file is attached to a conversation (not for avatars).

```json
{
  "file_id": "uuid",
  "message_id": "uuid | null",
  "uploader_id": "uuid",
  "kind": "file | image | snippet",
  "name": "schema.sql",
  "mime": "text/plain",
  "size": 1834,
  "language": "sql | null"
}
```

### `suggestion.created`
`subject_type = suggestion`, `actor_id = null` (the AI). `payload.proposal` is exactly the
`TaskProposal` or `StatusChangeProposal` schema from `openapi.yaml`.

```json
{
  "suggestion_id": "uuid",
  "run_id": "uuid",
  "kind": "task | status_change",
  "proposal": { "title": "...", "assignee_id": "uuid", "assignee_is_member": true, "...": "..." },
  "confidence": 0.82
}
```

### `suggestion.decided`
`subject_type = suggestion`, `actor_id` = the deciding user (or null when it expired).

```json
{ "suggestion_id": "uuid", "status": "accepted | modified | rejected | expired", "applied_task_id": "uuid | null" }
```

## Who reads what

| Type | WebSocket fan-out | AI worker |
| --- | --- | --- |
| `message.*` | conversation members | yes, the main input |
| `reaction.*` | conversation members | yes (status signals) |
| `member.*` | conversation members + the member | yes (assignment candidates) |
| `conversation.updated` | conversation members | yes (`ai_enabled` changes) |
| `task.*` | members of the source conversation, of the assignee's department conversation, the assignee and their superiors | yes (dedupe, open-task context) |
| `file.uploaded` | conversation members | yes (context only) |
| `suggestion.*` | source conversation members | yes (dedupe; ignores its own `created`) |

The AI consumer skips events whose conversation fails `ai_can_read` and logs the skip (spec 3.5).
