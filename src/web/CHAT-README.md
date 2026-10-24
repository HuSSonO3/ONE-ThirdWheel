# Main chat frontend

Run `npm ci` then `npm run dev` from `src/web`. Validate with `npm run lint` and `npm run build`.

The visual design follows the supplied screenshot: white surfaces, pale-blue navigation rail, electric-blue actions.

The product source of truth is `.agents/skills/impeccable/feature_spec.md` in the repository root. The current local spec is untracked; it was read, not changed or automatically committed.

## Implemented frontend scope

- §1.5: department / channel / DM sections, conversation selection, descriptions and member counts.
- §1.7: local send with UUID, blank-message guard, edit own messages with edited marker, delete own messages with confirmation.
- §1.8: right-side thread panel and local thread replies with reply counts.
- §1.10: safe Markdown rendering including GFM, inline/fenced code, lists, links and quotes (raw HTML is not enabled).
- §1.12: toggle local emoji reactions; counts reflect local reactions only.
- §1.16: sample unread badges, cleared locally when selecting a conversation.
- Local text search within the selected conversation (not the cross-channel server search in §1.18).
- Per-conversation and per-thread drafts, Enter to send, Shift+Enter for newline, IME guard, keyboard navigation, mobile sidebar and reduced-motion support.

## Boundaries

The backend currently exposes only `/health`; no message/auth/WebSocket contracts exist yet. All identities, messages and counts are sample data held in memory until the API exists. Reload resets local activity. No requests claim real delivery or authorization. The shared fixture files remain untouched and empty; frontend sample data lives in `src/chat/data.ts`.

Tasks/AI, channel creation/join/archive, new-DM lookup, authentication, server permissions, persistence, infinite history/virtualization, real-time delivery, attachments, mention autocomplete, WYSIWYG editing, syntax highlighting and cross-channel search are future integrations. Threads do not yet include “also send to channel.”

## Manual smoke check

Switch between all three conversation kinds; verify headers and unread counts. Type a draft, switch away and back, then send using Enter. Confirm whitespace-only sends are disabled and Shift+Enter inserts a newline. Edit a sent message, cancel deletion once, then confirm deletion. Add and remove a reaction. Open a thread, send a reply, close and reopen it. Search for matching and nonmatching text. At mobile width, open navigation, cycle focus, press Escape, and confirm focus returns to the menu button. Reload to confirm local activity resets.
