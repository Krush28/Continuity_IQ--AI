import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { useAuth } from '../auth'

const ROLES = [
  { v: 'manager', t: 'Project manager', d: 'Create projects, review and approve handovers' },
  { v: 'member', t: 'Team member', d: 'Upload documents, answer handover questions' },
  { v: 'incoming', t: 'Incoming member', d: 'Read the approved handover and ask questions' },
]

export default function Login() {
  const { signIn } = useAuth()
  const nav = useNavigate()
  const [mode, setMode] = useState('login')
  const [f, setF] = useState({ name: '', email: '', password: '', role: 'manager' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      await signIn(mode === 'login' ? '/auth/login' : '/auth/register',
        mode === 'login' ? { email: f.email, password: f.password } : f)
      nav('/')
    } catch (e2) { setErr(e2.message) } finally { setBusy(false) }
  }

  return (
    <div className="auth">
      <section className="auth-hero">
        <div className="brand big"><Logo size={44} /><div><b>ContinuityIQ</b><small>Project knowledge & handover</small></div></div>
        <h1>When someone leaves,<br /><span className="grad">their knowledge stays.</span></h1>
        <p>Upload the scattered notes, task lists, bug lists and decisions. AI agents organise them, find what's missing,
          and write a source-linked handover your manager approves.</p>
        <ul className="hero-points">
          <li><b>Extraction Agent</b> turns PDFs & DOCX into tasks, decisions, issues, dependencies and contacts — every item linked to its source.</li>
          <li><b>Gap Auditor</b> catches contradictions, missing owners and undocumented access <i>before</i> the person leaves.</li>
          <li><b>Handover Writer</b> drafts the report, next steps and a first-week plan from approved records only.</li>
          <li><b>Ask ContinuityIQ</b> answers the new member's questions with citations — or says it doesn't know.</li>
        </ul>
        <p className="muted small">Runs fully offline with the rules engine, or with a local LLM via Ollama, or any cloud LLM.</p>
      </section>
      <section className="auth-card">
        <div className="tabs-inline">
          <button className={mode === 'login' ? 'on' : ''} onClick={() => setMode('login')}>Sign in</button>
          <button className={mode === 'register' ? 'on' : ''} onClick={() => setMode('register')}>Create account</button>
        </div>
        <form onSubmit={submit} className="form">
          {mode === 'register' && <label>Full name<input value={f.name} onChange={set('name')} required minLength={2} /></label>}
          <label>Email<input type="email" value={f.email} onChange={set('email')} required autoComplete="username" /></label>
          <label>Password<input type="password" value={f.password} onChange={set('password')} required minLength={6} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></label>
          {mode === 'register' && (
            <div className="role-pick">
              {ROLES.map((r) => (
                <label key={r.v} className={`role ${f.role === r.v ? 'on' : ''}`}>
                  <input type="radio" name="role" value={r.v} checked={f.role === r.v} onChange={set('role')} />
                  <b>{r.t}</b><small>{r.d}</small>
                </label>
              ))}
            </div>
          )}
          {err && <div className="alert">{err}</div>}
          <button className="primary block" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
          {mode === 'login' && <p className="muted small center">Demo: <code>manager@demo.in</code> / <code>demo123</code> (after running the seed script)</p>}
        </form>
      </section>
    </div>
  )
}
