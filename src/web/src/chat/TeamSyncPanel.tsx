import { useState } from 'react'
import { Check, ChevronRight, Clock, FileText, FolderOpen, Image, Link2, ShieldCheck, Info, Sparkles, Users, X } from 'lucide-react'
import type { Conversation, Message, Suggestion, Task, User } from './types'
import { STATUS_LABEL, conversationTitle } from './data'
import SuggestionCard from './SuggestionCard'
import { Avatar } from './ui'

interface Props {
  conversation: Conversation
  me: User
  members: User[]
  messages: Message[]
  tasks: Task[]
  suggestions: Suggestion[]
  on: boolean
  onClose: () => void
  onViewTasks: () => void
  onAccept: (s: Suggestion, invite?: boolean) => void
  onModify: (s: Suggestion) => void
  onReject: (s: Suggestion) => void
}

type Shared = 'directory' | 'media' | 'links' | 'docs'
const SHARED_TABS: { id: Shared; label: string; icon: typeof Users }[] = [
  { id: 'directory', label: 'Directory', icon: Users },
  { id: 'media', label: 'Media', icon: Image },
  { id: 'links', label: 'Links', icon: Link2 },
  { id: 'docs', label: 'Docs', icon: FileText },
]
const IMAGE = /\.(png|jpe?g|gif|webp|svg)$/i
const URL_RE = /https?:\/\/[^\s)]+/g

export default function TeamSyncPanel(p: Props) {
  const [shared, setShared] = useState<Shared>('directory')
  const [reviewing, setReviewing] = useState<string | null>(null)
  const [showTasks, setShowTasks] = useState(false)

  const pending = p.suggestions.filter(s => s.status === 'pending')
  const done = p.tasks.filter(t => t.status === 'done').length
  const pct = p.tasks.length ? Math.round((done / p.tasks.length) * 100) : 0
  const title = conversationTitle(p.conversation, p.me.id)
  const project = p.tasks.find(t => t.project)?.project ?? title

  const files = p.messages.flatMap(m => m.files ?? [])
  const links = [...new Set(p.messages.flatMap(m => m.body.match(URL_RE) ?? []))]
  const roleLabel = (u: User) => (u.id === p.me.id ? 'You' : u.title)

  return (
    <aside className="tspanel" aria-label="TeamSync">
      <header className="tspanel__head">
        <span className="tspanel__icon"><Sparkles size={18} /></span>
        <div><h2>TeamSync</h2><p>{title} · {p.members.length} members</p></div>
        <span className="tspanel__info" tabIndex={0} role="img" aria-label="TeamSync may surface task suggestions from new messages. Nothing is shared without approval. Progress is completed tasks divided by approved tasks, not a measure of team capacity." title="TeamSync may surface task suggestions from new messages. Nothing is shared without approval.&#10;Progress is completed tasks ÷ approved tasks, not a measure of team capacity."><Info size={17} /></span>
        <button className="icon-btn" aria-label="Close TeamSync panel" onClick={p.onClose}><X size={18} /></button>
      </header>

      <div className="tspanel__body">
        {!p.on && <p className="tspanel__paused"><ShieldCheck size={15} /> TeamSync is off here. Nothing is read or suggested until it is turned on.</p>}

        {p.on && pending.length > 0 && (
          <section className="tscard tscard--review">
            <div className="tscard__row"><span className="eyebrow"><Clock size={14} /> Needs your review</span><span className="pill pill--amber">{pending.length}</span></div>
            {pending.map(s => (
              <div key={s.id}>
                <div className="review-row">
                  <div><strong>{s.title}</strong><small>Suggested by TeamSync</small></div>
                  <button className="btn btn--small" aria-expanded={reviewing === s.id} onClick={() => setReviewing(r => (r === s.id ? null : s.id))}>
                    {reviewing === s.id ? 'Hide' : 'Review'} <ChevronRight size={13} />
                  </button>
                </div>
                {reviewing === s.id && (
                  <SuggestionCard suggestion={s} conversation={p.conversation} me={p.me} source={p.messages.find(m => m.id === s.sourceMessageId)}
                    onAccept={p.onAccept} onModify={p.onModify} onReject={p.onReject} />
                )}
              </div>
            ))}
          </section>
        )}
        {p.on && pending.length === 0 && <p className="caught-up"><Check size={15} /> All caught up. Nothing needs your review.</p>}

        <section className="progress-block">
          <div className="progress__label">
            <span><strong>{project}</strong></span>
            <span>{done} of {p.tasks.length} complete</span>
          </div>
          <div className="progress" role="progressbar" aria-label="Project progress" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${pct}%` }} /></div>
          {p.tasks.length > 0 && (
            <button className="link-btn" aria-expanded={showTasks} onClick={() => setShowTasks(v => !v)}>
              {showTasks ? 'Hide tasks' : `View ${p.tasks.length} ${p.tasks.length === 1 ? 'task' : 'tasks'}`}
            </button>
          )}
          {showTasks && (
            <ul className="task-mini">
              {p.tasks.map(t => (
                <li key={t.id}><span>{t.title}</span><span className={`pill pill--${t.status}`}>{STATUS_LABEL[t.status]}</span></li>
              ))}
              <li><button className="link-btn" onClick={p.onViewTasks}>Open Tasks tab</button></li>
            </ul>
          )}
        </section>

        <div className="shared__title"><FolderOpen size={16} /> Shared in this chat</div>
        <div className="shared__tabs" role="tablist">
          {SHARED_TABS.map(t => (
            <button key={t.id} role="tab" aria-selected={shared === t.id} className={shared === t.id ? 'is-on' : ''} onClick={() => setShared(t.id)}>
              <t.icon size={18} />{t.label}
            </button>
          ))}
        </div>

        <ul className="shared__list">
          {shared === 'directory' && p.members.map(u => (
            <li key={u.id}><Avatar user={u} size={34} presence /><div><strong>{u.name}</strong><small>{roleLabel(u)}</small></div><ChevronRight size={15} /></li>
          ))}
          {shared === 'media' && files.filter(f => IMAGE.test(f.name)).map(f => <li key={f.id}><Image size={18} /><div><strong>{f.name}</strong><small>{f.size}</small></div></li>)}
          {shared === 'docs' && files.filter(f => !IMAGE.test(f.name)).map(f => <li key={f.id}><FileText size={18} /><div><strong>{f.name}</strong><small>{f.size}</small></div></li>)}
          {shared === 'links' && links.map(l => <li key={l}><Link2 size={18} /><div><strong>{l}</strong></div></li>)}
        </ul>
        {((shared === 'media' && !files.some(f => IMAGE.test(f.name))) || (shared === 'docs' && !files.some(f => !IMAGE.test(f.name))) || (shared === 'links' && !links.length)) && (
          <p className="muted shared__empty">Nothing shared here yet.</p>
        )}
      </div>
    </aside>
  )
}
