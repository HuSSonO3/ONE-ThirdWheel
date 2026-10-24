import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { components } from '../api/schema'
import { api, call } from './api'
import {
  formatTime, reactionsRecord, toConversation, toMessage, toNotification, toSuggestion, toTask, toUser, withMentionLinks,
} from './adapt'
import { setDirectory } from './data'
import { ChatSocket, type ServerFrame } from './socket'
import type { AppNotification, Conversation, Message, Suggestion, Task, TaskStatus, User } from './types'

type S = components['schemas']

const byTime = (a: Message, b: Message) => (a.createdAt < b.createdAt ? -1 : a.createdAt > b.createdAt ? 1 : a.seq - b.seq)

/** Insert or replace by id (or by the client id of an optimistic copy), keeping time order. */
function upsert(list: Message[], m: Message) {
  const i = list.findIndex(x => x.id === m.id || (m.clientId && x.clientId === m.clientId))
  if (i >= 0) { const next = list.slice(); next[i] = { ...m, replyCount: Math.max(m.replyCount, list[i].replyCount) }; return next }
  return [...list, m].sort(byTime)
}

export type ChatData = ReturnType<typeof useChatData>

export function useChatData(meUser: S['User'], activeId: string | null) {
  const meId = meUser.id
  const [people, setPeople] = useState<User[]>([])
  const [online, setOnline] = useState<Set<string>>(new Set())
  const [connected, setConnected] = useState(true)
  const [loading, setLoading] = useState(true)
  const [convs, setConvs] = useState<Conversation[]>([])
  const [memberIds, setMemberIds] = useState<Record<string, string[]>>({})
  const [messages, setMessages] = useState<Record<string, Message[]>>({})
  const [hasMore, setHasMore] = useState<Record<string, boolean>>({})
  const [threads, setThreads] = useState<Record<string, Message[]>>({})
  const [tasks, setTasks] = useState<Record<string, Task[]>>({})
  const [myTasks, setMyTasks] = useState<Task[]>([])
  const [reports, setReports] = useState<User[]>([])
  const [reportTasks, setReportTasks] = useState<Record<string, Task[]>>({})
  const [rawSuggestions, setRawSuggestions] = useState<Record<string, S['Suggestion'][]>>({})
  const [mySuggestionIds, setMySuggestionIds] = useState<Set<string>>(new Set())
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [error, setError] = useState<string | null>(null)

  const cursors = useRef<Record<string, number | null>>({})
  const active = useRef(activeId)
  const convsRef = useRef<Conversation[]>([])
  const socket = useRef<ChatSocket | null>(null)
  const loaded = useRef(new Set<string>())
  useEffect(() => { active.current = activeId }, [activeId])
  useEffect(() => { convsRef.current = convs }, [convs])

  const fail = useCallback((e: unknown) => setError(e instanceof Error ? e.message : 'Something went wrong'), [])

  // Directory with live presence. `setDirectory` feeds the module-level `userById` lookups.
  const directory = useMemo(() => {
    const list = people.map(u => ({ ...u, presence: online.has(u.id) ? 'online' as const : 'offline' as const }))
    setDirectory(list)
    return list
  }, [people, online])

  const taskTitle = useCallback((id: string) => {
    for (const list of [myTasks, ...Object.values(tasks)]) { const t = list.find(x => x.id === id); if (t) return t.title }
    return undefined
  }, [myTasks, tasks])

  const suggestions = useMemo(
    () => Object.fromEntries(Object.entries(rawSuggestions).map(([k, v]) => [k, v.map(x => toSuggestion(x, taskTitle))])) as Record<string, Suggestion[]>,
    [rawSuggestions, taskTitle])

  const mySuggestions = useMemo(
    () => Object.values(suggestions).flat().filter(x => mySuggestionIds.has(x.id) && x.status === 'pending'),
    [suggestions, mySuggestionIds])

  const conversations = useMemo(() => convs.map(c => ({ ...c, memberIds: memberIds[c.id] ?? [] })), [convs, memberIds])

  // ---- loaders -------------------------------------------------------------------------------
  const loadConversationTasks = useCallback(async (id: string) => {
    const list = await call(api.GET('/conversations/{conversation_id}/tasks', { params: { path: { conversation_id: id } } }))
    setTasks(t => ({ ...t, [id]: list.map(toTask) }))
  }, [])
  const loadMyTasks = useCallback(async () => {
    setMyTasks((await call(api.GET('/users/{user_id}/tasks', { params: { path: { user_id: meId } } }))).map(toTask))
  }, [meId])
  const loadSuggestions = useCallback(async (id: string) => {
    const list = await call(api.GET('/conversations/{conversation_id}/suggestions', { params: { path: { conversation_id: id } } }))
    setRawSuggestions(s => ({ ...s, [id]: list }))
  }, [])
  const loadMessages = useCallback(async (id: string, beforeSeq?: number) => {
    const page = await call(api.GET('/conversations/{conversation_id}/messages', {
      params: { path: { conversation_id: id }, query: { limit: 50, ...(beforeSeq ? { before_seq: beforeSeq } : {}) } },
    }))
    const items = page.items.filter(m => !m.deleted_at).map(toMessage)
    setMessages(m => ({ ...m, [id]: items.reduce(upsert, m[id] ?? []) }))
    setHasMore(h => ({ ...h, [id]: page.has_more }))
    const top = Math.max(0, ...page.items.map(m => m.seq))
    if (!beforeSeq) cursors.current[id] ??= null
    return top
  }, [])

  const markRead = useCallback(async (id: string, seq: number) => {
    setConvs(cs => cs.map(c => (c.id === id ? { ...c, unread: 0 } : c)))
    if (seq > 0) {
      await call(api.PUT('/conversations/{conversation_id}/read', { params: { path: { conversation_id: id } }, body: { last_read_seq: seq } })).catch(() => {})
    }
  }, [])

  // ---- boot ------------------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [users, mine, notes, subs, forMe] = await Promise.all([
          call(api.GET('/users', { params: { query: {} } })),
          call(api.GET('/conversations', { params: { query: { scope: 'mine' } } })),
          call(api.GET('/notifications', { params: { query: { limit: 30 } } })),
          call(api.GET('/me/subordinates')),
          call(api.GET('/me/suggestions')),
        ])
        if (cancelled) return
        setPeople(users.map(toUser))
        setConvs(mine.map(toConversation))
        setNotifications(notes.map(toNotification))
        setMySuggestionIds(new Set(forMe.map(x => x.id)))
        setRawSuggestions(m => {
          const next = { ...m }
          for (const x of forMe) next[x.conversation_id] = [...(next[x.conversation_id] ?? []).filter(y => y.id !== x.id), x]
          return next
        })
        const ids = new Set(subs.map(s => s.id))
        setReports(users.filter(u => ids.has(u.id)).map(toUser))
        await loadMyTasks()
      } catch (e) { fail(e) } finally { if (!cancelled) setLoading(false) }
    })()
    return () => { cancelled = true }
  }, [fail, loadMyTasks])

  // ---- live updates ----------------------------------------------------------------------------
  const applyFrame = useCallback((f: ServerFrame) => {
    const cid = f.conversation_id
    if (f.event_id != null && cid) cursors.current[cid] = Math.max(cursors.current[cid] ?? 0, f.event_id)
    const d = f.data as Record<string, unknown>
    switch (f.type) {
      case 'hello': setOnline(new Set((d.online_user_ids as string[]) ?? [])); break
      case 'presence.changed':
        setOnline(o => { const n = new Set(o); if (d.online) n.add(d.user_id as string); else n.delete(d.user_id as string); return n })
        break
      case 'message.created': case 'message.updated': {
        const raw = d.message as S['Message'] | undefined
        if (!raw) break
        const m = toMessage(raw)
        if (m.parentId) {
          setThreads(t => (t[m.parentId!] || f.type === 'message.created' ? { ...t, [m.parentId!]: upsert(t[m.parentId!] ?? [], m) } : t))
          if (f.type === 'message.created') {
            setMessages(ms => ({ ...ms, [m.conversationId]: (ms[m.conversationId] ?? []).map(x => (x.id === m.parentId ? { ...x, replyCount: x.replyCount + 1 } : x)) }))
          }
          if (!raw.also_in_channel) break
        }
        setMessages(ms => ({ ...ms, [m.conversationId]: upsert(ms[m.conversationId] ?? [], m) }))
        if (f.type === 'message.created' && m.authorId !== meId) {
          if (m.conversationId === active.current && document.hasFocus()) void markRead(m.conversationId, m.seq)
          else setConvs(cs => cs.map(c => (c.id === m.conversationId ? { ...c, unread: c.unread + 1, lastSeq: Math.max(c.lastSeq, m.seq) } : c)))
        }
        break
      }
      case 'message.deleted': {
        const id = d.message_id as string
        setMessages(ms => (cid ? { ...ms, [cid]: (ms[cid] ?? []).filter(m => m.id !== id) } : ms))
        setThreads(t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k, v.filter(m => m.id !== id)])))
        break
      }
      case 'reaction.added': case 'reaction.removed': {
        const id = d.message_id as string
        const rs = reactionsRecord((d.reactions as S['ReactionSummary'][]) ?? [])
        const patch = (m: Message) => (m.id === id ? { ...m, reactions: rs } : m)
        if (cid) setMessages(ms => ({ ...ms, [cid]: (ms[cid] ?? []).map(patch) }))
        setThreads(t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k, v.map(patch)])))
        break
      }
      case 'conversation.updated': {
        const c = d.conversation as S['Conversation'] | undefined
        if (c) setConvs(cs => cs.map(x => (x.id === c.id ? { ...toConversation(c), unread: x.unread, memberIds: x.memberIds } : x)))
        break
      }
      case 'member.joined': case 'member.left':
        if (cid) {
          loaded.current.delete(`members:${cid}`)
          if (cid === active.current) void call(api.GET('/conversations/{conversation_id}/members', { params: { path: { conversation_id: cid } } }))
            .then(ms => setMemberIds(m => ({ ...m, [cid]: ms.map(x => x.user.id) }))).catch(() => {})
        }
        break
      case 'task.created': case 'task.updated':
        void loadMyTasks().catch(() => {})
        if (cid && loaded.current.has(`tasks:${cid}`)) void loadConversationTasks(cid).catch(() => {})
        break
      case 'suggestion.created': case 'suggestion.decided': {
        const s = d.suggestion as S['Suggestion'] | undefined
        if (s && f.type === 'suggestion.created' && (s.payload as { assignee_id?: string }).assignee_id === meId) setMySuggestionIds(ids => new Set(ids).add(s.id))
        if (s) setRawSuggestions(m => {
          const list = m[s.conversation_id] ?? []
          return { ...m, [s.conversation_id]: list.some(x => x.id === s.id) ? list.map(x => (x.id === s.id ? s : x)) : [...list, s] }
        })
        break
      }
      case 'notification.created': {
        const n = d.notification as S['Notification'] | undefined
        if (n) setNotifications(ns => [toNotification(n), ...ns.filter(x => x.id !== n.id)])
        break
      }
      case 'resync_required':
        if (cid) { delete cursors.current[cid]; setMessages(ms => { const rest = { ...ms }; delete rest[cid]; return rest }); loaded.current.delete(`messages:${cid}`) }
        break
    }
  }, [loadConversationTasks, loadMyTasks, markRead, meId])

  // Coming back to the window counts as reading the open conversation.
  useEffect(() => {
    const onFocus = () => {
      const id = active.current
      const c = id ? convsRef.current.find(x => x.id === id) : undefined
      if (c && c.unread > 0) void markRead(c.id, c.lastSeq)
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [markRead])

  const applyRef = useRef(applyFrame)
  useEffect(() => { applyRef.current = applyFrame }, [applyFrame])

  useEffect(() => {
    const s = new ChatSocket({ cursors: () => cursors.current, onFrame: f => applyRef.current(f), onStatus: setConnected })
    socket.current = s
    s.connect()
    return () => s.close()
  }, [])

  // ---- opening a conversation ------------------------------------------------------------------
  const open = useCallback(async (id: string) => {
    try {
      const jobs: Promise<unknown>[] = []
      if (!loaded.current.has(`messages:${id}`)) { loaded.current.add(`messages:${id}`); jobs.push(loadMessages(id)) }
      if (!loaded.current.has(`members:${id}`)) {
        loaded.current.add(`members:${id}`)
        jobs.push(call(api.GET('/conversations/{conversation_id}/members', { params: { path: { conversation_id: id } } }))
          .then(ms => setMemberIds(m => ({ ...m, [id]: ms.map(x => x.user.id) }))))
      }
      if (!loaded.current.has(`tasks:${id}`)) { loaded.current.add(`tasks:${id}`); jobs.push(loadConversationTasks(id)) }
      if (!loaded.current.has(`suggestions:${id}`)) { loaded.current.add(`suggestions:${id}`); jobs.push(loadSuggestions(id)) }
      await Promise.all(jobs)
      const conv = convs.find(c => c.id === id)
      if (conv?.isMember) {
        const real = (messages[id] ?? []).filter(m => !m.pending).map(m => m.seq)
        await markRead(id, Math.max(conv.lastSeq, ...real))
      }
    } catch (e) { loaded.current.delete(`messages:${id}`); fail(e) }
  }, [convs, fail, loadConversationTasks, loadMessages, loadSuggestions, markRead, messages])

  // ---- actions ---------------------------------------------------------------------------------
  const send = useCallback(async (conversationId: string, body: string, parentId?: string, files: File[] = []) => {
    const clientId = crypto.randomUUID()
    const text = withMentionLinks(body, directory) || files.map(f => f.name).join(', ')
    const now = new Date().toISOString()
    const optimistic: Message = { id: clientId, clientId, seq: Number.MAX_SAFE_INTEGER, conversationId, authorId: meId, time: formatTime(now), createdAt: now, body: text, reactions: {}, parentId, replyCount: 0, pending: true }
    const put = (m: Message) => (parentId
      ? setThreads(t => ({ ...t, [parentId]: upsert(t[parentId] ?? [], m) }))
      : setMessages(ms => ({ ...ms, [conversationId]: upsert(ms[conversationId] ?? [], m) })))
    put(optimistic)
    try {
      const fileIds: string[] = []
      for (const file of files) {
        const form = new FormData()
        form.append('file', file)
        form.append('conversation_id', conversationId)
        const res = await fetch('/files', { method: 'POST', body: form, credentials: 'include' })
        if (!res.ok) throw new Error(`Could not upload ${file.name}.`)
        fileIds.push(((await res.json()) as S['FileMeta']).id)
      }
      const saved = await call(api.POST('/conversations/{conversation_id}/messages', {
        params: { path: { conversation_id: conversationId } }, body: { client_id: clientId, body_md: text, parent_id: parentId ?? null, also_in_channel: false, file_ids: fileIds },
      }))
      put(toMessage(saved))
      if (parentId) setMessages(ms => ({ ...ms, [conversationId]: (ms[conversationId] ?? []).map(x => (x.id === parentId ? { ...x, replyCount: Math.max(x.replyCount, 1) } : x)) }))
    } catch (e) {
      put({ ...optimistic, failed: true })
      fail(e)
    }
  }, [directory, fail, meId])

  const patchMessage = (conversationId: string, id: string, fn: (m: Message) => Message) => {
    setMessages(ms => ({ ...ms, [conversationId]: (ms[conversationId] ?? []).map(m => (m.id === id ? fn(m) : m)) }))
    setThreads(t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k, v.map(m => (m.id === id ? fn(m) : m))])))
  }

  const edit = useCallback(async (conversationId: string, id: string, body: string) => {
    try {
      const m = toMessage(await call(api.PATCH('/messages/{message_id}', { params: { path: { message_id: id } }, body: { body_md: withMentionLinks(body, directory) } })))
      patchMessage(conversationId, id, () => m)
    } catch (e) { fail(e) }
  }, [directory, fail])

  const remove = useCallback(async (conversationId: string, id: string) => {
    try {
      await call(api.DELETE('/messages/{message_id}', { params: { path: { message_id: id } } }))
      setMessages(ms => ({ ...ms, [conversationId]: (ms[conversationId] ?? []).filter(m => m.id !== id) }))
      setThreads(t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k, v.filter(m => m.id !== id)])))
    } catch (e) { fail(e) }
  }, [fail])

  const react = useCallback(async (conversationId: string, id: string, emoji: string) => {
    const all = [...(messages[conversationId] ?? []), ...Object.values(threads).flat()]
    const mine = all.find(m => m.id === id)?.reactions[emoji]?.includes(meId)
    const params = { params: { path: { message_id: id, emoji } } }
    try {
      const rs = await call(mine ? api.DELETE('/messages/{message_id}/reactions/{emoji}', params) : api.PUT('/messages/{message_id}/reactions/{emoji}', params))
      patchMessage(conversationId, id, m => ({ ...m, reactions: reactionsRecord(rs) }))
    } catch (e) { fail(e) }
  }, [fail, meId, messages, threads])

  const openThread = useCallback(async (parentId: string) => {
    try {
      const t = await call(api.GET('/messages/{message_id}/thread', { params: { path: { message_id: parentId } } }))
      setThreads(x => ({ ...x, [parentId]: t.replies.filter(r => !r.deleted_at).map(toMessage) }))
    } catch (e) { fail(e) }
  }, [fail])

  const setTaskStatus = useCallback(async (id: string, status: TaskStatus) => {
    const patch = (list: Task[]) => list.map(t => (t.id === id ? { ...t, status } : t))
    setMyTasks(patch); setTasks(t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k, patch(v)])))
    setReportTasks(t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k, patch(v)])))
    try { await call(api.PATCH('/tasks/{task_id}', { params: { path: { task_id: id } }, body: { status } })) } catch (e) { fail(e); void loadMyTasks() }
  }, [fail, loadMyTasks])

  const loadReportTasks = useCallback(async (userId: string) => {
    try {
      const list = await call(api.GET('/users/{user_id}/tasks', { params: { path: { user_id: userId } } }))
      setReportTasks(t => ({ ...t, [userId]: list.map(toTask) }))
    } catch (e) { fail(e) }
  }, [fail])

  const decide = useCallback(async (s: Suggestion, how: 'accept' | 'reject' | 'modify', over?: Partial<Pick<Suggestion, 'title' | 'assigneeId' | 'project' | 'due'>>, invite = false) => {
    try {
      if (invite && s.assigneeId) {
        await call(api.POST('/conversations/{conversation_id}/members', { params: { path: { conversation_id: s.conversationId } }, body: { user_ids: [s.assigneeId] } }))
        loaded.current.delete(`members:${s.conversationId}`)
        setMemberIds(m => ({ ...m, [s.conversationId]: [...(m[s.conversationId] ?? []), s.assigneeId] }))
      }
      const path = { params: { path: { suggestion_id: s.id } } }
      const res = how === 'accept' ? await call(api.POST('/suggestions/{suggestion_id}/accept', path))
        : how === 'reject' ? await call(api.POST('/suggestions/{suggestion_id}/reject', path))
        : await call(api.POST('/suggestions/{suggestion_id}/modify', { ...path, body: {
          title: over?.title ?? s.title, description_md: s.description, assignee_id: over?.assigneeId ?? s.assigneeId,
          project: (over?.project ?? s.project) || null, due_at: (over?.due ?? s.due) ? `${over?.due ?? s.due}T00:00:00Z` : null,
          source_message_ids: s.sourceMessageId ? [s.sourceMessageId] : [],
        } }))
      setRawSuggestions(m => ({ ...m, [s.conversationId]: (m[s.conversationId] ?? []).map(x => (x.id === s.id ? res.suggestion : x)) }))
      if (res.task) { void loadMyTasks(); void loadConversationTasks(s.conversationId) }
    } catch (e) { fail(e); void loadSuggestions(s.conversationId) }
  }, [fail, loadConversationTasks, loadMyTasks, loadSuggestions])

  const createConversation = useCallback(async (body: S['ConversationCreate']) => {
    const c = toConversation(await call(api.POST('/conversations', { body })))
    setConvs(cs => (cs.some(x => x.id === c.id) ? cs : [...cs, c]))
    return c
  }, [])
  const join = useCallback(async (id: string) => {
    await call(api.POST('/conversations/{conversation_id}/join', { params: { path: { conversation_id: id } } }))
    const c = toConversation(await call(api.GET('/conversations/{conversation_id}', { params: { path: { conversation_id: id } } })))
    setConvs(cs => (cs.some(x => x.id === id) ? cs.map(x => (x.id === id ? c : x)) : [...cs, c]))
    loaded.current.delete(`members:${id}`)
  }, [])
  const archive = useCallback(async (id: string) => {
    await call(api.POST('/conversations/{conversation_id}/archive', { params: { path: { conversation_id: id } } }))
    setConvs(cs => cs.filter(c => c.id !== id))
  }, [])
  /** Makes a conversation known to the sidebar state (e.g. a public channel found through search). */
  const ensure = useCallback(async (id: string) => {
    if (convs.some(c => c.id === id)) return
    const c = toConversation(await call(api.GET('/conversations/{conversation_id}', { params: { path: { conversation_id: id } } })))
    setConvs(cs => (cs.some(x => x.id === id) ? cs : [...cs, c]))
  }, [convs])
  const browse = useCallback(async () => (await call(api.GET('/conversations', { params: { query: { scope: 'browse' } } }))).map(toConversation), [])

  const toggleTeamSync = useCallback(async (c: Conversation) => {
    const next = !c.aiEnabled
    setConvs(cs => cs.map(x => (x.id === c.id ? { ...x, aiEnabled: next } : x)))
    try {
      const updated = c.kind === 'dm'
        ? await call(api.PATCH('/conversations/{conversation_id}/membership', { params: { path: { conversation_id: c.id } }, body: { ai_opt_in: next } }))
        : await call(api.PATCH('/admin/conversations/{conversation_id}/ai', { params: { path: { conversation_id: c.id } }, body: { ai_enabled: next } }))
      void updated
      const fresh = toConversation(await call(api.GET('/conversations/{conversation_id}', { params: { path: { conversation_id: c.id } } })))
      setConvs(cs => cs.map(x => (x.id === c.id ? { ...fresh, unread: x.unread } : x)))
    } catch (e) { setConvs(cs => cs.map(x => (x.id === c.id ? { ...x, aiEnabled: c.aiEnabled } : x))); fail(e) }
  }, [fail])

  const search = useCallback(async (q: string) => call(api.GET('/search', { params: { query: { q, limit: 8 } } })), [])

  const markNotificationRead = useCallback((id: string) => {
    setNotifications(ns => ns.map(n => (n.id === id ? { ...n, read: true } : n)))
    void call(api.POST('/notifications/{notification_id}/read', { params: { path: { notification_id: id } } })).catch(() => {})
  }, [])
  const markAllNotificationsRead = useCallback(() => {
    setNotifications(ns => ns.map(n => ({ ...n, read: true })))
    void call(api.POST('/notifications/read-all')).catch(() => {})
  }, [])

  return {
    meId, people: directory, connected, loading, error, clearError: () => setError(null),
    conversations, mySuggestions, messages, hasMore, threads, tasks, myTasks, reports, reportTasks, suggestions, notifications, online,
    open, loadOlder: (id: string, seq: number) => loadMessages(id, seq).catch(fail), send, edit, remove, react, openThread,
    setTaskStatus, loadReportTasks, accept: (s: Suggestion, invite = false) => decide(s, 'accept', undefined, invite), reject: (s: Suggestion) => decide(s, 'reject'),
    modify: (s: Suggestion, over: Partial<Pick<Suggestion, 'title' | 'assigneeId' | 'project' | 'due'>>) => decide(s, 'modify', over),
    createConversation, join, archive, browse, ensure, toggleTeamSync, search, markNotificationRead, markAllNotificationsRead,
    sendTyping: (id: string, parent: string | null = null) => socket.current?.sendTyping(id, parent),
  }
}
