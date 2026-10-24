import { useRef, useState, type KeyboardEvent } from 'react'
import { AtSign, Bold, ChevronDown, Code, FileCode2, Heading2, Italic, Link2, List, ListOrdered, Paperclip, Quote, Send, Smile, Strikethrough, X } from 'lucide-react'
import type { FileAttachment, User } from './types'

const LANGS = ['typescript', 'python', 'sql', 'json', 'bash', 'markdown']
const EMOJI = ['👍', '🎉', '✨', '👀', '✅', '🙏', '😄', '🚀', '❤️', '🤔', '💡', '🔥']

interface Props {
  value: string
  onChange: (v: string) => void
  onSend: (body: string, files: FileAttachment[]) => void
  members: User[]
  placeholder: string
  compact?: boolean
}

export default function Composer({ value, onChange, onSend, members, placeholder, compact }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [lang, setLang] = useState('typescript')
  const [files, setFiles] = useState<FileAttachment[]>([])
  const [emojiOpen, setEmojiOpen] = useState(false)
  const [mention, setMention] = useState<string | null>(null)

  const canSend = value.trim().length > 0 || files.length > 0

  function edit(fn: (text: string, start: number, end: number) => { text: string; start: number; end: number }) {
    const el = ref.current
    if (!el) return
    const r = fn(value, el.selectionStart, el.selectionEnd)
    onChange(r.text)
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(r.start, r.end) })
  }
  const wrap = (a: string, b = a, ph = 'text') => edit((t, s, e) => {
    const sel = t.slice(s, e) || ph
    return { text: t.slice(0, s) + a + sel + b + t.slice(e), start: s + a.length, end: s + a.length + sel.length }
  })
  const linePrefix = (prefix: string | ((i: number) => string)) => edit((t, s, e) => {
    const from = t.lastIndexOf('\n', s - 1) + 1
    const lines = t.slice(from, e).split('\n').map((l, i) => (typeof prefix === 'function' ? prefix(i) : prefix) + l)
    const block = lines.join('\n')
    return { text: t.slice(0, from) + block + t.slice(e), start: from + block.length, end: from + block.length }
  })
  const insert = (str: string) => edit((t, s, e) => ({ text: t.slice(0, s) + str + t.slice(e), start: s + str.length, end: s + str.length }))

  function send() {
    if (!canSend) return
    onSend(value.trim(), files)
    setFiles([])
    setMention(null)
  }
  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Escape') { setMention(null); setEmojiOpen(false) }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() }
  }
  function onInput(v: string, caret: number) {
    onChange(v)
    const m = /(?:^|\s)@([\w ]{0,20})$/.exec(v.slice(0, caret))
    setMention(m ? m[1].toLowerCase() : null)
  }
  function pickMention(u: User) {
    edit((t, s) => {
      const before = t.slice(0, s).replace(/@[\w ]{0,20}$/, '')
      const ins = `@${u.name} `
      return { text: before + ins + t.slice(s), start: before.length + ins.length, end: before.length + ins.length }
    })
    setMention(null)
  }
  function addFiles(list: FileList | null) {
    if (!list) return
    const next = [...list].map(f => ({ id: crypto.randomUUID(), name: f.name, size: f.size > 1024 * 1024 ? `${(f.size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(f.size / 1024))} KB` }))
    setFiles(cur => [...cur, ...next])
  }
  const suggestions = mention === null ? [] : members.filter(u => u.name.toLowerCase().includes(mention)).slice(0, 5)

  return (
    <div className="composer-wrap">
      <div className="composer">
        {!compact && (
          <div className="composer__toolbar" role="toolbar" aria-label="Formatting">
            <button className="tb" aria-label="Bold" title="Bold" onClick={() => wrap('**')}><Bold size={16} /></button>
            <button className="tb" aria-label="Italic" title="Italic" onClick={() => wrap('_')}><Italic size={16} /></button>
            <button className="tb" aria-label="Strikethrough" title="Strikethrough" onClick={() => wrap('~~')}><Strikethrough size={16} /></button>
            <span className="tb-sep" />
            <button className="tb" aria-label="Link" title="Link" onClick={() => edit((t, s, e) => {
              const sel = t.slice(s, e) || 'link text'
              const ins = `[${sel}](https://)`
              return { text: t.slice(0, s) + ins + t.slice(e), start: s + sel.length + 3, end: s + ins.length - 1 }
            })}><Link2 size={16} /></button>
            <button className="tb" aria-label="Bulleted list" title="Bulleted list" onClick={() => linePrefix('- ')}><List size={16} /></button>
            <button className="tb" aria-label="Numbered list" title="Numbered list" onClick={() => linePrefix(i => `${i + 1}. `)}><ListOrdered size={16} /></button>
            <button className="tb" aria-label="Quote" title="Quote" onClick={() => linePrefix('> ')}><Quote size={16} /></button>
            <button className="tb" aria-label="Heading" title="Heading" onClick={() => linePrefix('## ')}><Heading2 size={16} /></button>
            <button className="tb" aria-label="Code block" title="Code block" onClick={() => wrap('```' + lang + '\n', '\n```', 'code')}><Code size={16} /></button>
            <label className="lang">
              <span className="sr-only">Code language</span>
              <select value={lang} onChange={e => setLang(e.target.value)}>{LANGS.map(l => <option key={l}>{l}</option>)}</select>
              <ChevronDown size={13} aria-hidden="true" />
            </label>
          </div>
        )}

        {files.length > 0 && (
          <div className="composer__files">
            {files.map(f => (
              <span className="chip" key={f.id}>{f.name} · {f.size}
                <button aria-label={`Remove ${f.name}`} onClick={() => setFiles(cur => cur.filter(x => x.id !== f.id))}><X size={12} /></button>
              </span>
            ))}
          </div>
        )}

        <textarea ref={ref} className="composer__input" value={value} placeholder={placeholder} aria-label="Message"
          rows={compact ? 2 : 3} onKeyDown={onKey} onChange={e => onInput(e.target.value, e.target.selectionStart)} />

        {suggestions.length > 0 && (
          <div className="popover popover--mention" role="listbox" aria-label="Mention someone">
            {suggestions.map(u => (
              <button key={u.id} role="option" aria-selected="false" onClick={() => pickMention(u)}><b>{u.initials}</b>{u.name}<small>{u.title}</small></button>
            ))}
          </div>
        )}

        <div className="composer__foot">
          <div className="composer__tools">
            <input ref={fileRef} type="file" multiple hidden onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
            <button className="tb" aria-label="Attach file" title="Attach file" onClick={() => fileRef.current?.click()}><Paperclip size={18} /></button>
            {!compact && <button className="tb" aria-label="Create snippet" title="Create snippet" onClick={() => wrap('```' + lang + '\n', '\n```', 'snippet')}><FileCode2 size={18} /></button>}
            <div className="composer__emoji-wrap">
              <button className="tb" aria-label="Insert emoji" title="Emoji" aria-expanded={emojiOpen} onClick={() => setEmojiOpen(o => !o)}><Smile size={18} /></button>
              {emojiOpen && (
                <div className="popover popover--emoji popover--up">
                  {EMOJI.map(e => <button key={e} aria-label={`Insert ${e}`} onClick={() => { insert(e); setEmojiOpen(false) }}>{e}</button>)}
                </div>
              )}
            </div>
            <button className="tb" aria-label="Mention someone" title="Mention" onClick={() => { insert('@'); setMention('') }}><AtSign size={18} /></button>
          </div>
          <div className="composer__right">
            <span className="composer__hint">Enter to send · Shift + Enter for a new line</span>
            <button className="btn btn--primary btn--send" disabled={!canSend} onClick={send}>Send <Send size={15} /></button>
          </div>
        </div>
      </div>
    </div>
  )
}
