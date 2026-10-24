import { useMemo, useState } from 'react'
import { CheckCheck, ListTodo } from 'lucide-react'
import type { Conversation, Task, TaskStatus, User } from './types'
import { STATUS_LABEL, userById } from './data'
import { Avatar } from './ui'

interface TableProps {
  tasks: Task[]
  showSource?: boolean
  onStatus: (id: string, s: TaskStatus) => void
  emptyText: string
}

function TaskTable({ tasks, showSource, onStatus, emptyText }: TableProps) {
  const [project, setProject] = useState('')
  const [assignee, setAssignee] = useState('')
  const projects = useMemo(() => [...new Set(tasks.map(t => t.project).filter(Boolean))] as string[], [tasks])
  const people = useMemo(() => [...new Set(tasks.map(t => t.assigneeId))], [tasks])
  const rows = tasks.filter(t => (!project || t.project === project) && (!assignee || t.assigneeId === assignee))

  return (
    <div className="tasks">
      <div className="tasks__filters">
        <label>Project
          <select value={project} onChange={e => setProject(e.target.value)}><option value="">All projects</option>{projects.map(p => <option key={p}>{p}</option>)}</select>
        </label>
        <label>User
          <select value={assignee} onChange={e => setAssignee(e.target.value)}><option value="">Everyone</option>{people.map(id => <option key={id} value={id}>{userById(id)?.name}</option>)}</select>
        </label>
      </div>
      {rows.length === 0 ? (
        <div className="empty"><ListTodo size={28} /><h3>No tasks here yet</h3><p>{emptyText}</p></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Task</th><th>Assignee</th><th>Project</th>{showSource && <th>Source</th>}<th>Status</th><th>Due</th></tr></thead>
            <tbody>
              {rows.map(t => {
                const a = userById(t.assigneeId)
                return (
                  <tr key={t.id}>
                    <td><strong>{t.title}</strong>{t.createdByAi && <span className="tag">via TeamSync</span>}</td>
                    <td><span className="who"><Avatar user={a} size={24} />{a?.name}</span></td>
                    <td>{t.project ?? '—'}</td>
                    {showSource && <td>{t.sourceConversationName ? `# ${t.sourceConversationName}` : '—'}</td>}
                    <td>
                      <select className={`status status--${t.status}`} aria-label={`Status of ${t.title}`} value={t.status} onChange={e => onStatus(t.id, e.target.value as TaskStatus)}>
                        {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    </td>
                    <td>{t.due ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/** Tasks tab inside a conversation (spec 2.3). */
export function ConversationTasks({ conversation, tasks, onStatus }: { conversation: Conversation; tasks: Task[]; onStatus: (id: string, s: TaskStatus) => void }) {
  return <TaskTable tasks={tasks} showSource={conversation.kind === 'department'} onStatus={onStatus}
    emptyText={conversation.kind === 'department' ? 'Tasks for this department will appear here.' : 'Accept a TeamSync suggestion to create the first task in this conversation.'} />
}

/** Personal dashboard (spec 2.4) with subordinate picker. */
export function MyTasks({ me, tasks, reports, reportTasks, onLoadReport, onStatus }: {
  me: User; tasks: Task[]; reports: User[]; reportTasks: Record<string, Task[]>
  onLoadReport: (userId: string) => void; onStatus: (id: string, s: TaskStatus) => void
}) {
  const [viewing, setViewing] = useState(me.id)
  const who = viewing === me.id || reports.some(r => r.id === viewing) ? viewing : me.id
  const list = who === me.id ? tasks : reportTasks[who] ?? []
  return (
    <section className="page">
      <header className="page__head">
        <span className="page__icon"><CheckCheck size={22} /></span>
        <div><h1>{who === me.id ? 'My tasks' : `${userById(who)?.name}’s tasks`}</h1><p>Everything assigned to {who === me.id ? 'you' : userById(who)?.name?.split(' ')[0]}, from every conversation.</p></div>
        {reports.length > 0 && (
          <label className="page__picker">View dashboard of
            <select value={who} onChange={e => { setViewing(e.target.value); if (e.target.value !== me.id) onLoadReport(e.target.value) }}>
              <option value={me.id}>Me</option>
              {reports.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </label>
        )}
      </header>
      <TaskTable tasks={list} showSource onStatus={onStatus} emptyText="Nothing is assigned to this person right now." />
    </section>
  )
}

/** Placeholder admin page (spec 1.3 / 3.5). */
export function AdminView({ people }: { people: User[] }) {
  const [scopes, setScopes] = useState({ 'conversations:read': true, 'suggestions:create': true, 'suggestions:status': true })
  return (
    <section className="page">
      <header className="page__head"><div><h1>Admin &amp; people</h1><p>Manage people and AI settings.</p></div></header>
      <div className="admin-grid">
        <div className="card">
          <h2>People</h2>
          <table>
            <thead><tr><th>Name</th><th>Title</th><th>Department</th><th>Role</th></tr></thead>
            <tbody>{people.map(u => <tr key={u.id}><td><span className="who"><Avatar user={u} size={24} />{u.name}</span></td><td>{u.title}</td><td>{u.department}</td><td>{u.role}</td></tr>)}</tbody>
          </table>
        </div>
        <div className="card">
          <h2>TeamSync AI scopes</h2>
          {Object.entries(scopes).map(([k, v]) => (
            <label className="check" key={k}><input type="checkbox" checked={v} onChange={() => setScopes(s => ({ ...s, [k]: !v }))} /> <code>{k}</code></label>
          ))}
          <p className="muted">The AI proposes; a person accepts. It never acts as a user.</p>
        </div>
      </div>
    </section>
  )
}
