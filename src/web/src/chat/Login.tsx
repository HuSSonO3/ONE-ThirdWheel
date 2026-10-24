import { useState } from 'react'
import { MessageCircle } from 'lucide-react'
import { api, call } from './api'
import type { components } from '../api/schema'
import './chat.css'

export default function Login({ onLogin }: { onLogin: (u: components['schemas']['User']) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setError('')
    try { onLogin(await call(api.POST('/auth/login', { body: { email: email.trim(), password } }))) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not sign in.') }
    finally { setBusy(false) }
  }

  return (
    <div className="shell shell--center">
      <form className="login" onSubmit={submit}>
        <span className="brand__mark"><MessageCircle size={22} /></span>
        <h1>Sign in to TeamSync</h1>
        <p className="muted">Use your company email and password.</p>
        <label>Email<input type="email" autoComplete="username" autoFocus required value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
        {error && <p className="login__error" role="alert">{error}</p>}
        <button className="btn btn--primary" disabled={busy || !email || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}
