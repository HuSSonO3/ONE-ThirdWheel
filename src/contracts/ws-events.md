# WebSocket contract

One socket per tab at `GET /ws` (upgrade). It authenticates from the same `session` cookie as REST;
an invalid session closes with code `4401`. A browser `Origin` outside the server's
`ALLOWED_ORIGINS` closes with `4403`. All frames are JSON text.

## Server → client envelope

```json
{ "type": "message.created", "event_id": 1234, "conversation_id": "uuid", "data": { } }
```

- `event_id`: the `events.id` for persisted events; `null` for ephemeral ones (presence, typing,
  read cursors, notifications, control frames).
- `conversation_id`: null for frames not tied to a conversation.
- `data`: per type below. For persisted events it is the event's `payload` from `events-row.md`
  plus the fields listed here, so the client can render without a REST call. Two exceptions:
  `prior_body_md` (edit history, AI-only) is never sent, and for `message.created`/`message.updated`
  the `body_md`, `mentions` and `refs` are always the message's current state (empty once deleted),
  so replaying an old event never reveals pre-edit text.

## Persisted events (replayable)

| `type` | `data` = events-row payload, plus |
| --- | --- |
| `message.created` | `message`: full `Message` (openapi) |
| `message.updated` | `message`: full `Message` |
| `message.deleted` | nothing |
| `reaction.added`, `reaction.removed` | `reactions`: the message's `ReactionSummary[]` after the change |
| `member.joined`, `member.left` | `member`: `Member`; `member_count` |
| `conversation.updated` | `conversation`: `Conversation` |
| `task.created`, `task.updated` | `task`: full `Task` |
| `suggestion.created`, `suggestion.decided` | `suggestion`: full `Suggestion` (with `can_accept` for the recipient) |
| `file.uploaded` | `file`: `FileMeta` |

Clients dedupe by `event_id`; messages additionally by `message.id`.

## Ephemeral events (not replayed)

| `type` | `conversation_id` | `data` |
| --- | --- | --- |
| `hello` | null | `{ "user_id": "uuid", "online_user_ids": ["uuid"], "server_time": "ts", "max_event_id": 1234 }`. First frame after connect. |
| `presence.changed` | null | `{ "user_id": "uuid", "online": true }`. Sent on first connect and last disconnect, after a 10 s grace. |
| `typing` | set | `{ "user_id": "uuid", "parent_id": "uuid \| null" }`. Clients show it for 3 s; never persisted. |
| `read_cursor.updated` | set | `{ "last_read_seq": 42 }`. Sent only to the reader's other tabs. |
| `notification.created` | set or null | `{ "notification": Notification }`. Sent only to the recipient. |
| `subscribed` | null | `{ "conversation_ids": ["uuid"] }`. Ack for `subscribe`, sent after replay. |
| `resync_required` | set | `{ "reason": "gap_too_large" \| "access_changed" }`. Drop local state for this conversation and refetch over REST. |
| `error` | null | `Error` (openapi) |

## Client → server frames

### `subscribe`
Sent after `hello` and after every reconnect. It lists the conversations the tab has open or cached,
each with the last persisted `event_id` the client applied for it (null = no history).

```json
{ "type": "subscribe", "conversations": { "uuid-a": 1200, "uuid-b": null } }
```

For each conversation the caller can access, the server replays the `events` rows with
`id > cursor` in `id` order (index `(conversation_id, id)`), then sends `subscribed`. A `null`
cursor replays nothing; the client loads history over REST. If more than 500 events are pending
for one conversation, the server sends `resync_required` instead of replaying.

Inaccessible conversations are dropped from the subscription silently.

Without a subscription, the server still pushes every live event the user is entitled to (see the
fan-out table in `events-row.md`). `subscribe` only adds replay.

### `typing`
```json
{ "type": "typing", "conversation_id": "uuid", "parent_id": null }
```
Rate-limited server side to one relay per user per conversation per 2 s.

## Reconnect

The client reconnects with exponential backoff (0.5 s doubling, capped at 30 s, with jitter). On
reconnect it re-sends `subscribe` with its latest per-conversation cursors, merges the replayed
events, and dedupes by `event_id`.
