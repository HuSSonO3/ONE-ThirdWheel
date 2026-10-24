// View models used by the chat components. `adapt.ts` maps API objects (api/schema.ts) onto these.
export type Presence = 'online' | 'away' | 'offline'
export type Role = 'admin' | 'member'
export type TaskStatus = 'open' | 'in_progress' | 'done' | 'cancelled'

export type User = {
  id: string
  name: string
  initials: string
  title: string
  department: string
  role: Role
  presence: Presence
  managerId?: string
}

export type Conversation = {
  id: string
  kind: 'department' | 'channel' | 'dm'
  name: string
  description: string
  isPublic: boolean
  /** Loaded lazily for the open conversation (GET /conversations/{id}/members). */
  memberIds: string[]
  memberCount: number
  isMember: boolean
  /** Channel owner (or any DM participant). */
  isOwner: boolean
  peerId?: string
  /** Admin switch for channels; the caller's own opt-in for DMs. */
  aiEnabled: boolean
  /** True only when the AI may actually read (DMs need both people). */
  aiActive: boolean
  lastSeq: number
  unread: number
  archived: boolean
}

export type FileAttachment = { id: string; name: string; size: string }

export type Message = {
  id: string
  clientId?: string
  seq: number
  conversationId: string
  authorId: string
  time: string
  createdAt: string
  body: string
  reactions: Record<string, string[]>
  files?: FileAttachment[]
  parentId?: string
  replyCount: number
  edited?: boolean
  /** Sent from this tab and not yet confirmed by the server. */
  pending?: boolean
  failed?: boolean
}

export type Task = {
  id: string
  title: string
  description: string
  assigneeId: string
  project?: string
  sourceConversationId: string
  sourceConversationName: string
  status: TaskStatus
  due?: string
  createdByAi?: boolean
}

export type Suggestion = {
  id: string
  conversationId: string
  kind: 'task' | 'status_change'
  title: string
  description: string
  assigneeId: string
  project: string
  due: string
  confidence: number
  sourceMessageId: string
  status: 'pending' | 'accepted' | 'rejected' | 'expired'
  taskId?: string
  /** False when the proposed assignee is not a member and the viewer is not their manager. */
  canAccept: boolean
  assigneeIsMember: boolean
}

export type AppNotification = {
  id: string
  text: string
  time: string
  conversationId: string | null
  refId: string
  read: boolean
}
