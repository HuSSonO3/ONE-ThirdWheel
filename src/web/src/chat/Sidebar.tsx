import { CheckCheck, ChevronDown, Hash, Lock, MessageCircle, Plus, Search, SlidersHorizontal, Users, X } from 'lucide-react'
import type { Conversation, User } from './types'
import { conversationTitle, dmPartner, users } from './data'
import { Avatar } from './ui'

export type View = 'chat' | 'tasks' | 'admin'

interface Props {
  me: User
  conversations: Conversation[]
  activeId: string
  view: View
  unread: Record<string, number>
  myTaskCount: number
  open: boolean
  onClose: () => void
  onSelect: (id: string) => void
  onView: (v: View) => void
  onPersona: (id: string) => void
  onBrowse: () => void
  onNewChannel: () => void
  onNewMessage: () => void
}

export default function Sidebar(p: Props) {
  const mine = p.conversations.filter(c => c.memberIds.includes(p.me.id))
  const dept = mine.filter(c => c.kind === 'department')
  const channels = mine.filter(c => c.kind === 'channel')
  const dms = mine.filter(c => c.kind === 'dm')
  const key = (id: string) => `${p.me.id}:${id}`
  const active = (id: string) => p.view === 'chat' && p.activeId === id

  const row = (c: Conversation) => {
    const n = p.unread[key(c.id)] ?? 0
    const partner = c.kind === 'dm' ? dmPartner(c, p.me.id) : undefined
    return (
      <button key={c.id} className={`nav-row${active(c.id) ? ' is-active' : ''}${n ? ' is-unread' : ''}`}
        aria-current={active(c.id) ? 'page' : undefined} onClick={() => p.onSelect(c.id)}>
        <span className="nav-row__icon">
          {c.kind === 'department' && <Users size={18} />}
          {c.kind === 'channel' && (c.isPublic ? <Hash size={18} /> : <Lock size={17} />)}
          {c.kind === 'dm' && <Avatar user={partner} size={26} presence />}
        </span>
        <span className="nav-row__label">{conversationTitle(c, p.me.id)}</span>
        {n > 0 && <span className="count" aria-label={`${n} unread`}>{n}</span>}
      </button>
    )
  }

  return (
    <>
      {p.open && <button className="scrim" aria-label="Close navigation" onClick={p.onClose} />}
      <aside className={`sidebar${p.open ? ' is-open' : ''}`} aria-label="Workspace navigation">
        <div className="brand">
          <span className="brand__mark"><MessageCircle size={20} /></span>
          <div>
            <div className="brand__name">Northstar</div>
            <div className="brand__sub">Company workspace</div>
          </div>
          <button className="icon-btn brand__close" aria-label="Close navigation" onClick={p.onClose}><X size={18} /></button>
        </div>

        <div className="sidebar__scroll">
          <button className="ws-switch" aria-label="Workspace: Northstar (demo)" title="Single demo workspace">
            <span className="ws-switch__n">N</span>
            <span><strong>Northstar</strong><small>Demo workspace</small></span>
            <ChevronDown size={16} />
          </button>

          <nav className="nav" aria-label="Primary">
            <button className={`nav-row nav-row--primary${p.view === 'chat' ? ' is-active' : ''}`} onClick={() => p.onView('chat')} aria-current={p.view === 'chat' ? 'page' : undefined}>
              <span className="nav-row__icon"><MessageCircle size={18} /></span><span className="nav-row__label">Chat</span>
            </button>
            <button className={`nav-row nav-row--primary${p.view === 'tasks' ? ' is-active' : ''}`} onClick={() => p.onView('tasks')} aria-current={p.view === 'tasks' ? 'page' : undefined}>
              <span className="nav-row__icon"><CheckCheck size={18} /></span><span className="nav-row__label">My tasks</span>
              <span className="count count--soft">{p.myTaskCount}</span>
            </button>
          </nav>

          <div className="nav-section"><span>Departments</span></div>
          {dept.map(row)}

          <div className="nav-section"><span>Channels</span><button className="icon-btn" aria-label="Create channel" onClick={p.onNewChannel}><Plus size={15} /></button></div>
          {channels.map(row)}
          <button className="nav-row" onClick={p.onBrowse}><span className="nav-row__icon"><Search size={17} /></span><span className="nav-row__label">Browse channels</span></button>

          <div className="nav-section"><span>Direct messages</span><button className="icon-btn" aria-label="New message" onClick={p.onNewMessage}><Plus size={15} /></button></div>
          {dms.map(row)}
          <button className="nav-row" onClick={p.onNewMessage}><span className="nav-row__icon"><Plus size={17} /></span><span className="nav-row__label">New message</span></button>
        </div>

        <div className="sidebar__foot">
          <div className="me">
            <Avatar user={p.me} size={40} />
            <div><strong>{p.me.name}</strong><small>{p.me.title}</small></div>
            <ChevronDown size={16} />
          </div>
          <div className="persona">
            <label htmlFor="persona">Demo persona</label>
            <select id="persona" value={p.me.id} onChange={e => p.onPersona(e.target.value)}>
              {users.map(u => <option key={u.id} value={u.id}>{u.name} · {u.role}</option>)}
            </select>
          </div>
          {p.me.role === 'admin' && (
            <button className={`nav-row${p.view === 'admin' ? ' is-active' : ''}`} onClick={() => p.onView('admin')}>
              <span className="nav-row__icon"><SlidersHorizontal size={17} /></span><span className="nav-row__label">Admin &amp; people</span>
            </button>
          )}
        </div>
      </aside>
    </>
  )
}
