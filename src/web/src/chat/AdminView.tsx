import { Fragment, useCallback, useEffect, useState } from 'react'
import type { components } from '../api/schema'
import { api, call } from './api'
import { toConversation } from './adapt'
import type { Conversation, User } from './types'
import { Avatar } from './ui'

type S = components['schemas']
type Tab = 'people' | 'ai'

const SCOPE_INFO: Record<S['Scope'], { label: string; hint: string; stub?: boolean }> = {
  'conversations:read': { label: 'Read conversations', hint: 'Lets TeamSync read messages where it is switched on.' },
  'suggestions:create': { label: 'Suggest tasks', hint: 'Lets TeamSync propose new tasks for a person to accept.' },
  'suggestions:status': { label: 'Suggest status changes', hint: 'Lets TeamSync propose marking a task done or in progress.' },
  'leave:request': { label: 'Request leave', hint: 'Not connected yet. Calls are recorded, not executed.', stub: true },
  'claims:submit': { label: 'Submit claims', hint: 'Not connected yet. Calls are recorded, not executed.', stub: true },
  'calendar:create': { label: 'Schedule meetings', hint: 'Not connected yet. Calls are recorded, not executed.', stub: true },
}

const when = (iso: string | null) => (iso ? new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit' }).format(new Date(iso)) : '—')

export default function AdminView({ people }: { people: User[] }) {
  const [tab, setTab] = useState<Tab>('people')
  return (
    <section className="page">
      <header className="page__head"><div><h1>Admin &amp; people</h1><p>Manage people and how TeamSync is allowed to act.</p></div></header>
      <div className="tabs tabs--page" role="tablist">
        <button role="tab" aria-selected={tab === 'people'} className={tab === 'people' ? 'is-on' : ''} onClick={() => setTab('people')}>People</button>
        <button role="tab" aria-selected={tab === 'ai'} className={tab === 'ai' ? 'is-on' : ''} onClick={() => setTab('ai')}>TeamSync AI</button>
      </div>
      {tab === 'people' ? <People people={people} /> : <AiAdmin />}
    </section>
  )
}

function People({ people }: { people: User[] }) {
  return (
    <div className="card">
      <h2>People</h2>
      <table>
        <thead><tr><th>Name</th><th>Title</th><th>Department</th><th>Role</th></tr></thead>
        <tbody>{people.map(u => <tr key={u.id}><td><span className="who"><Avatar user={u} size={24} />{u.name}</span></td><td>{u.title}</td><td>{u.department}</td><td>{u.role}</td></tr>)}</tbody>
      </table>
    </div>
  )
}

function AiAdmin() {
  const [config, setConfig] = useState<S['AiConfig'] | null>(null)
  const [convs, setConvs] = useState<Conversation[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([call(api.GET('/admin/ai')), call(api.GET('/admin/conversations'))])
      .then(([c, list]) => { setConfig(c); setConvs(list.map(toConversation)) })
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load AI settings.'))
  }, [])

  async function update(body: S['AiConfigUpdate']) {
    setError('')
    try { setConfig(await call(api.PATCH('/admin/ai', { body }))) } catch (e) { setError(e instanceof Error ? e.message : 'Could not save.') }
  }
  async function setSwitch(c: Conversation, on: boolean) {
    setConvs(cs => cs.map(x => (x.id === c.id ? { ...x, aiEnabled: on } : x)))
    try { await call(api.PATCH('/admin/conversations/{conversation_id}/ai', { params: { path: { conversation_id: c.id } }, body: { ai_enabled: on } })) }
    catch (e) { setConvs(cs => cs.map(x => (x.id === c.id ? { ...x, aiEnabled: !on } : x))); setError(e instanceof Error ? e.message : 'Could not save.') }
  }

  if (!config) return <div className="card"><p className="muted">{error || 'Loading…'}</p></div>
  const toggleScope = (s: S['Scope']) => update({ scopes: config.scopes.includes(s) ? config.scopes.filter(x => x !== s) : [...config.scopes, s] })

  return (
    <div className="admin-stack">
      {error && <p className="login__error" role="alert">{error}</p>}
      <div className="admin-grid">
        <div className="card">
          <div className="card__row">
            <h2>TeamSync permissions</h2>
            <label className="switch"><input type="checkbox" checked={config.active} onChange={e => void update({ active: e.target.checked })} /><span>{config.active ? 'Active' : 'Paused everywhere'}</span></label>
          </div>
          <p className="muted">TeamSync only proposes. A person always accepts, so it can never act as a user.</p>
          <ul className="scope-list">
            {config.available_scopes.map(s => (
              <li key={s}>
                <label className="check">
                  <input type="checkbox" checked={config.scopes.includes(s)} onChange={() => void toggleScope(s)} />
                  <span><span className="scope-name"><strong>{SCOPE_INFO[s]?.label ?? s}</strong>{SCOPE_INFO[s]?.stub && <em className="tag">not connected</em>}</span><small>{SCOPE_INFO[s]?.hint}</small></span>
                </label>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <h2>Where TeamSync is on</h2>
          <p className="muted">Switch it off for a channel or department to stop it reading there. DMs need both people to allow it.</p>
          <ul className="switch-list">
            {convs.map(c => (
              <li key={c.id}>
                <span>{c.kind === 'department' ? c.name : `# ${c.name}`}<small>{c.kind}</small></span>
                <label className="switch"><input type="checkbox" aria-label={`TeamSync in ${c.name}`} checked={c.aiEnabled} onChange={e => void setSwitch(c, e.target.checked)} /></label>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <AuditLog />
    </div>
  )
}

/** Runs and tool calls (spec 3.4): every call is recorded, including denied and stubbed ones. */
function AuditLog() {
  const [runs, setRuns] = useState<S['AiRun'][] | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [calls, setCalls] = useState<Record<string, S['AiToolCall'][]>>({})
  const [more, setMore] = useState(false)

  const load = useCallback(async (before?: string) => {
    const page = await call(api.GET('/admin/ai/runs', { params: { query: { limit: 25, ...(before ? { before } : {}) } } }))
    setRuns(r => [...(before ? r ?? [] : []), ...page])
    setMore(page.length === 25)
  }, [])
  useEffect(() => { void load().catch(() => setRuns([])) }, [load])

  async function toggle(id: string) {
    setOpen(o => (o === id ? null : id))
    if (!calls[id]) {
      const list = await call(api.GET('/admin/ai/tool-calls', { params: { query: { run_id: id, limit: 50 } } })).catch(() => [])
      setCalls(c => ({ ...c, [id]: list }))
    }
  }

  return (
    <div className="card">
      <div className="card__row"><h2>Audit log</h2><button className="btn btn--small" onClick={() => void load()}>Refresh</button></div>
      {runs === null ? <p className="muted">Loading…</p> : runs.length === 0 ? <p className="muted">TeamSync has not run yet. Runs and every tool call appear here.</p> : (
        <div className="table-scroll">
          <table>
            <thead><tr><th>Started</th><th>Conversation</th><th>Status</th><th>Tool calls</th><th /></tr></thead>
            <tbody>
              {runs.map(r => (
                <Fragment key={r.id}>
                  <tr>
                    <td>{when(r.started_at)}</td>
                    <td>{r.conversation.kind === 'dm' ? 'Direct message' : `# ${r.conversation.name ?? ''}`}</td>
                    <td><span className={`pill pill--run-${r.status}`}>{r.status}</span>{r.error && <small className="muted"> {r.error}</small>}</td>
                    <td>{r.tool_call_count}</td>
                    <td><button className="link-btn" aria-expanded={open === r.id} onClick={() => void toggle(r.id)}>{open === r.id ? 'Hide' : 'Details'}</button></td>
                  </tr>
                  {open === r.id && (
                    <tr className="detail-row"><td colSpan={5}>
                      {!calls[r.id] ? <span className="muted">Loading…</span> : calls[r.id].length === 0 ? <span className="muted">No tool calls in this run.</span> : (
                        <ul className="call-list">
                          {calls[r.id].map(c => (
                            <li key={c.id}>
                              <div><code>{c.tool_name}</code><span className={`pill pill--call-${c.status}`}>{c.status}</span>{!c.scope_check && <em className="tag">scope denied</em>}</div>
                              <pre>{JSON.stringify(c.arguments, null, 2)}</pre>
                            </li>
                          ))}
                        </ul>
                      )}
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {more && runs && <button className="btn btn--small load-more" onClick={() => void load(runs[runs.length - 1].started_at)}>Load older runs</button>}
    </div>
  )
}
