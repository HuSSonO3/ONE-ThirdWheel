import { Check, MessageCircle, Sparkles } from 'lucide-react'
import type { Conversation, Message, Suggestion, User } from './types'
import { userById } from './data'
import { Avatar } from './ui'

interface Props {
  suggestion: Suggestion
  conversation: Conversation
  source?: Message
  me: User
  onAccept: (s: Suggestion, inviteAssignee?: boolean) => void
  onModify: (s: Suggestion) => void
  onReject: (s: Suggestion) => void
}

export default function SuggestionCard({ suggestion: s, conversation, source, onAccept, onModify, onReject }: Props) {
  const assignee = userById(s.assigneeId)
  const sourceAuthor = source ? userById(source.authorId) : undefined
  const isMember = conversation.isMember
  // Assignment rule (spec 2.7) is decided by the server: `canAccept` already accounts for the direct-manager exception.
  const allowed = s.canAccept
  const decided = s.status !== 'pending'

  return (
    <section className={`suggest${decided ? ` suggest--${s.status}` : ''}`} aria-label="TeamSync task suggestion">
      <header className="suggest__head">
        <span className="suggest__icon"><Sparkles size={16} /></span>
        <div>
          <div className="suggest__brand">TeamSync suggests</div>
          <div className="suggest__sub">Human approval required · {s.confidence}% confidence</div>
        </div>
        <span className={`badge badge--${s.status}`}>
          {s.status === 'pending' ? 'Needs review' : s.status === 'accepted' ? 'Task created' : 'Rejected'}
        </span>
      </header>

      <h3 className="suggest__title">{s.title}</h3>
      <p className="suggest__desc">{s.description}</p>

      {s.kind === 'task' && <div className="suggest__row">
        <Avatar user={assignee} size={26} />
        <strong>{assignee?.name}</strong>
        <span>{s.project}</span>
        <span>{s.due}</span>
      </div>}

      {source && (
        <div className="suggest__source">
          <div className="suggest__source-label"><MessageCircle size={14} /> Source message · {conversation.name}</div>
          <blockquote>
            “{source.body}”
            <cite>— {sourceAuthor?.name} · {source.time}</cite>
          </blockquote>
        </div>
      )}

      {!decided && !allowed && (
        <p className="suggest__warn">{assignee?.name ?? 'The assignee'} isn’t in this channel.</p>
      )}

      {!decided && (
        <div className="suggest__actions">
          {allowed ? (
            <button className="btn btn--primary" disabled={!isMember} onClick={() => onAccept(s)}><Check size={15} /> Accept</button>
          ) : (
            <button className="btn btn--primary" disabled={!isMember} onClick={() => onAccept(s, true)}>Invite and accept</button>
          )}
          <button className="btn" disabled={!isMember} onClick={() => onModify(s)}>{allowed ? 'Modify and accept' : 'Reassign'}</button>
          <button className="btn btn--ghost" disabled={!isMember} onClick={() => onReject(s)}>Reject</button>
        </div>
      )}
    </section>
  )
}
