import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Download, FileText, MessageSquare, Pencil, Smile, Trash2 } from 'lucide-react'
import type { Message } from './types'
import { userById } from './data'
import { Avatar } from './ui'

export const QUICK_EMOJI = ['👍', '✨', '🎉', '👀', '✅', '❤️']

export function Markdown({ body, meId }: { body: string; meId: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={url => url}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith('mention:')) {
              const id = href.slice(href.lastIndexOf('/') + 1)
              return <span className={`mention${id === meId ? ' mention--me' : ''}`}>{children}</span>
            }
            if (href && /^(https?:|mailto:)/i.test(href)) return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>
            return <>{children}</>
          },
        }}
      >
        {body}
      </ReactMarkdown>
    </div>
  )
}

export function FileCard({ id, name, size }: { id: string; name: string; size: string }) {
  return (
    <div className="file-card">
      <span className="file-card__icon"><FileText size={18} /></span>
      <div className="file-card__meta">
        <strong>{name}</strong>
        <span>{size}</span>
      </div>
      <a className="icon-btn" aria-label={`Download ${name}`} href={`/files/${id}`} download={name}><Download size={17} /></a>
    </div>
  )
}

interface Props {
  message: Message
  meId: string
  replyCount: number
  inThread?: boolean
  onReact: (id: string, emoji: string) => void
  onReply: (id: string) => void
  onEdit: (id: string, body: string) => void
  onDelete: (id: string) => void
}

export default function MessageItem({ message, meId, replyCount, inThread, onReact, onReply, onEdit, onDelete }: Props) {
  const author = userById(message.authorId)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(message.body)
  const [pickerOpen, setPickerOpen] = useState(false)
  const mine = message.authorId === meId && !message.pending

  return (
    <article className={`msg${message.pending ? ' is-pending' : ''}`} id={`msg-${message.id}`}>
      <Avatar user={author} size={40} />
      <div className="msg__main">
        <div className="msg__meta">
          <span className="msg__author">{author?.name}</span>
          <span className="msg__time">{message.time}</span>
          {message.edited && <span className="msg__time">(edited)</span>}
          {message.failed && <span className="msg__failed">Not sent</span>}
        </div>

        {editing ? (
          <form className="msg__edit" onSubmit={e => { e.preventDefault(); if (draft.trim()) { onEdit(message.id, draft.trim()); setEditing(false) } }}>
            <textarea value={draft} autoFocus aria-label="Edit message" onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Escape') setEditing(false) }} />
            <div className="msg__edit-actions">
              <button type="button" className="btn" onClick={() => setEditing(false)}>Cancel</button>
              <button className="btn btn--primary" disabled={!draft.trim()}>Save</button>
            </div>
          </form>
        ) : (
          <Markdown body={message.body} meId={meId} />
        )}

        {message.files?.map(f => <FileCard key={f.id} id={f.id} name={f.name} size={f.size} />)}

        {(Object.keys(message.reactions).length > 0 || (!inThread && replyCount > 0)) && (
          <div className="msg__reactions">
            {Object.entries(message.reactions).filter(([, ids]) => ids.length).map(([emoji, ids]) => (
              <button key={emoji} className={`pill${ids.includes(meId) ? ' pill--on' : ''}`} aria-pressed={ids.includes(meId)}
                title={ids.map(id => userById(id)?.name).join(', ')} onClick={() => onReact(message.id, emoji)}>
                <span>{emoji}</span> {ids.length}
              </button>
            ))}
            {!inThread && replyCount > 0 && (
              <button className="link-btn" onClick={() => onReply(message.id)}>{replyCount} {replyCount === 1 ? 'reply' : 'replies'}</button>
            )}
          </div>
        )}
      </div>

      <div className="msg__actions" role="toolbar" aria-label="Message actions">
        <div className="msg__picker-wrap">
          <button className="icon-btn" aria-label="Add reaction" title="Add reaction" aria-expanded={pickerOpen} onClick={() => setPickerOpen(o => !o)}><Smile size={16} /></button>
          {pickerOpen && (
            <div className="popover popover--emoji">
              {QUICK_EMOJI.map(e => <button key={e} aria-label={`React ${e}`} onClick={() => { onReact(message.id, e); setPickerOpen(false) }}>{e}</button>)}
            </div>
          )}
        </div>
        {!inThread && <button className="icon-btn" aria-label="Reply in thread" title="Reply in thread" onClick={() => onReply(message.id)}><MessageSquare size={16} /></button>}
        {mine && <button className="icon-btn" aria-label="Edit message" title="Edit" onClick={() => { setDraft(message.body); setEditing(true) }}><Pencil size={16} /></button>}
        {mine && <button className="icon-btn" aria-label="Delete message" title="Delete" onClick={() => onDelete(message.id)}><Trash2 size={16} /></button>}
      </div>
    </article>
  )
}
