import { useEffect, useState } from 'react'
import { CheckCheck, Hash, Lock, MessageCircle, MessagesSquare, Plus, Search, SlidersHorizontal, Users, X } from 'lucide-react'
import type { Conversation, User } from './types'
import { conversationTitle, dmPartner } from './data'
import { Avatar } from './ui'

export type View = 'chat' | 'tasks' | 'admin'
type ListTab = 'channels' | 'dms'

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
  const unreadIn = (list: Conversation[]) => list.reduce((n, c) => n + (p.unread[key(c.id)] ?? 0), 0)

  const activeKind = p.conversations.find(c => c.id === p.activeId)?.kind
  const [listTab, setListTab] = useState<ListTab>(activeKind === 'dm' ? 'dms' : 'channels')
  // Follow the conversation when it is opened from search, a notification or a new DM.
  useEffect(() => { setListTab(activeKind === 'dm' ? 'dms' : 'channels') }, [p.activeId, activeKind])

  const active = (id: string) => p.view === 'chat' && p.activeId === id
  const showList = p.view === 'chat'

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

  const tab = (id: ListTab, label: string, icon: React.ReactNode, badge: number) => {
    const on = p.view === 'chat' && listTab === id
    return (
      <button className={`rail__tab${on ? ' is-active' : ''}`} aria-current={on ? 'page' : undefined}
        onClick={() => { setListTab(id); p.onView('chat') }}>
        <span className="rail__icon">{icon}{badge > 0 && <i className="rail__badge">{badge}</i>}</span>{label}
      </button>
    )
  }

  return (
    <>
      {p.open && <button className="scrim" aria-label="Close navigation" onClick={p.onClose} />}
      <aside className={`sidebar${p.open ? ' is-open' : ''}${showList ? '' : ' is-rail-only'}`} aria-label="Workspace navigation">
        <nav className="rail" aria-label="Primary">
          <span className="brand__mark" title="Northstar"><MessageCircle size={20} /></span>
          {tab('channels', 'Channels', <Hash size={21} />, unreadIn([...dept, ...channels]))}
          {tab('dms', 'DMs', <MessagesSquare size={21} />, unreadIn(dms))}
          <button className={`rail__tab${p.view === 'tasks' ? ' is-active' : ''}`} aria-current={p.view === 'tasks' ? 'page' : undefined} onClick={() => p.onView('tasks')}>
            <span className="rail__icon"><CheckCheck size={21} />{p.myTaskCount > 0 && <i className="rail__badge">{p.myTaskCount}</i>}</span>My tasks
          </button>
          <span className="rail__spacer" />
          {p.me.role === 'admin' && (
            <button className={`rail__tab${p.view === 'admin' ? ' is-active' : ''}`} aria-current={p.view === 'admin' ? 'page' : undefined} onClick={() => p.onView('admin')}>
              <span className="rail__icon"><SlidersHorizontal size={20} /></span>Admin
            </button>
          )}
          <span className="rail__me" title={`${p.me.name} · ${p.me.title}`}><Avatar user={p.me} size={38} presence /></span>
        </nav>

        {showList && (
          <div className="panel">
            <div className="panel__head">
              <h2>{listTab === 'channels' ? 'Channels' : 'Direct messages'}</h2>
              <button className="icon-btn" aria-label={listTab === 'channels' ? 'Create channel' : 'New message'} onClick={listTab === 'channels' ? p.onNewChannel : p.onNewMessage}><Plus size={17} /></button>
              <button className="icon-btn brand__close" aria-label="Close navigation" onClick={p.onClose}><X size={18} /></button>
            </div>
            <div className="sidebar__scroll">
              {listTab === 'channels' ? (
                <>
                  {dept.length > 0 && <div className="nav-section"><span>Departments</span></div>}
                  {dept.map(row)}
                  <div className="nav-section"><span>Channels</span></div>
                  {channels.map(row)}
                  <button className="nav-row" onClick={p.onBrowse}><span className="nav-row__icon"><Search size={17} /></span><span className="nav-row__label">Browse channels</span></button>
                </>
              ) : (
                <>
                  {dms.map(row)}
                  <button className="nav-row" onClick={p.onNewMessage}><span className="nav-row__icon"><Plus size={17} /></span><span className="nav-row__label">New message</span></button>
                </>
              )}
            </div>
            <div className="panel__foot">
              <Avatar user={p.me} size={34} />
              <div><strong>{p.me.name}</strong><small>{p.me.title}</small></div>
            </div>
          </div>
        )}
      </aside>
    </>
  )
}
