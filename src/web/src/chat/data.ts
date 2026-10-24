// Frontend-only demo data. Replaced by the generated API client + fixtures later.
import type { AppNotification, Conversation, Message, Suggestion, Task, User } from './types'

export const users: User[] = [
  { id: 'alice', name: 'Alice Morgan', initials: 'AM', title: 'Product Operations Lead', department: 'Operations', role: 'admin', presence: 'online' },
  { id: 'bob', name: 'Bob Chen', initials: 'BC', title: 'Web Engineer', department: 'Engineering', role: 'member', presence: 'online', managerId: 'alice' },
  { id: 'nina', name: 'Nina Patel', initials: 'NP', title: 'Content Designer', department: 'Operations', role: 'member', presence: 'online', managerId: 'alice' },
  { id: 'priya', name: 'Priya Shah', initials: 'PS', title: 'Program Manager', department: 'Operations', role: 'member', presence: 'away', managerId: 'alice' },
  { id: 'marco', name: 'Marco Ruiz', initials: 'MR', title: 'Customer Insights Analyst', department: 'Operations', role: 'member', presence: 'away', managerId: 'priya' },
]

export const conversations: Conversation[] = [
  { id: 'dept-operations', kind: 'department', name: 'Operations', description: 'Operations department · every task of every member', isPublic: false, memberIds: ['alice', 'nina', 'priya', 'marco'], department: 'Operations', ownerId: 'alice' },
  { id: 'dept-engineering', kind: 'department', name: 'Engineering', description: 'Engineering department · every task of every member', isPublic: false, memberIds: ['bob'], department: 'Engineering', ownerId: 'alice' },
  { id: 'ch-website-refresh', kind: 'channel', name: 'website-refresh', description: 'A focused space for the Northstar website refresh.', isPublic: true, memberIds: ['alice', 'bob', 'nina', 'priya'], ownerId: 'alice' },
  { id: 'ch-customer-insights', kind: 'channel', name: 'customer-insights', description: 'Research notes and patterns from customer conversations.', isPublic: true, memberIds: ['alice', 'marco', 'nina', 'priya'], ownerId: 'marco' },
  { id: 'ch-leadership-planning', kind: 'channel', name: 'leadership-planning', description: 'Private planning space for the leadership group.', isPublic: false, memberIds: ['alice', 'priya'], ownerId: 'alice' },
  { id: 'ch-brand-assets', kind: 'channel', name: 'brand-assets', description: 'Logos, templates and approved brand material.', isPublic: true, memberIds: ['nina', 'bob'], ownerId: 'nina' },
  { id: 'dm-alice-nina', kind: 'dm', name: '', description: 'Direct message', isPublic: false, memberIds: ['alice', 'nina'] },
  { id: 'dm-alice-marco', kind: 'dm', name: '', description: 'Direct message', isPublic: false, memberIds: ['alice', 'marco'] },
]

const m = (id: string, conversationId: string, authorId: string, time: string, body: string, extra: Partial<Message> = {}): Message =>
  ({ id, conversationId, authorId, time, body, reactions: {}, ...extra })

export const seedMessages: Message[] = [
  m('m0', 'ch-website-refresh', 'nina', '9:36 AM', 'Homepage hero copy v2 is in the doc. The mobile headline wraps to three lines at 375px, so it needs a second look.'),
  m('m1', 'ch-website-refresh', 'alice', '9:41 AM', 'Great. @Nina Patel could you prepare the mobile headline review by Thursday? Let\'s keep the first launch review moving.', { reactions: { '👍': ['alice', 'bob'], '✨': ['nina'] } }),
  m('m2', 'ch-website-refresh', 'alice', '10:03 AM', 'Morning team — the content review is booked for Thursday. Please bring any open questions into this thread.'),
  m('m3', 'ch-website-refresh', 'bob', '10:16 AM', 'I can confirm the performance budget after the asset export lands. The page should remain under 1.8 MB.', { files: [{ id: 'f1', name: 'homepage-performance-notes.txt', size: '2.4 KB' }] }),
  m('c1', 'ch-customer-insights', 'marco', '10:14 AM', 'A theme from this week\'s calls: teams want a clear place to pick up a conversation after being away. A concise recent-message preview came up twice.'),
  m('c2', 'ch-customer-insights', 'priya', '10:32 AM', 'That matches the onboarding interviews. I\'ll add the Northwind and Cedar Grove notes to the research summary.'),
  m('l1', 'ch-leadership-planning', 'priya', '8:55 AM', 'Draft Q1 priorities are in the planning doc. Comments welcome before Friday.'),
  m('o1', 'dept-operations', 'priya', '9:12 AM', 'Weekly ops sync moves to 2 PM today. Agenda is pinned in the doc.'),
  m('o2', 'dept-operations', 'alice', '9:20 AM', 'Thanks Priya. Please add the website refresh milestones to the agenda.'),
  m('e1', 'dept-engineering', 'bob', '9:05 AM', 'Staging deploy is green. Asset export lands this afternoon.'),
  m('d1', 'dm-alice-nina', 'alice', 'Yesterday, 5:02 PM', 'Great work on the narrow-width layouts. Can you check the longer headline variants too?'),
  m('d2', 'dm-alice-nina', 'nina', '9:37 AM', 'I checked the narrow-width headline this morning. Want me to post the summary in #website-refresh?'),
  m('d3', 'dm-alice-marco', 'marco', 'Yesterday, 2:08 PM', 'I\'ve pulled together the customer wording for the handoff. Short version: teams want fewer places to check for a follow-up.'),
]

export const seedTasks: Task[] = [
  { id: 'task1', title: 'Confirm homepage performance budget', assigneeId: 'bob', project: 'Website refresh', sourceConversationId: 'ch-website-refresh', status: 'in_progress', due: '2026-10-27' },
  { id: 'task2', title: 'Collect open questions for the content review', assigneeId: 'priya', project: 'Website refresh', sourceConversationId: 'ch-website-refresh', status: 'open', due: '2026-10-29' },
  { id: 'task3', title: 'Summarise onboarding interview themes', assigneeId: 'marco', project: 'Customer research', sourceConversationId: 'ch-customer-insights', status: 'open', due: '2026-10-30' },
]

export const seedSuggestions: Suggestion[] = [
  {
    id: 's1', conversationId: 'ch-website-refresh', title: 'Prepare mobile headline review',
    description: 'Review the homepage headline at narrow widths and share a recommendation.',
    assigneeId: 'nina', project: 'Website refresh', due: '2026-10-29', confidence: 91,
    sourceMessageId: 'm1', status: 'pending',
  },
]

export const seedNotifications: AppNotification[] = [
  { id: 'n1', text: 'Nina Patel sent you a message', time: '9:37 AM', conversationId: 'dm-alice-nina', read: false },
  { id: 'n2', text: 'TeamSync suggested a task in #website-refresh', time: '10:16 AM', conversationId: 'ch-website-refresh', read: true },
]

export const seedUnread: Record<string, number> = { 'alice:dm-alice-nina': 1 }

export const userById = (id: string) => users.find(u => u.id === id)

export function nowLabel() {
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date())
}

export function dmPartner(c: Conversation, meId: string) {
  return userById(c.memberIds.find(id => id !== meId) ?? c.memberIds[0])
}

export function conversationTitle(c: Conversation, meId: string) {
  return c.kind === 'dm' ? dmPartner(c, meId)?.name ?? 'Direct message' : c.name
}

export const STATUS_LABEL: Record<string, string> = { open: 'Open', in_progress: 'In progress', done: 'Done', cancelled: 'Cancelled' }
