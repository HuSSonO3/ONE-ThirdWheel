# Fixtures

Shared seed data for all three tiers (plan.md §3 Day 3). Changes go in their own PR to `main`.

- **BE / demos:** `python scripts/seed.py` loads these into Postgres.
- **FE:** the MSW mock server in `web/` serves these files through the generated client.
- **AI:** the worker's fixture event source replays `messages.json` as `events` rows on a timer.
