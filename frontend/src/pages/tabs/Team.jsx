import { useState } from 'react'
import { api } from '../../api'
import { Badge, timeAgo, useToast } from '../../components/ui'

export default function Team({ project: p, projectId, role, reload }) {
  const toast = useToast()
  const [f, setF] = useState({ email: '', project_role: 'incoming' })
  const add = async (e) => {
    e.preventDefault()
    try { await api(`/projects/${projectId}/members`, { method: 'POST', body: f }); toast('Member added'); setF({ ...f, email: '' }); reload() }
    catch (e2) { toast(e2.message, 'err') }
  }
  const remove = async (id) => { await api(`/projects/${projectId}/members/${id}`, { method: 'DELETE' }); reload() }
  return (
    <div className="grid g2 top">
      <div className="card">
        <h3 className="card-title">Team</h3>
        <ul className="members">
          {p.members.map((m) => (
            <li key={m.id}><div className="avatar">{m.name[0]}</div><div><b>{m.name}</b><small className="muted">{m.email}</small></div>
              <Badge kind={m.project_role === 'manager' ? 'violet' : m.project_role === 'incoming' ? 'blue' : 'gray'}>{m.project_role}</Badge>
              {role === 'manager' && m.project_role !== 'manager' && <button className="ghost sm danger" onClick={() => remove(m.id)}>Remove</button>}
            </li>
          ))}
        </ul>
        {role === 'manager' && (
          <form className="form mt" onSubmit={add}>
            <div className="muted small">Add a registered user to this project</div>
            <div className="row gap">
              <input type="email" placeholder="email@company.com" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required />
              <select value={f.project_role} onChange={(e) => setF({ ...f, project_role: e.target.value })}>
                <option value="member">member</option><option value="incoming">incoming</option><option value="manager">manager</option>
              </select>
              <button className="primary">Add</button>
            </div>
          </form>
        )}
      </div>
      <div className="card">
        <h3 className="card-title">Activity log</h3>
        <ul className="activity">
          {p.activity.map((a, i) => <li key={i}><b>{a.user}</b> {a.action}<small className="muted"> · {timeAgo(a.at)}</small></li>)}
        </ul>
      </div>
    </div>
  )
}
