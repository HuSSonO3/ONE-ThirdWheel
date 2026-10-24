import { useEffect, useRef, useState } from 'react'
import { Bell, Menu, Search } from 'lucide-react'
import type { components } from '../api/schema'
import type { AppNotification, User } from './types'
import { userById } from './data'
import { Avatar } from './ui'

type Hit = components['schemas']['SearchHit']

interface Props {
  me: User
  crumb: string
  notifications: AppNotification[]
  onSearch: (q: string) => Promise<Hit[]>
  onMenu: () => void
  onOpenResult: (conversationId: string, messageId: string) => void
  onOpenNotification: (n: AppNotification) => void
  onMarkAllRead: () => void
  embedded?: boolean
}

export default function TopBar({ me, crumb, notifications, onSearch, onMenu, onOpenResult, onOpenNotification, onMarkAllRead, embedded }: Props) {
  const [q, setQ] = useState('')
  const [focus, setFocus] = useState(false)
  const [bell, setBell] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [results, setResults] = useState<Hit[] | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if (embedded) setSearchOpen(true); else inputRef.current?.focus() } }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [embedded])

  // Debounced server search (full-text, filtered by access on the server).
  useEffect(() => {
    const term = q.trim()
    if (!term) { setResults(null); return }
    let stale = false
    const t = window.setTimeout(() => { onSearch(term).then(r => { if (!stale) setResults(r) }).catch(() => { if (!stale) setResults([]) }) }, 250)
    return () => { stale = true; window.clearTimeout(t) }
  }, [q, onSearch])

  const unread = notifications.filter(n => !n.read).length
  const Wrapper = embedded ? 'div' : 'header'
  const strip = (s: string) => s.replace(/\*\*/g, '').replace(/\[([^\]]*)\]\(mention:[^)]*\)/g, '$1').replace(/\]\(mention:[^)]*\)/g, '')

  return (
    <Wrapper className={embedded ? 'topbar topbar--embedded' : 'topbar'}>
      {!embedded && <>
        <button className="icon-btn topbar__menu" aria-label="Open navigation" onClick={onMenu}><Menu size={20} /></button>
        <nav className="crumbs" aria-label="Breadcrumb"><span>TeamSync</span><span className="crumbs__sep">›</span><strong>{crumb}</strong></nav>
      </>}

      <div className="search-slot">
        {embedded && (
          <button className="icon-btn icon-btn--box icon-btn--lg" aria-label="Search messages" aria-expanded={searchOpen}
            onMouseDown={e => e.preventDefault()} onClick={() => setSearchOpen(o => !o)}><Search size={19} /></button>
        )}
        {(!embedded || searchOpen) && <div className={embedded ? 'search search--drop' : 'search'}>
          <Search size={17} />
          <input ref={inputRef} type="search" placeholder="Search messages" aria-label="Search messages" value={q}
            onChange={e => setQ(e.target.value)} onFocus={() => setFocus(true)}
            onBlur={() => setTimeout(() => { setFocus(false); if (embedded) setSearchOpen(false) }, 150)}
            onKeyDown={e => { if (e.key === 'Escape') { setSearchOpen(false); setQ('') } }} autoFocus={embedded} />
          <kbd>⌘ K</kbd>
          {(focus || embedded) && q.trim() && results && (
            <div className="popover popover--results" role="listbox">
              {results.length === 0 && <div className="popover__empty">No messages match “{q}”.</div>}
              {results.map(h => (
                <button key={h.message.id} role="option" aria-selected="false" onMouseDown={e => e.preventDefault()}
                  onClick={() => { onOpenResult(h.conversation.id, h.message.parent_id ?? h.message.id); setQ(''); setSearchOpen(false) }}>
                  <small>{h.conversation.kind === 'dm' ? 'Direct message' : `# ${h.conversation.name ?? ''}`} · {userById(h.message.author_id)?.name}</small>
                  <span>{strip(h.headline)}</span>
                </button>
              ))}
            </div>
          )}
        </div>}
      </div>

      <div className="bell-wrap">
        <button className="icon-btn bell" aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={bell} onClick={() => setBell(b => !b)}>
          <Bell size={20} />{unread > 0 && <span className="bell__badge">{unread}</span>}
        </button>
        {bell && (
          <div className="popover popover--bell">
            <div className="popover__head"><strong>Notifications</strong><button className="link-btn" onClick={onMarkAllRead}>Mark all read</button></div>
            {notifications.length === 0 && <div className="popover__empty">You’re all caught up.</div>}
            {notifications.map(n => (
              <button key={n.id} className={n.read ? '' : 'is-unread'} onClick={() => { setBell(false); onOpenNotification(n) }}>
                <span>{n.text}</span><small>{n.time}</small>
              </button>
            ))}
          </div>
        )}
      </div>
      <Avatar user={me} size={34} />
    </Wrapper>
  )
}
