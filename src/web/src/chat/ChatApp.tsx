import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ClipboardList, Hash, Lock, Menu, MessageSquare, MoreHorizontal, Sparkles, Users, WifiOff, X } from 'lucide-react'
import './chat.css'
import type { components } from '../api/schema'
import type { Conversation, Suggestion, TaskStatus } from './types'
import { toUser } from './adapt'
import { conversationTitle, dmPartner, userById } from './data'
import { useChatData } from './useChatData'
import Sidebar, { type View } from './Sidebar'
import TopBar from './TopBar'
import MessageItem from './MessageItem'
import Composer from './Composer'
import TeamSyncPanel from './TeamSyncPanel'
import { AdminView, ConversationTasks, MyTasks } from './TaskViews'
import { Avatar, Dialog } from './ui'

type Modal = null | 'browse' | 'channel' | 'dm' | { modify: Suggestion } | { remove: string } | { archive: string }

export default function ChatApp({ meUser, onLogout }: { meUser: components['schemas']['User']; onLogout: () => void }) {
  const [view, setView] = useState<View>('chat')
  const [activeId, setActiveId] = useState<string | null>(null)
  const [tab, setTab] = useState<'messages' | 'tasks'>('messages')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [threadId, setThreadId] = useState<string | null>(null)
  const [modal, setModal] = useState<Modal>(null)
  const [navOpen, setNavOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)
  const [jump, setJump] = useState<string | null>(null)
  const scroller = useRef<HTMLDivElement>(null)

  const d = useChatData(meUser, activeId)
  const meId = d.meId
  const me = userById(meId) ?? toUser(meUser)

  const visible = d.conversations.filter(c => !c.archived)
  const conversation: Conversation | undefined = visible.find(c => c.id === activeId)
    ?? visible.find(c => c.isMember && c.kind === 'channel') ?? visible.find(c => c.isMember) ?? visible[0]
  const convId = conversation?.id
  const title = conversation ? conversationTitle(conversation, meId) : ''
  const topLevel = useMemo(() => (convId ? d.messages[convId] ?? [] : []), [d.messages, convId])
  const convTasks = convId ? d.tasks[convId] ?? [] : []
  const convSuggestions = convId ? d.suggestions[convId] ?? [] : []
  const pendingCount = convSuggestions.filter(s => s.status === 'pending').length
  const approvedCount = convSuggestions.filter(s => s.status === 'accepted').length
  const members = (conversation?.memberIds ?? []).map(userById).filter(Boolean) as NonNullable<ReturnType<typeof userById>>[]
  const partner = conversation?.kind === 'dm' ? dmPartner(conversation, meId) : undefined
  const thread = threadId ? topLevel.find(m => m.id === threadId) : undefined
  const replies = threadId ? d.threads[threadId] ?? [] : []
  const myOpenTasks = d.myTasks.filter(t => t.status === 'open' || t.status === 'in_progress').length

  const isAdmin = me.role === 'admin'
  const canSwitchAi = !!conversation && (conversation.kind === 'dm' ? conversation.isMember : conversation.isOwner || isAdmin)
  const tsOn = !!conversation?.aiEnabled

  // Load a conversation's messages, members, tasks and suggestions the first time it is shown.
  const open = d.open
  useEffect(() => { if (!d.loading && convId) void open(convId) }, [d.loading, convId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Stay at the bottom as messages arrive; jump to a searched message when asked.
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
  }, [convId, topLevel.length, convSuggestions.length, tab, view, jump, tsOn])

  async function selectConversation(id: string) {
    setView('chat'); setActiveId(id); setTab('messages'); setThreadId(null); setNavOpen(false); setMoreOpen(false)
    await d.ensure(id).catch(() => {})
  }
  const openThread = (id: string | null) => { setThreadId(id); if (id) { setPanelOpen(false); void d.openThread(id) } }
  const togglePanel = () => { setPanelOpen(o => !o); setThreadId(null) }

  const deleteTarget = typeof modal === 'object' && modal && 'remove' in modal ? modal.remove : null
  const archiveTarget = typeof modal === 'object' && modal && 'archive' in modal ? modal.archive : null
  const modifyTarget = typeof modal === 'object' && modal && 'modify' in modal ? modal.modify : null
  const crumb = view === 'chat' ? title : view === 'tasks' ? 'My tasks' : 'Admin & people'
  const topBar = (embedded: boolean) => (
    <TopBar embedded={embedded} me={me} crumb={crumb} notifications={d.notifications} onSearch={d.search}
      onMenu={() => setNavOpen(true)}
      onOpenResult={(cid, mid) => { void selectConversation(cid).then(() => setJump(mid)) }}
      onOpenNotification={n => { if (n.conversationId) void selectConversation(n.conversationId); d.markNotificationRead(n.id) }}
      onMarkAllRead={d.markAllNotificationsRead} />
  )

  if (d.loading) return <div className="shell shell--center"><p className="muted">Loading your workspace…</p></div>

  return (
    <div className="shell">
      <div className="app">
        <Sidebar me={me} conversations={visible} activeId={convId ?? ''} view={view} myTaskCount={myOpenTasks}
          open={navOpen} onClose={() => setNavOpen(false)} onSelect={id => void selectConversation(id)} onView={v => { setView(v); setNavOpen(false) }}
          onBrowse={() => setModal('browse')} onNewChannel={() => setModal('channel')} onNewMessage={() => setModal('dm')} />

        <main className="main" inert={navOpen}>
          {view !== 'chat' && topBar(false)}

          {view === 'tasks' && (
            <div className="scroll"><MyTasks me={me} tasks={d.myTasks} reports={d.reports} reportTasks={d.reportTasks} onLoadReport={d.loadReportTasks} onStatus={d.setTaskStatus} /></div>
          )}
          {view === 'admin' && <div className="scroll"><AdminView people={d.people} /></div>}

          {view === 'chat' && !conversation && (
            <div className="empty"><MessageSquare size={28} /><h3>No conversations yet</h3><p>Join a channel or start a message from the sidebar.</p></div>
          )}

          {view === 'chat' && conversation && (
            <div className="chatview">
              <div className="chead">
                <button className="icon-btn topbar__menu" aria-label="Open navigation" onClick={() => setNavOpen(true)}><Menu size={20} /></button>
                <span className="chead__tile">
                  {conversation.kind === 'channel' && (conversation.isPublic ? <Hash size={20} /> : <Lock size={18} />)}
                  {conversation.kind === 'department' && <Users size={19} />}
                  {conversation.kind === 'dm' && <Avatar user={partner} size={36} presence />}
                </span>
                <div className="chead__copy">
                  <h1>{conversation.kind === 'channel' ? `# ${title}` : title}</h1>
                  <p>{conversation.kind === 'dm' ? `${partner?.title ?? ''}${partner?.department ? ` · ${partner.department}` : ''}` : conversation.description || `${conversation.memberCount} members`}</p>
                </div>
                <div className="chead__right">
                  {!d.connected && <span className="conn" role="status"><WifiOff size={13} /> Reconnecting…</span>}
                  <button className={`ts-toggle${tsOn ? ' is-on' : ''}`} aria-pressed={tsOn} disabled={!canSwitchAi} onClick={() => void d.toggleTeamSync(conversation)}
                    title={!canSwitchAi ? 'Only the channel owner can turn TeamSync on or off'
                      : conversation.kind === 'dm' ? (conversation.aiActive ? 'TeamSync is reading this DM because you both allowed it' : 'TeamSync reads a DM only when you both allow it') : 'Turn TeamSync on or off for this conversation'}>
                    <Sparkles size={16} /><span className="ts-toggle__label">TeamSync {tsOn ? 'on' : 'off'}</span>
                  </button>
                  <button className={`icon-btn icon-btn--box icon-btn--lg icon-btn--count${panelOpen ? ' is-on' : ''}`}
                    aria-label={`TeamSync overview, ${conversation.memberCount} members and shared resources`} aria-pressed={panelOpen} onClick={togglePanel}>
                    <ClipboardList size={19} /><span className="btn-count">{conversation.memberCount}</span>{tsOn && pendingCount > 0 && <span className="icon-btn__dot" />}
                  </button>
                  <div className="members-wrap">
                    <button className="icon-btn icon-btn--lg" aria-label="More options" aria-expanded={moreOpen} onClick={() => setMoreOpen(o => !o)}><MoreHorizontal size={20} /></button>
                    {moreOpen && (
                      <div className="popover popover--menu">
                        <button disabled={conversation.kind !== 'channel' || !(conversation.isOwner || isAdmin)} onClick={() => { setMoreOpen(false); setModal({ archive: conversation.id }) }}>Archive channel</button>
                        <button onClick={onLogout}>Sign out</button>
                      </div>
                    )}
                  </div>
                </div>
                {topBar(true)}
              </div>

              <div className="chat">
                <div className="chat__col">
                  <div className="tabs" role="tablist">
                    <button role="tab" aria-selected={tab === 'messages'} className={tab === 'messages' ? 'is-on' : ''} onClick={() => setTab('messages')}>Messages</button>
                    <button role="tab" aria-selected={tab === 'tasks'} className={tab === 'tasks' ? 'is-on' : ''} onClick={() => setTab('tasks')}>Tasks <span className="count count--soft">{convTasks.length}</span></button>
                  </div>

                  {tab === 'tasks' ? (
                    <div className="scroll"><ConversationTasks conversation={conversation} tasks={convTasks} onStatus={(id: string, s: TaskStatus) => void d.setTaskStatus(id, s)} /></div>
                  ) : (
                    <>
                      <div className="messages" ref={scroller} role="log" aria-label={`Messages in ${title}`} tabIndex={0}>
                        {d.hasMore[conversation.id] && topLevel.length > 0 && (
                          <button className="btn btn--small load-more" onClick={() => void d.loadOlder(conversation.id, Math.min(...topLevel.map(m => m.seq)))}>Load earlier messages</button>
                        )}
                        {topLevel.length === 0 && (
                          <div className="empty"><MessageSquare size={28} /><h3>Start the conversation</h3><p>Send the first message to get things going.</p></div>
                        )}
                        {topLevel.map(m => (
                          <MessageItem key={m.clientId ?? m.id} message={m} meId={meId} replyCount={m.replyCount}
                            onReact={(id, e) => void d.react(conversation.id, id, e)} onReply={openThread}
                            onEdit={(id, body) => void d.edit(conversation.id, id, body)} onDelete={id => setModal({ remove: id })} />
                        ))}
                        {conversation.isMember && tsOn && pendingCount > 0 && (
                          <button className="ts-note ts-note--pending" onClick={() => { setPanelOpen(true); setThreadId(null) }}>
                            <Sparkles size={15} /> TeamSync found {pendingCount} possible {pendingCount === 1 ? 'action' : 'actions'} · Review required
                          </button>
                        )}
                        {conversation.isMember && tsOn && approvedCount > 0 && (
                          <div className="ts-note ts-note--done"><Check size={15} /> TeamSync approved {approvedCount} {approvedCount === 1 ? 'task' : 'tasks'} · Added to this conversation</div>
                        )}
                      </div>
                      {conversation.isMember ? (
                        <Composer value={drafts[conversation.id] ?? ''} onChange={v => setDrafts(x => ({ ...x, [conversation.id]: v }))}
                          onSend={(body, files) => { setDrafts(x => ({ ...x, [conversation.id]: '' })); void d.send(conversation.id, body, undefined, files) }} members={members}
                          placeholder={`Message ${conversation.kind === 'channel' ? '#' : ''}${title}`} />
                      ) : (
                        <div className="join-bar"><span>You’re previewing <strong>#{conversation.name}</strong>.</span>
                          <button className="btn btn--primary" onClick={() => void d.join(conversation.id)}>Join channel</button></div>
                      )}
                    </>
                  )}
                </div>

                {panelOpen && tab === 'messages' && (
                  <TeamSyncPanel conversation={conversation} me={me} members={members} messages={topLevel} tasks={convTasks} suggestions={convSuggestions}
                    on={tsOn} onClose={() => setPanelOpen(false)} onViewTasks={() => setTab('tasks')}
                    onAccept={(s, invite) => void d.accept(s, invite)} onModify={s => setModal({ modify: s })} onReject={s => void d.reject(s)} />
                )}

                {thread && tab === 'messages' && (
                  <aside className="thread" aria-label="Thread">
                    <header><h2>Thread</h2><button className="icon-btn" aria-label="Close thread" onClick={() => setThreadId(null)}><X size={18} /></button></header>
                    <div className="thread__list">
                      <MessageItem message={thread} meId={meId} replyCount={0} inThread onReact={(id, e) => void d.react(conversation.id, id, e)} onReply={() => {}}
                        onEdit={(id, body) => void d.edit(conversation.id, id, body)} onDelete={id => setModal({ remove: id })} />
                      <div className="divider">{replies.length} {replies.length === 1 ? 'reply' : 'replies'}</div>
                      {replies.map(m => (
                        <MessageItem key={m.clientId ?? m.id} message={m} meId={meId} replyCount={0} inThread onReact={(id, e) => void d.react(conversation.id, id, e)} onReply={() => {}}
                          onEdit={(id, body) => void d.edit(conversation.id, id, body)} onDelete={id => setModal({ remove: id })} />
                      ))}
                    </div>
                    {conversation.isMember && <Composer compact value={drafts[`thread:${thread.id}`] ?? ''} onChange={v => setDrafts(x => ({ ...x, [`thread:${thread.id}`]: v }))}
                      onSend={(body, files) => { setDrafts(x => ({ ...x, [`thread:${thread.id}`]: '' })); void d.send(conversation.id, body, thread.id, files) }} members={members} placeholder="Reply in thread…" />}
                  </aside>
                )}
              </div>
            </div>
          )}
        </main>
      </div>

      {d.error && <div className="toast" role="alert"><span>{d.error}</span><button onClick={d.clearError}>Dismiss</button></div>}

      {modal === 'browse' && <BrowseDialog browse={d.browse} meId={meId} onClose={() => setModal(null)}
        onOpen={c => { void d.ensure(c.id).then(() => selectConversation(c.id)); setModal(null) }} onJoin={c => { void d.join(c.id).then(() => selectConversation(c.id)); setModal(null) }} />}
      {modal === 'dm' && (
        <Dialog title="New message" onClose={() => setModal(null)}>
          <ul className="list">
            {d.people.filter(u => u.id !== meId).map(u => (
              <li key={u.id}><button className="list__btn" onClick={() => { void d.createConversation({ kind: 'dm', is_public: false, member_ids: [u.id] }).then(c => selectConversation(c.id)); setModal(null) }}>
                <Avatar user={u} size={34} presence /><div><strong>{u.name}</strong><small>{u.title}</small></div></button></li>
            ))}
          </ul>
        </Dialog>
      )}
      {modal === 'channel' && <NewChannel onClose={() => setModal(null)} onCreate={(name, description, isPublic) => {
        void d.createConversation({ kind: 'channel', name, description, is_public: isPublic }).then(c => selectConversation(c.id)); setModal(null)
      }} />}
      {modifyTarget && conversation && <ModifyTask s={modifyTarget} conversation={conversation} meId={meId} people={d.people} onClose={() => setModal(null)}
        onSave={over => { void d.modify(modifyTarget, over); setModal(null) }} />}
      {deleteTarget && conversation && (
        <Dialog title="Delete this message?" onClose={() => setModal(null)}>
          <p className="muted">This removes your message for everyone in the conversation.</p>
          <div className="dialog__actions"><button className="btn" onClick={() => setModal(null)}>Cancel</button>
            <button className="btn btn--danger" onClick={() => { void d.remove(conversation.id, deleteTarget); setModal(null); if (threadId === deleteTarget) setThreadId(null) }}>Delete message</button></div>
        </Dialog>
      )}
      {archiveTarget && (
        <Dialog title="Archive this channel?" onClose={() => setModal(null)}>
          <p className="muted">The channel disappears from the sidebar. Messages are kept.</p>
          <div className="dialog__actions"><button className="btn" onClick={() => setModal(null)}>Cancel</button>
            <button className="btn btn--danger" onClick={() => { void d.archive(archiveTarget); setModal(null) }}>Archive</button></div>
        </Dialog>
      )}
    </div>
  )
}

function BrowseDialog({ browse, meId, onClose, onOpen, onJoin }: {
  browse: () => Promise<Conversation[]>; meId: string; onClose: () => void; onOpen: (c: Conversation) => void; onJoin: (c: Conversation) => void
}) {
  const [list, setList] = useState<Conversation[] | null>(null)
  useEffect(() => { void browse().then(setList).catch(() => setList([])) }, [browse])
  void meId
  return (
    <Dialog title="Browse channels" onClose={onClose}>
      {list === null ? <p className="muted">Loading…</p> : list.length === 0 ? <p className="muted">No public channels to show.</p> : (
        <ul className="list">
          {list.map(c => (
            <li key={c.id}><div><strong># {c.name}</strong><small>{c.description} · {c.memberCount} members</small></div>
              {c.isMember ? <button className="btn" onClick={() => onOpen(c)}>Open</button> : <button className="btn btn--primary" onClick={() => onJoin(c)}>Join</button>}
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  )
}

function NewChannel({ onClose, onCreate }: { onClose: () => void; onCreate: (name: string, description: string, isPublic: boolean) => void }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [priv, setPriv] = useState(false)
  const slug = name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return (
    <Dialog title="Create channel" onClose={onClose}>
      <form className="form" onSubmit={e => { e.preventDefault(); if (slug) onCreate(slug, desc.trim(), !priv) }}>
        <label>Name<input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. launch-planning" autoFocus /></label>
        {slug && <small className="muted">Will be created as #{slug}</small>}
        <label>Description<input value={desc} onChange={e => setDesc(e.target.value)} placeholder="What is this channel for?" /></label>
        <label className="check"><input type="checkbox" checked={priv} onChange={e => setPriv(e.target.checked)} /> Make private (invite only)</label>
        <div className="dialog__actions"><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn btn--primary" disabled={!slug}>Create channel</button></div>
      </form>
    </Dialog>
  )
}

function ModifyTask({ s, conversation, meId, people, onClose, onSave }: {
  s: Suggestion; conversation: Conversation; meId: string; people: ReturnType<typeof useChatData>['people']; onClose: () => void
  onSave: (over: Partial<Pick<Suggestion, 'title' | 'assigneeId' | 'project' | 'due'>>) => void
}) {
  const [title, setTitle] = useState(s.title)
  const [assigneeId, setAssignee] = useState(s.assigneeId)
  const [project, setProject] = useState(s.project)
  const [due, setDue] = useState(s.due)
  const reports = people.filter(u => u.managerId === meId && !conversation.memberIds.includes(u.id))
  const mems = conversation.memberIds.map(id => people.find(u => u.id === id)).filter(Boolean) as typeof people
  return (
    <Dialog title="Modify and accept" onClose={onClose}>
      <form className="form" onSubmit={e => { e.preventDefault(); if (title.trim()) onSave({ title: title.trim(), assigneeId, project, due }) }}>
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
