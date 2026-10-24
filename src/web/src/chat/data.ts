import type { Conversation, TaskStatus, User } from './types'

// Live directory of people, filled from GET /users and kept current by the data hook.
// Module state keeps the many `userById` call sites simple; the hook re-renders after each update.
let directory: User[] = []
const byId = new Map<string, User>()

export function setDirectory(list: User[]) {
  directory = list
  byId.clear()
  for (const u of list) byId.set(u.id, u)
}
export const allUsers = () => directory
export const userById = (id: string) => byId.get(id)

export function dmPartner(c: Conversation, meId: string) {
  return c.peerId && c.peerId !== meId ? userById(c.peerId) : undefined
}

export function conversationTitle(c: Conversation, meId: string) {
  return c.kind === 'dm' ? dmPartner(c, meId)?.name ?? 'Direct message' : c.name
}

export const STATUS_LABEL: Record<TaskStatus, string> = { open: 'Open', in_progress: 'In progress', done: 'Done', cancelled: 'Cancelled' }
