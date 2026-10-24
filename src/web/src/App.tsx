import { useEffect, useState } from 'react'
import type { components } from './api/schema'
import { api, call, setUnauthenticatedHandler } from './chat/api'
import ChatApp from './chat/ChatApp'
import Login from './chat/Login'

type User = components['schemas']['User']

export default function App() {
  // undefined = checking the session, null = signed out.
  const [user, setUser] = useState<User | null | undefined>(undefined)

  useEffect(() => {
    setUnauthenticatedHandler(() => setUser(null))
    call(api.GET('/auth/me')).then(setUser).catch(() => setUser(null))
  }, [])

  async function logout() {
    await call(api.POST('/auth/logout')).catch(() => {})
    setUser(null)
  }

  if (user === undefined) return <div className="shell shell--center"><p className="muted">Loading…</p></div>
  if (user === null) return <Login onLogin={setUser} />
  // Remount on user change so no state from the previous session leaks across sign-ins.
  return <ChatApp key={user.id} meUser={user} onLogout={() => void logout()} />
}
