import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, Empty, Modal, Spinner, timeAgo, useToast } from '../components/ui'

export default function Projects() {
  const { user } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const [list, setList] = useState(null)
  const [show, setShow] = useState(false)
  const [f, setF] = useState({ name: '', description: '' })

  const load = () => api('/projects').then(setList).catch((e) => toast(e.message, 'err'))
  useEffect(() => { load() }, [])

  const create = async (e) => {
    e.preventDefault()
    try {
      const p = await api('/projects', { method: 'POST', body: f })
      toast('Project created')
      nav(`/projects/${p.id}/documents`)
    } catch (e2) { toast(e2.message, 'err') }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Projects</h1><p className="muted">Every project's knowledge, ready for the next person.</p></div>
        {user.role === 'manager' && <button className="primary" onClick={() => setShow(true)}>+ New project</button>}
      </div>
      {!list ? <Spinner label="Loading projects" /> : list.length === 0 ? (
        <Empty icon="▦" title="No projects yet">
          {user.role === 'manager' ? <button className="primary" onClick={() => setShow(true)}>Create your first project</button>
            : 'Ask your manager to add you to a project.'}
        </Empty>
      ) : (
        <div className="grid cards">
          {list.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="card proj">
              <div className="row between"><h3>{p.name}</h3><Badge kind={p.my_role === 'manager' ? 'violet' : p.my_role === 'incoming' ? 'blue' : 'gray'}>{p.my_role}</Badge></div>
              <p className="muted clamp2">{p.description || 'No description'}</p>
              <div className="meter"><div style={{ width: `${p.readiness}%` }} className={p.readiness >= 80 ? 'g' : p.readiness >= 50 ? 'a' : 'r'} /></div>
              <div className="row between small muted">
                <span>Handover readiness <b>{p.readiness}%</b></span>
                <span>{p.documents} docs · {p.records} records · {p.open_questions} open Qs</span>
              </div>
              <div className="small muted">Created {timeAgo(p.created_at)}</div>
            </Link>
          ))}
        </div>
      )}
      {show && (
        <Modal title="New project" onClose={() => setShow(false)}>
          <form className="form" onSubmit={create}>
            <label>Project name<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required minLength={2} autoFocus /></label>
            <label>Description<textarea rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="What is the project, who is it for?" /></label>
            <button className="primary">Create project</button>
          </form>
        </Modal>
      )}
    </div>
  )
}
