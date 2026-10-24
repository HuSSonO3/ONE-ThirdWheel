import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import type { Presence, User } from './types'

export function Avatar({ user, size = 40, presence }: { user?: User; size?: number; presence?: boolean }) {
  const dot: Presence | undefined = presence ? user?.presence : undefined
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.3)) }} aria-hidden="true">
      {user?.initials ?? '?'}
      {dot && <span className={`avatar__dot avatar__dot--${dot}`} />}
    </span>
  )
}

export function Dialog({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return (
    <dialog ref={ref} className={`dialog${wide ? ' dialog--wide' : ''}`} onCancel={onClose} onClick={e => { if (e.target === ref.current) onClose() }} aria-labelledby="dlg-title">
      <div className="dialog__head">
        <h2 id="dlg-title">{title}</h2>
        <button className="icon-btn" aria-label="Close" onClick={onClose}><X size={18} /></button>
      </div>
      {children}
    </dialog>
  )
}
