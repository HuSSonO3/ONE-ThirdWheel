// Frontend-only demo types. Replaced by the generated API client once contracts exist.
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
  memberIds: string[]
  department?: string
}

export type FileAttachment = { id: string; name: string; size: string }

export type Message = {
  id: string
  conversationId: string
  authorId: string
  time: string
  body: string
  reactions: Record<string, string[]>
  files?: FileAttachment[]
  parentId?: string
  edited?: boolean
  local?: boolean
}

export type Task = {
  id: string
  title: string
  assigneeId: string
  project?: string
  sourceConversationId: string
  status: TaskStatus
  due?: string
  createdByAi?: boolean
}

export type Suggestion = {
  id: string
  conversationId: string
  title: string
  description: string
  assigneeId: string
  project: string
  due: string
  confidence: number
  sourceMessageId: string
  status: 'pending' | 'accepted' | 'rejected'
  taskId?: string
}

export type AppNotification = {
  id: string
  text: string
  time: string
  conversationId: string
  read: boolean
}
