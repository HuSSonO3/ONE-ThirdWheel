import { useEffect, useMemo, useRef, useState } from 'react'
import { Bell, Menu, Search } from 'lucide-react'
import type { AppNotification, Conversation, Message, User } from './types'
import { conversationTitle, userById } from './data'
import { Avatar } from './ui'

interface Props {
  me: User
  crumb: string
  conversations: Conversation[]
  messages: Message[]
  notifications: AppNotification[]
  onMenu: () => void
  onOpenResult: (conversationId: string, messageId: string) => void
  onOpenNotification: (n: AppNotification) => void
  onMarkAllRead: () => void
}

export default function TopBar({ me, crumb, conversations, messages, notifications, onMenu, onOpenResult, onOpenNotification, onMarkAllRead }: Props) {
  const [q, setQ] = useState('')
  const [focus, setFocus] = useState(false)
  const [bell, setBell] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); inputRef.current?.focus() } }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  const results = useMemo(() => {
    const term = q.trim().toLowerCase()
    if (!term) return []
    const accessible = new Map(conversations.filter(c => c.isPublic || c.memberIds.includes(me.id)).map(c => [c.id, c]))
    return messages
      .filter(m => accessible.has(m.conversationId) && `${userById(m.authorId)?.name} ${m.body}`.toLowerCase().includes(term))
      .slice(0, 8)
      .map(m => ({ m, c: accessible.get(m.conversationId)! }))
  }, [q, messages, conversations, me.id])

  const unread = notifications.filter(n => !n.read).length

  return (
    <header className="topbar">
      <button className="icon-btn topbar__menu" aria-label="Open navigation" onClick={onMenu}><Menu size={20} /></button>
      <nav className="crumbs" aria-label="Breadcrumb"><span>Northstar</span><span className="crumbs__sep">›</span><strong>{crumb}</strong></nav>

      <div className="search">
        <Search size={17} />
        <input ref={inputRef} type="search" placeholder="Search messages" aria-label="Search messages" value={q}
          onChange={e => setQ(e.target.value)} onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)} />
        <kbd>⌘ K</kbd>
        {focus && q.trim() && (
          <div className="popover popover--results" role="listbox">
            {results.length === 0 && <div className="popover__empty">No messages match “{q}”.</div>}
            {results.map(({ m, c }) => (
              <button key={m.id} role="option" aria-selected="false" onMouseDown={e => e.preventDefault()}
                onClick={() => { onOpenResult(c.id, m.parentId ?? m.id); setQ('') }}>
                <small>{c.kind === 'dm' ? conversationTitle(c, me.id) : `# ${c.name}`} · {userById(m.authorId)?.name}</small>
                <span>{m.body.length > 90 ? m.body.slice(0, 90) + '…' : m.body}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="bell-wrap">
        <button className="icon-btn bell" aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={bell} onClick={() => setBell(b => !b)}>
          <Bell size={20} />{unread > 0 && <span className="bell__badge">{unread}</span>}
        </button>
        {bell && (
          <div className="popover popover--bell">
            <div className="popover__head"><strong>Notifications</strong><button className="link-btn" onClick={onMarkAllRead}>Mark all read</button></div>
            {notifications.map(n => (
              <button key={n.id} className={n.read ? '' : 'is-unread'} onClick={() => { setBell(false); onOpenNotification(n) }}>
                <span>{n.text}</span><small>{n.time}</small>
              </button>
            ))}
          </div>
        )}
      </div>
      <Avatar user={me} size={34} />
    </header>
  )
}
