# Chat frontend

React + TypeScript (Vite). The UI talks to the real API through the generated client in `src/api/` and a single
WebSocket (`/ws`). Code lives in `src/chat/`.

## Run it

1. Start Postgres and the API from the repo root, then load the fixtures:

   ```bash
   docker compose up --build postgres api
   docker compose exec api python scripts/seed.py --reset
   ```

2. Start the web app:

   ```bash
   cd src/web && npm ci && npm run dev
   ```

3. Open http://localhost:5173 and sign in as a fixture user, e.g. `grace.liu@example.com` (admin) / `password123`.

The API uses an HttpOnly session cookie, so the browser must reach it same-origin. `vite.config.ts` proxies the API
paths and `/ws` to `http://localhost:8000` (override with `API_PROXY_TARGET`; Compose sets it to `http://api:8000`).

Checks: `npm run lint`, `npm run build` (type-checks). After editing `contracts/openapi.yaml`, run `src/scripts/gen_client.sh`.

## Layout

| File | Role |
| --- | --- |
| `App.tsx` | Session gate: `/auth/me`, then `Login` or `ChatApp`. |
| `chat/ChatApp.tsx` | The signed-in screen: sidebar, header, messages, panels, dialogs. |
| `chat/useChatData.ts` | All server state and actions (REST calls, optimistic send, WebSocket event handling). |
| `chat/socket.ts` | WebSocket client: `subscribe` with per-conversation cursors, jittered reconnect. |
| `chat/adapt.ts` | API objects → view models in `chat/types.ts`; mention links; time formatting. |
| `chat/api.ts` | Client wrapper: error shape, 401 handling. |

## Wired to the API

Sign in/out, conversations (mine, browse, create, join, archive, DMs), messages (send with `client_id`, edit, delete,
paginate, threads, reactions, file upload and download), live updates and presence over the WebSocket, unread counts and
read cursors, server-side search, notifications, tasks (per conversation, My tasks, subordinate picker, status changes),
AI suggestions (accept, modify, reject, invite-and-accept) and the per-conversation TeamSync switch.

## Not done yet

Typing indicators in the UI, message/channel/task link embeds, `@here`/department mention autocomplete, slash commands,
manual task creation dialog, project filters beyond the table, the admin page (users, departments, AI scopes, audit log),
code syntax highlighting, virtualised message list, and "also send to channel".

## Known gap with the backend

The channel TeamSync switch calls `PATCH /admin/conversations/{id}/ai`, which is admin-only. Product wants the channel owner to
control it, so a non-admin owner will get a 403 until that endpoint allows owners.
