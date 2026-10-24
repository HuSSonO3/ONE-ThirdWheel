# `events` row

TODO (Phase 0 Day 2, written by AI, reviewed by BE). See plan.md §3.

| Column | Type |
| --- | --- |
| `id` | bigint, monotonic |
| `type` | text |
| `conversation_id` | uuid, nullable |
| `actor_id` | uuid |
| `subject_type` | text |
| `subject_id` | uuid |
| `payload` | jsonb — exact shape per `type` below |

## Payloads by type
TODO
