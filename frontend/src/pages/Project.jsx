import { useCallback, useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { api } from '../api'
import SourceModal from '../components/Source'
import { Badge, Spinner, useToast } from '../components/ui'
import Ask from './tabs/Ask'
import Documents from './tabs/Documents'
import Gaps from './tabs/Gaps'
import Handover from './tabs/Handover'
import Overview from './tabs/Overview'
import Quiz from './tabs/Quiz'
import Review from './tabs/Review'
import SearchTab from './tabs/Search'
import Team from './tabs/Team'

export default function Project() {
  const { id } = useParams()
  const toast = useToast()
  const [p, setP] = useState(null)
  const [cite, setCite] = useState(null)

  const [tick, setTick] = useState(0)
  const loc = useLocation()
  const reload = useCallback(() => api(`/projects/${id}`).then(setP).catch((e) => toast(e.message, 'err')), [id, toast])
  useEffect(() => { reload() }, [reload])
  // The Voice Agent changes data from outside the page: reload and remount the open tab.
  useEffect(() => {
    const f = () => { reload(); setTick((t) => t + 1) }
    window.addEventListener('ciq:refresh', f)
    return () => window.removeEventListener('ciq:refresh', f)
  }, [reload])
  if (!p) return <div className="page"><Spinner label="Loading project" /></div>

  const role = p.my_role
  const canEdit = role !== 'incoming'
  const ctx = { project: p, projectId: Number(id), role, canEdit, reload, openSource: setCite }
  const tabs = [
    ['', 'Overview', '◎'],
    ...(canEdit ? [['documents', 'Documents', '⇪'], ['review', 'Review', '✓'], ['gaps', 'Gap Auditor', '⚑']] : []),
    ['ask', 'Ask', '✦'],
    ['handover', 'Handover', '⎙'],
    ['search', 'Search', '⌕'],
    ['quiz', 'Onboarding quiz', '🎓'],
    ...(canEdit ? [['team', 'Team & activity', '☺']] : []),
  ]
  const badges = { review: p.review?.unreviewed || 0, gaps: p.open_questions || 0 }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="crumbs">Projects / </div>
          <h1>{p.name}</h1>
          <p className="muted">{p.description}</p>
        </div>
        <Badge kind={role === 'manager' ? 'violet' : role === 'incoming' ? 'blue' : 'gray'}>You are: {role}</Badge>
      </div>
      <nav className="tabs">
        {tabs.map(([path, label, icon]) => (
          <NavLink key={path} to={`/projects/${id}${path ? '/' + path : ''}`} end={!path}>
            <span className="ti">{icon}</span>{label}
            {badges[path] > 0 && <span className="count">{badges[path]}</span>}
          </NavLink>
        ))}
      </nav>
      <Routes key={`${tick}${loc.search}`}>
        <Route index element={<Overview {...ctx} />} />
        {canEdit && <Route path="documents" element={<Documents {...ctx} />} />}
        {canEdit && <Route path="review" element={<Review {...ctx} />} />}
        {canEdit && <Route path="gaps" element={<Gaps {...ctx} />} />}
        <Route path="ask" element={<Ask {...ctx} />} />
        <Route path="handover" element={<Handover {...ctx} />} />
        <Route path="search" element={<SearchTab {...ctx} />} />
        <Route path="quiz" element={<Quiz {...ctx} />} />
        {canEdit && <Route path="team" element={<Team {...ctx} />} />}
        <Route path="*" element={<Navigate to={`/projects/${id}`} replace />} />
      </Routes>
      {cite && <SourceModal projectId={id} recordId={cite} onClose={() => setCite(null)} />}
    </div>
  )
}
