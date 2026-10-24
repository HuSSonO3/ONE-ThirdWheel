import type { components } from '../api/schema'
import type { AppNotification, Conversation, FileAttachment, Message, Suggestion, Task, User } from './types'

type S = components['schemas']

export const initialsOf = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]!.toUpperCase()).join('') || '?'

export function toUser(u: S['User']): User {
  return {
    id: u.id, name: u.name, initials: initialsOf(u.name), title: u.job_title ?? '', department: u.department_name ?? '',
    role: u.role, presence: 'offline', managerId: u.manager_id ?? undefined,
  }
}

const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString()

export function formatTime(iso: string, now = new Date()) {
  const d = new Date(iso)
  const time = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(d)
  if (sameDay(d, now)) return time
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1)
  if (sameDay(d, yesterday)) return `Yesterday, ${time}`
  return `${new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(d)}, ${time}`
}

export function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function toConversation(c: S['Conversation']): Conversation {
  const dm = c.kind === 'dm'
  return {
    id: c.id, kind: c.kind, name: c.name ?? '', description: c.description ?? '', isPublic: c.is_public,
    memberIds: [], memberCount: c.member_count, isMember: c.membership !== null,
    isOwner: dm ? c.membership !== null : c.membership?.role === 'owner',
    peerId: c.dm_peer?.id,
    aiEnabled: dm ? c.membership?.ai_opt_in ?? false : c.ai_enabled,
    aiActive: c.ai_active, lastSeq: c.last_seq, unread: c.unread_count, archived: c.archived_at !== null,
  }
}

export function toMessage(m: S['Message']): Message {
  const reactions: Record<string, string[]> = {}
  for (const r of m.reactions) if (r.user_ids.length) reactions[r.emoji] = r.user_ids
  const files: FileAttachment[] = m.files.map(f => ({ id: f.id, name: f.name, size: formatSize(f.size) }))
  return {
    id: m.id, clientId: m.client_id ?? undefined, seq: m.seq, conversationId: m.conversation_id, authorId: m.author_id, time: formatTime(m.created_at), createdAt: m.created_at,
    body: m.body_md, reactions, files: files.length ? files : undefined, parentId: m.parent_id ?? undefined,
    replyCount: m.reply_count, edited: m.edited_at !== null,
  }
}

export function reactionsRecord(list: S['ReactionSummary'][]) {
  const out: Record<string, string[]> = {}
  for (const r of list) if (r.user_ids.length) out[r.emoji] = r.user_ids
  return out
}

export function toTask(t: S['Task']): Task {
  return {
    id: t.id, title: t.title, description: t.description_md, assigneeId: t.assignee.id, project: t.project ?? undefined,
    sourceConversationId: t.source_conversation.id, sourceConversationName: t.source_conversation.name ?? '',
    status: t.status, due: t.due_at ? t.due_at.slice(0, 10) : undefined, createdByAi: t.created_by_ai,
  }
}

export function toSuggestion(s: S['Suggestion'], taskTitle: (id: string) => string | undefined): Suggestion {
  const status = s.status === 'modified' ? 'accepted' : s.status
  const base = {
    id: s.id, conversationId: s.conversation_id, confidence: Math.round((s.confidence ?? 0) * 100), status,
    taskId: s.applied_task_id ?? undefined, canAccept: s.can_accept,
  } as const
  if (s.kind === 'status_change') {
    const p = s.payload as S['StatusChangeProposal']
    const name = taskTitle(p.task_id) ?? 'a task'
    return { ...base, kind: 'status_change', title: `Mark “${name}” as ${p.new_status.replace('_', ' ')}`,
      description: 'Suggested from recent messages in this conversation.', assigneeId: '', project: '', due: '',
      sourceMessageId: p.source_message_ids[0] ?? '', assigneeIsMember: true }
  }
  const p = s.payload as S['TaskProposal']
  return { ...base, kind: 'task', title: p.title, description: p.description_md, assigneeId: p.assignee_id ?? '',
    project: p.project ?? '', due: p.due_at ? p.due_at.slice(0, 10) : '', sourceMessageId: p.source_message_ids[0] ?? '',
    assigneeIsMember: p.assignee_is_member }
}

export function toNotification(n: S['Notification']): AppNotification {
  return { id: n.id, text: n.preview, time: formatTime(n.created_at), conversationId: n.conversation_id, refId: n.ref_id, read: n.read_at !== null }
}

/** Turns typed `@Full Name` into the contract's `[@Full Name](mention:user/<id>)` links (DECISIONS #16). */
export function withMentionLinks(body: string, people: User[]) {
  let out = body
  for (const u of [...people].sort((a, b) => b.name.length - a.name.length)) {
    const plain = new RegExp(`(^|[^\\[\\w])@${u.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\w\\]])`, 'g')
    out = out.replace(plain, `$1[@${u.name}](mention:user/${u.id})`)
  }
  return out
}
