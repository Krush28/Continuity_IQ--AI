import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import { RunModal, agentName } from '../../components/Trace'
import { CATEGORY, Ring, Status, timeAgo } from '../../components/ui'

export default function Overview({ project: p, projectId, canEdit }) {
  const [runs, setRuns] = useState([])
  const [run, setRun] = useState(null)
  const [risk, setRisk] = useState(null)
  useEffect(() => {
    api(`/projects/${projectId}/agents/runs`).then(setRuns).catch(() => {})
    api(`/projects/${projectId}/people`).then(setRisk).catch(() => {})
  }, [projectId])

  const t = p.tasks || {}
  const total = (t.completed || 0) + (t.ongoing || 0) + (t.pending || 0)
  const pct = (n) => (total ? (100 * (n || 0)) / total : 0)
  const steps = [
    { done: p.documents > 0, label: 'Upload project files', to: 'documents', hint: 'PDF, DOCX, TXT or MD' },
    { done: p.records > 0 && !(p.review?.unreviewed), label: 'Review extracted records', to: 'review', hint: `${p.review?.unreviewed || 0} waiting` },
    { done: p.agent_runs > 0 && p.open_questions === 0, label: 'Close knowledge gaps', to: 'gaps', hint: `${p.open_questions} open questions` },
    { done: p.handovers > 0, label: 'Generate handover', to: 'handover', hint: 'AI-written, source-linked' },
    { done: p.approved_handover, label: 'Manager approves', to: 'handover', hint: 'Then the new member can read it' },
  ]
  const next = steps.find((s) => !s.done)

  return (
    <div className="stack">
      {canEdit && (
        <div className="card flow">
          {steps.map((s, i) => (
            <Link key={i} to={`/projects/${projectId}/${s.to}`} className={`flow-step ${s.done ? 'done' : s === next ? 'next' : ''}`}>
              <span className="flow-n">{s.done ? '✓' : i + 1}</span>
              <span><b>{s.label}</b><small>{s.hint}</small></span>
            </Link>
          ))}
        </div>
      )}
      <div className="grid g3">
        <div className="card center-col">
          <h3 className="card-title">Handover readiness</h3>
          <Ring value={p.readiness_detail.score} size={150} />
          <ul className="checks">
            {p.readiness_detail.checks.map((c) => <li key={c.label} className={c.ok ? 'ok' : ''}><span>{c.ok ? '✓' : '○'}</span>{c.label}<b>{c.value}</b></li>)}
          </ul>
        </div>
        <div className="card">
          <h3 className="card-title">Work status</h3>
          <div className="big-num">{total}<small> tasks</small></div>
          <div className="stackbar">
            <div className="g" style={{ width: `${pct(t.completed)}%` }} title="completed" />
            <div className="b" style={{ width: `${pct(t.ongoing)}%` }} title="ongoing" />
            <div className="a" style={{ width: `${pct(t.pending)}%` }} title="pending" />
          </div>
          <div className="legend">
            <span><i className="g" />Completed <b>{t.completed || 0}</b></span>
            <span><i className="b" />Ongoing <b>{t.ongoing || 0}</b></span>
            <span><i className="a" />Pending <b>{t.pending || 0}</b></span>
          </div>
          <h3 className="card-title mt">Knowledge base</h3>
          <div className="kb">
            {Object.entries(CATEGORY).map(([k, m]) => (
              <div key={k} className={`kb-i cat-${k}`}><span>{m.icon}</span><b>{p.counts[k] || 0}</b><small>{m.label}</small></div>
            ))}
          </div>
        </div>
        <div className="card">
          <h3 className="card-title">Agent activity</h3>
          {runs.length === 0 ? <p className="muted">No agent runs yet. Upload a document to start.</p> : (
            <ul className="runs">
              {runs.slice(0, 7).map((r) => (
                <li key={r.id} onClick={() => setRun(r.id)}>
                  <span className={`agent-ic a-${r.agent}`}>{r.agent === 'voice' ? '🎙' : r.agent === 'ask' ? '✦' : r.agent === 'gap_auditor' ? '⚑' : r.agent === 'extraction' ? '⇪' : '⎙'}</span>
                  <div><b>{agentName(r.agent)}</b><small className="ellipsis">{r.input || r.provider} · {r.steps} steps · {timeAgo(r.started_at)}</small></div>
                  <Status s={r.status} />
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">Click a run to see every thought, tool call and observation.</p>
        </div>
      </div>
      {risk && (risk.people.length > 0 || risk.unowned.length > 0) && (
        <div className="card">
          <div className="row between"><h3 className="card-title">Knowledge risk map · who holds the open work</h3>
            <span className="muted small">{risk.total_open} open tasks</span></div>
          {risk.warnings.map((w, i) => <div key={i} className="alert warn mb">⚠ {w}</div>)}
          <div className="people">
            {risk.people.map((p) => (
              <div key={p.name} className={`person r-${p.risk}`}>
                <div className="row gap"><div className="avatar">{p.name[0]}</div><div><b>{p.name}</b><small className="muted">{p.contact ? 'listed contact · ' : ''}{p.risk} risk</small></div></div>
                <div className="meter"><div className={p.risk === 'high' ? 'r' : p.risk === 'medium' ? 'a' : 'g'} style={{ width: `${Math.max(4, p.share)}%` }} /></div>
                <div className="small muted">{p.open_tasks} open · {p.high_open} high priority · {p.completed} done · {p.other} other</div>
                {p.items.length > 0 && <ul className="tiny">{p.items.map((it) => <li key={it.id}>{it.title} <i>({it.status})</i></li>)}</ul>}
              </div>
            ))}
            {risk.unowned.length > 0 && (
              <div className="person r-high">
                <div className="row gap"><div className="avatar gray">?</div><div><b>Nobody</b><small className="muted">unowned work</small></div></div>
                <div className="meter"><div className="r" style={{ width: `${(100 * risk.unowned.length) / (risk.total_open || 1)}%` }} /></div>
                <div className="small muted">{risk.unowned.length} open tasks with no owner</div>
                <ul className="tiny">{risk.unowned.slice(0, 6).map((it) => <li key={it.id}>{it.title}</li>)}</ul>
              </div>
            )}
          </div>
        </div>
      )}
      {run && <RunModal projectId={projectId} runId={run} onClose={() => setRun(null)} />}
    </div>
  )
}
