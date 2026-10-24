# WebSocket events

TODO (Phase 0 Day 2). See plan.md §3.

## Server → client
`message.created`, `message.updated`, `message.deleted`, `reaction.added`, `reaction.removed`,
`member.joined`, `member.left`, `presence.changed`, `typing`, `read_cursor.updated`,
`task.created`, `task.updated`, `suggestion.created`, `suggestion.decided`, `notification.created`

## Client → server
- `subscribe` — `{ conversations: { [conversation_id]: last_seq } }`
- `typing` — `{ conversation_id }`
