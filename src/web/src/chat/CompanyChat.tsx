import { useEffect, useMemo, useRef, useState } from 'react'
import { Hash, Lock, MessageSquare, MoreHorizontal, Users, X } from 'lucide-react'
import './chat.css'
import type { AppNotification, Conversation, FileAttachment, Message, Suggestion, Task, TaskStatus } from './types'
import {
  conversationTitle, conversations as seedConversations, dmPartner, nowLabel, seedMessages, seedNotifications,
  seedSuggestions, seedTasks, seedUnread, userById, users,
} from './data'
import Sidebar, { type View } from './Sidebar'
import TopBar from './TopBar'
import MessageItem from './MessageItem'
import SuggestionCard from './SuggestionCard'
import Composer from './Composer'
import { AdminView, ConversationTasks, MyTasks } from './TaskViews'
import { Avatar, Dialog } from './ui'

type Modal = null | 'browse' | 'channel' | 'dm' | { modify: Suggestion } | { remove: string } | { archive: string }

export default function CompanyChat() {
  const [meId, setMeId] = useState('alice')
  const [view, setView] = useState<View>('chat')
  const [activeId, setActiveId] = useState('ch-website-refresh')
  const [tab, setTab] = useState<'messages' | 'tasks'>('messages')
  const [convs, setConvs] = useState<Conversation[]>(seedConversations)
  const [archived, setArchived] = useState<string[]>([])
  const [messages, setMessages] = useState<Message[]>(seedMessages)
  const [tasks, setTasks] = useState<Task[]>(seedTasks)
  const [suggestions, setSuggestions] = useState<Suggestion[]>(seedSuggestions)
  const [notifications, setNotifications] = useState<AppNotification[]>(seedNotifications)
  const [unread, setUnread] = useState<Record<string, number>>(seedUnread)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [threadId, setThreadId] = useState<string | null>(null)
  const [modal, setModal] = useState<Modal>(null)
  const [navOpen, setNavOpen] = useState(false)
  const [offline, setOffline] = useState(true)
  const [typingOn, setTypingOn] = useState(false)
  const [membersOpen, setMembersOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [jump, setJump] = useState<string | null>(null)
  const scroller = useRef<HTMLDivElement>(null)

  const me = userById(meId)!
  const visibleConvs = convs.filter(c => !archived.includes(c.id))
  const conversation = visibleConvs.find(c => c.id === activeId) ?? visibleConvs.find(c => c.memberIds.includes(meId)) ?? visibleConvs[0]
  const title = conversationTitle(conversation, meId)
  const isMember = conversation.memberIds.includes(meId)
  const topLevel = useMemo(() => messages.filter(m => m.conversationId === conversation.id && !m.parentId), [messages, conversation.id])
  const replyCount = (id: string) => messages.filter(m => m.parentId === id).length

  const convTasks = useMemo(() => conversation.kind === 'department'
    ? tasks.filter(t => userById(t.assigneeId)?.department === conversation.department)
    : tasks.filter(t => t.sourceConversationId === conversation.id), [tasks, conversation])
  const myOpenTasks = tasks.filter(t => t.assigneeId === meId && (t.status === 'open' || t.status === 'in_progress')).length
  const pending = suggestions.filter(s => s.conversationId === conversation.id)
  const thread = threadId ? messages.find(m => m.id === threadId) : undefined

  // Scroll to bottom on conversation / message changes; or to a jumped-to message.
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    if (jump) {
      const target = document.getElementById(`msg-${jump}`)
      if (target) {
        target.scrollIntoView({ block: 'center' })
        target.classList.add('is-flash')
        setTimeout(() => target.classList.remove('is-flash'), 1800)
        setJump(null)
        return
      }
    }
    el.scrollTop = el.scrollHeight
  }, [conversation.id, topLevel.length, suggestions, tab, view, jump])

  function selectConversation(id: string) {
    setView('chat'); setActiveId(id); setTab('messages'); setThreadId(null); setNavOpen(false); setMembersOpen(false); setMoreOpen(false)
    setUnread(u => ({ ...u, [`${meId}:${id}`]: 0 }))
  }
  function changePersona(id: string) {
    setMeId(id)
    const next = userById(id)!
    if (view === 'admin' && next.role !== 'admin') setView('chat')
    const c = visibleConvs.find(x => x.id === activeId)
    if (!c || !(c.isPublic || c.memberIds.includes(id))) {
      const first = visibleConvs.find(x => x.memberIds.includes(id) && x.kind === 'channel') ?? visibleConvs.find(x => x.memberIds.includes(id))
      if (first) setActiveId(first.id)
    }
    setThreadId(null)
  }

  function sendMessage(body: string, files: FileAttachment[], parentId?: string) {
    const msg: Message = { id: crypto.randomUUID(), conversationId: conversation.id, authorId: meId, time: nowLabel(), body, reactions: {}, files: files.length ? files : undefined, parentId, local: true }
    setMessages(ms => [...ms, msg])
    const key = parentId ? `thread:${parentId}` : conversation.id
    setDrafts(d => ({ ...d, [key]: '' }))
  }
  const react = (id: string, emoji: string) => setMessages(ms => ms.map(m => {
    if (m.id !== id) return m
    const cur = m.reactions[emoji] ?? []
    const next = cur.includes(meId) ? cur.filter(x => x !== meId) : [...cur, meId]
    const reactions = { ...m.reactions, [emoji]: next }
    if (!next.length) delete reactions[emoji]
    return { ...m, reactions }
  }))
  const editMessage = (id: string, body: string) => setMessages(ms => ms.map(m => m.id === id ? { ...m, body, edited: true } : m))
  function removeMessage(id: string) {
    setMessages(ms => ms.filter(m => m.id !== id && m.parentId !== id))
    if (threadId === id) setThreadId(null)
    setModal(null)
  }

  function createTask(s: Suggestion, over: Partial<Pick<Suggestion, 'title' | 'assigneeId' | 'project' | 'due'>> = {}, invite = false) {
    const f = { ...s, ...over }
    const task: Task = { id: crypto.randomUUID(), title: f.title, assigneeId: f.assigneeId, project: f.project || undefined, sourceConversationId: s.conversationId, status: 'open', due: f.due || undefined, createdByAi: true }
    setTasks(t => [...t, task])
    if (invite) setConvs(cs => cs.map(c => c.id === s.conversationId && !c.memberIds.includes(f.assigneeId) ? { ...c, memberIds: [...c.memberIds, f.assigneeId] } : c))
    setSuggestions(ss => ss.map(x => x.id === s.id ? { ...x, ...over, status: 'accepted', taskId: task.id } : x))
    setNotifications(n => [{ id: crypto.randomUUID(), text: `Task “${f.title}” assigned to ${userById(f.assigneeId)?.name}`, time: nowLabel(), conversationId: s.conversationId, read: false }, ...n])
    setModal(null)
  }
  const rejectSuggestion = (s: Suggestion) => setSuggestions(ss => ss.map(x => x.id === s.id ? { ...x, status: 'rejected' } : x))
  const setStatus = (id: string, status: TaskStatus) => setTasks(ts => ts.map(t => t.id === id ? { ...t, status } : t))

  function openDm(userId: string) {
    const existing = convs.find(c => c.kind === 'dm' && c.memberIds.length === 2 && c.memberIds.includes(meId) && c.memberIds.includes(userId))
    if (existing) { selectConversation(existing.id); setModal(null); return }
    const c: Conversation = { id: `dm-${meId}-${userId}`, kind: 'dm', name: '', description: 'Direct message', isPublic: false, memberIds: [meId, userId] }
    setConvs(cs => [...cs, c]); selectConversation(c.id); setModal(null)
  }
  function joinChannel(id: string) {
    setConvs(cs => cs.map(c => c.id === id && !c.memberIds.includes(meId) ? { ...c, memberIds: [...c.memberIds, meId] } : c))
    selectConversation(id); setModal(null)
  }

  const deleteTarget = typeof modal === 'object' && modal && 'remove' in modal ? modal.remove : null
  const archiveTarget = typeof modal === 'object' && modal && 'archive' in modal ? modal.archive : null
  const modifyTarget = typeof modal === 'object' && modal && 'modify' in modal ? modal.modify : null
  const stack = view === 'chat' ? title : view === 'tasks' ? 'My tasks' : 'Admin & people'
  const partner = conversation.kind === 'dm' ? dmPartner(conversation, meId) : undefined
  const members = conversation.memberIds.map(id => userById(id)!).filter(Boolean)

  return (
    <div className="shell">
      <div className="app">
        <Sidebar me={me} conversations={visibleConvs} activeId={conversation.id} view={view} unread={unread} myTaskCount={myOpenTasks}
          open={navOpen} onClose={() => setNavOpen(false)} onSelect={selectConversation} onView={v => { setView(v); setNavOpen(false) }}
          onPersona={changePersona} onBrowse={() => setModal('browse')} onNewChannel={() => setModal('channel')} onNewMessage={() => setModal('dm')} />

        <main className="main" inert={navOpen}>
          <TopBar me={me} crumb={stack} conversations={visibleConvs} messages={messages} notifications={notifications}
            onMenu={() => setNavOpen(true)}
            onOpenResult={(cid, mid) => { selectConversation(cid); setJump(mid) }}
            onOpenNotification={n => { selectConversation(n.conversationId); setNotifications(ns => ns.map(x => x.id === n.id ? { ...x, read: true } : x)) }}
            onMarkAllRead={() => setNotifications(ns => ns.map(n => ({ ...n, read: true })))} />

          <div className="banner" role="status">
            <span className="banner__dot" />
            <strong>LOCAL DEMO · no server connected</strong>
            <span className="banner__text">Messages, files, and approvals stay in this browser.</span>
            <span className="banner__right">
              <span>{offline ? 'Simulated offline' : 'Simulated online'}</span>
              <button className="btn btn--small" onClick={() => setOffline(o => !o)}>{offline ? 'Reconnect' : 'Go offline'}</button>
            </span>
          </div>

          {view === 'tasks' && <div className="scroll"><MyTasks me={me} tasks={tasks} onStatus={setStatus} /></div>}
          {view === 'admin' && <div className="scroll"><AdminView /></div>}

          {view === 'chat' && (
            <div className="chat">
              <div className="chat__col">
                <div className="chead">
                  <span className="chead__tile">
                    {conversation.kind === 'channel' && (conversation.isPublic ? <Hash size={22} /> : <Lock size={20} />)}
                    {conversation.kind === 'department' && <Users size={21} />}
                    {conversation.kind === 'dm' && <Avatar user={partner} size={40} presence />}
                  </span>
                  <div className="chead__copy">
                    <h1>{conversation.kind === 'channel' ? `# ${title}` : title}</h1>
                    <p>{conversation.kind === 'dm' ? `${partner?.title} · ${partner?.department}` : conversation.description}</p>
                  </div>
                  <div className="chead__right">
                    <div className="members-wrap">
                      <button className="members" aria-expanded={membersOpen} onClick={() => { setMembersOpen(o => !o); setMoreOpen(false) }}>
                        <Users size={17} /><span>{members.length}</span>
                        <span className="members__stack">{members.slice(0, 3).map(u => <span key={u.id}>{u.initials}</span>)}</span>
                      </button>
                      {membersOpen && (
                        <div className="popover popover--members">
                          <div className="popover__head"><strong>{members.length} members</strong></div>
                          {members.map(u => <div className="member-row" key={u.id}><Avatar user={u} size={30} presence /><div><strong>{u.name}</strong><small>{u.title}</small></div></div>)}
                        </div>
                      )}
                    </div>
                    <div className="members-wrap">
                      <button className="icon-btn icon-btn--lg" aria-label="More options" aria-expanded={moreOpen} onClick={() => { setMoreOpen(o => !o); setMembersOpen(false) }}><MoreHorizontal size={20} /></button>
                      {moreOpen && (
                        <div className="popover popover--menu">
                          <button disabled={conversation.kind !== 'channel'} onClick={() => { setMoreOpen(false); setModal({ archive: conversation.id }) }}>Archive channel</button>
                          <button onClick={() => { setMoreOpen(false); setTypingOn(t => !t) }}>{typingOn ? 'Hide typing demo' : 'Show typing demo'}</button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="tabs" role="tablist">
                  <button role="tab" aria-selected={tab === 'messages'} className={tab === 'messages' ? 'is-on' : ''} onClick={() => setTab('messages')}>Messages</button>
                  <button role="tab" aria-selected={tab === 'tasks'} className={tab === 'tasks' ? 'is-on' : ''} onClick={() => setTab('tasks')}>Tasks <span className="count count--soft">{convTasks.length}</span></button>
                </div>

                {tab === 'tasks' ? (
                  <div className="scroll"><ConversationTasks conversation={conversation} tasks={convTasks} onStatus={setStatus} /></div>
                ) : (
                  <>
                    <div className="messages" ref={scroller} role="log" aria-label={`Messages in ${title}`} tabIndex={0}>
                      {topLevel.length === 0 && pending.length === 0 && (
                        <div className="empty"><MessageSquare size={28} /><h3>Start the conversation</h3><p>Messages you send here stay in this browser.</p></div>
                      )}
                      {topLevel.map(m => (
                        <MessageItem key={m.id} message={m} meId={meId} replyCount={replyCount(m.id)}
                          onReact={react} onReply={setThreadId} onEdit={editMessage} onDelete={id => setModal({ remove: id })} />
                      ))}
                      {isMember && pending.map(s => (
                        <SuggestionCard key={s.id} suggestion={s} conversation={conversation} me={me}
                          source={messages.find(m => m.id === s.sourceMessageId)}
                          onAccept={(x, invite) => createTask(x, {}, invite)} onModify={x => setModal({ modify: x })} onReject={rejectSuggestion} />
                      ))}
                    </div>
                    {isMember ? (
                      <Composer value={drafts[conversation.id] ?? ''} onChange={v => setDrafts(d => ({ ...d, [conversation.id]: v }))}
                        onSend={(b, f) => sendMessage(b, f)} members={members}
                        placeholder={`Message ${conversation.kind === 'channel' ? '#' : ''}${title}`}
                        typingOn={typingOn} onToggleTyping={() => setTypingOn(t => !t)} typingName={members.find(u => u.id !== meId)?.name.split(' ')[0]} />
                    ) : (
                      <div className="join-bar"><span>You’re previewing <strong>#{conversation.name}</strong>.</span><button className="btn btn--primary" onClick={() => joinChannel(conversation.id)}>Join channel</button></div>
                    )}
                  </>
                )}
              </div>

              {thread && tab === 'messages' && (
                <aside className="thread" aria-label="Thread">
                  <header><h2>Thread</h2><button className="icon-btn" aria-label="Close thread" onClick={() => setThreadId(null)}><X size={18} /></button></header>
                  <div className="thread__list">
                    <MessageItem message={thread} meId={meId} replyCount={0} inThread onReact={react} onReply={() => {}} onEdit={editMessage} onDelete={id => setModal({ remove: id })} />
                    <div className="divider">{replyCount(thread.id)} {replyCount(thread.id) === 1 ? 'reply' : 'replies'}</div>
                    {messages.filter(m => m.parentId === thread.id).map(m => (
                      <MessageItem key={m.id} message={m} meId={meId} replyCount={0} inThread onReact={react} onReply={() => {}} onEdit={editMessage} onDelete={id => setModal({ remove: id })} />
                    ))}
                  </div>
                  {isMember && <Composer compact value={drafts[`thread:${thread.id}`] ?? ''} onChange={v => setDrafts(d => ({ ...d, [`thread:${thread.id}`]: v }))}
                    onSend={(b, f) => sendMessage(b, f, thread.id)} members={members} placeholder="Reply in thread…" />}
                </aside>
              )}
            </div>
          )}
        </main>
      </div>

      {modal === 'browse' && (
        <Dialog title="Browse channels" onClose={() => setModal(null)}>
          <ul className="list">
            {visibleConvs.filter(c => c.kind === 'channel' && c.isPublic).map(c => (
              <li key={c.id}><div><strong># {c.name}</strong><small>{c.description} · {c.memberIds.length} members</small></div>
                {c.memberIds.includes(meId) ? <button className="btn" onClick={() => { selectConversation(c.id); setModal(null) }}>Open</button> : <button className="btn btn--primary" onClick={() => joinChannel(c.id)}>Join</button>}
              </li>
            ))}
          </ul>
        </Dialog>
      )}
      {modal === 'dm' && (
        <Dialog title="New message" onClose={() => setModal(null)}>
          <ul className="list">
            {users.filter(u => u.id !== meId).map(u => (
              <li key={u.id}><button className="list__btn" onClick={() => openDm(u.id)}><Avatar user={u} size={34} presence /><div><strong>{u.name}</strong><small>{u.title}</small></div></button></li>
            ))}
          </ul>
        </Dialog>
      )}
      {modal === 'channel' && <NewChannel onClose={() => setModal(null)} onCreate={(name, description, isPublic) => {
        const c: Conversation = { id: `ch-${name}-${Date.now()}`, kind: 'channel', name, description, isPublic, memberIds: [meId] }
        setConvs(cs => [...cs, c]); selectConversation(c.id); setModal(null)
      }} />}
      {modifyTarget && <ModifyTask s={modifyTarget} conversation={convs.find(c => c.id === modifyTarget.conversationId)!} meId={meId} onClose={() => setModal(null)} onSave={(over, invite) => createTask(modifyTarget, over, invite)} />}
      {deleteTarget && (
        <Dialog title="Delete this message?" onClose={() => setModal(null)}>
          <p className="muted">This removes your message and its replies from this local demo.</p>
          <div className="dialog__actions"><button className="btn" onClick={() => setModal(null)}>Cancel</button><button className="btn btn--danger" onClick={() => removeMessage(deleteTarget)}>Delete message</button></div>
        </Dialog>
      )}
      {archiveTarget && (
        <Dialog title="Archive this channel?" onClose={() => setModal(null)}>
          <p className="muted">The channel disappears from the sidebar. Messages are kept.</p>
          <div className="dialog__actions"><button className="btn" onClick={() => setModal(null)}>Cancel</button><button className="btn btn--danger" onClick={() => { setArchived(a => [...a, archiveTarget]); setModal(null) }}>Archive</button></div>
        </Dialog>
      )}
    </div>
  )
}

function NewChannel({ onClose, onCreate }: { onClose: () => void; onCreate: (name: string, description: string, isPublic: boolean) => void }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [priv, setPriv] = useState(false)
  const slug = name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return (
    <Dialog title="Create channel" onClose={onClose}>
      <form className="form" onSubmit={e => { e.preventDefault(); if (slug) onCreate(slug, desc.trim() || 'New channel', !priv) }}>
        <label>Name<input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. launch-planning" autoFocus /></label>
        {slug && <small className="muted">Will be created as #{slug}</small>}
        <label>Description<input value={desc} onChange={e => setDesc(e.target.value)} placeholder="What is this channel for?" /></label>
        <label className="check"><input type="checkbox" checked={priv} onChange={e => setPriv(e.target.checked)} /> Make private (invite only)</label>
        <div className="dialog__actions"><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn btn--primary" disabled={!slug}>Create channel</button></div>
      </form>
    </Dialog>
  )
}

function ModifyTask({ s, conversation, meId, onClose, onSave }: {
  s: Suggestion; conversation: Conversation; meId: string; onClose: () => void
  onSave: (over: Partial<Pick<Suggestion, 'title' | 'assigneeId' | 'project' | 'due'>>, invite: boolean) => void
}) {
  const [title, setTitle] = useState(s.title)
  const [assigneeId, setAssignee] = useState(s.assigneeId)
  const [project, setProject] = useState(s.project)
  const [due, setDue] = useState(s.due)
  const reports = users.filter(u => u.managerId === meId && !conversation.memberIds.includes(u.id))
  const mems = conversation.memberIds.map(id => userById(id)!)
  return (
    <Dialog title="Modify and accept" onClose={onClose}>
      <form className="form" onSubmit={e => { e.preventDefault(); if (title.trim()) onSave({ title: title.trim(), assigneeId, project, due }, false) }}>
        <label>Title<input value={title} onChange={e => setTitle(e.target.value)} autoFocus /></label>
        <label>Assignee
          <select value={assigneeId} onChange={e => setAssignee(e.target.value)}>
            <optgroup label="Channel members">{mems.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</optgroup>
            {reports.length > 0 && <optgroup label="Your reports">{reports.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</optgroup>}
          </select>
        </label>
        <div className="form__row">
          <label>Project<input value={project} onChange={e => setProject(e.target.value)} /></label>
          <label>Due<input type="date" value={due} onChange={e => setDue(e.target.value)} /></label>
        </div>
        <div className="dialog__actions"><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn btn--primary" disabled={!title.trim()}>Create task</button></div>
      </form>
    </Dialog>
  )
}
