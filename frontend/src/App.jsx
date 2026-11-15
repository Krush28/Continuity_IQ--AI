import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api'
import { useAuth } from './auth'
import { Spinner } from './components/ui'
import VoiceAgent from './components/VoiceAgent'
import Login from './pages/Login'
import { Logo } from './components/Logo'
import Project from './pages/Project'
import Projects from './pages/Projects'
import Settings from './pages/Settings'

function AIChip() {
  const [ai, setAi] = useState(null)
  const loc = useLocation()
  useEffect(() => { api('/settings/ai').then(setAi).catch(() => {}) }, [loc.pathname])
  if (!ai) return null
  return (
    <Link to="/settings" className={`ai-chip ${ai.available ? 'on' : ''}`} title="GenAI engine — click to configure">
      <span className="dot" />{ai.available ? `GenAI: ${ai.provider} · ${ai.model}` : 'Offline rules mode'}
    </Link>
  )
}

function Shell({ children }) {
  const { user, signOut } = useAuth()
  return (
    <div className="shell">
      <aside className="side">
        <Link to="/" className="brand"><Logo /><div><b>ContinuityIQ</b><small>Knowledge that stays</small></div></Link>
        <nav>
          <NavLink to="/" end>▦ Projects</NavLink>
          <NavLink to="/settings">⚙ AI settings</NavLink>
        </nav>
        <div className="side-foot">
          <div className="me"><div className="avatar">{user.name[0]}</div><div><b>{user.name}</b><small>{user.role}</small></div></div>
          <button className="ghost sm" onClick={signOut}>Sign out</button>
        </div>
      </aside>
      <main className="main">
        <div className="topbar"><AIChip /></div>
        {children}
      </main>
      <VoiceAgent />
    </div>
  )
}

export default function App() {
  const { user, ready } = useAuth()
  if (!ready) return <div className="center-screen"><Spinner label="Loading ContinuityIQ" /></div>
  if (!user) return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Projects />} />
        <Route path="/projects/:id/*" element={<Project />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  )
}
