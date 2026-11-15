import { useEffect, useState } from 'react'
import { api } from '../../api'
import { RunModal } from '../../components/Trace'
import { Badge, Empty, Spinner, Status, useToast } from '../../components/ui'

const KIND_LABEL = { contradiction: 'Contradiction', missing_owner: 'No owner', missing_rationale: 'No reason', missing_severity: 'No severity',
  critical_issue: 'Critical issue', access: 'Access / credentials', missing_contacts: 'No contacts', missing_dependencies: 'No dependencies',
  missing_progress: 'Unclear progress', agent: 'AI agent' }

function Question({ q, projectId, onDone, openSource }) {
  const [ans, setAns] = useState(q.answer || '')
  const [busy, setBusy] = useState(false)
  const send = async (status) => {
    setBusy(true)
    try { await api(`/projects/${projectId}/questions/${q.id}`, { method: 'POST', body: { answer: ans, status } }); onDone() }
    catch (e) { alert(e.message) } finally { setBusy(false) }
  }
  return (
    <div className={`q sev-${q.severity} ${q.status !== 'open' ? 'closed' : ''}`}>
      <div className="row gap wrap">
        <Status s={q.severity} /><Badge kind={q.kind === 'agent' ? 'violet' : 'gray'}>{KIND_LABEL[q.kind] || q.kind}</Badge>
        {q.record_id && <button className="cite" onClick={() => openSource(q.record_id)}>R{q.record_id}</button>}
        {q.status !== 'open' && <Status s={q.status} />}
        <span className="muted small">Q{q.id}</span>
      </div>
      <div className="q-text">{q.question}</div>
      {q.status === 'open' ? (
        <div className="q-answer">
          <textarea rows={2} placeholder="Answer from the outgoing member…" value={ans} onChange={(e) => setAns(e.target.value)} />
          <div className="row gap">
            <button className="primary sm" disabled={busy || !ans.trim()} onClick={() => send('answered')}>Save answer</button>
            <button className="ghost sm" disabled={busy} onClick={() => send('dismissed')}>Not relevant</button>
          </div>
        </div>
      ) : q.answer && <div className="q-done"><b>{q.answered_by}:</b> {q.answer}</div>}
    </div>
  )
}

export default function Gaps({ projectId, reload, openSource }) {
  const toast = useToast()
  const [qs, setQs] = useState(null)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [runId, setRunId] = useState(null)
  const [filter, setFilter] = useState('open')

  const load = () => api(`/projects/${projectId}/questions`).then(setQs)
  useEffect(() => { load() }, [projectId])

  const audit = async () => {
    setBusy(true)
    try {
      const out = await api(`/projects/${projectId}/agents/gap-audit`, { method: 'POST' })
      setRes(out)
      const runs = await api(`/projects/${projectId}/agents/runs`)
      setRunId(runs.find((r) => r.agent === 'gap_auditor')?.id)
      toast(`Gap Auditor raised ${out.rule_questions + out.agent_questions} new question(s)`)
      load(); reload()
    } catch (e) { toast(e.message, 'err') } finally { setBusy(false) }
  }
  const copy = () => {
    const open = qs.filter((q) => q.status === 'open')
    const text = `Handover questions (${open.length}) — please answer before your last day:\n\n` + open.map((q, i) => `${i + 1}. [${q.severity}] ${q.question}`).join('\n')
    navigator.clipboard?.writeText(text).then(() => toast('Questions copied — paste into email or chat'), () => toast('Copy failed', 'err'))
  }
  const shown = (qs || []).filter((q) => filter === 'all' || (filter === 'open' ? q.status === 'open' : q.status !== 'open'))
  const openCount = (qs || []).filter((q) => q.status === 'open').length

  return (
    <div className="stack">
      <div className="card hero-card">
        <div>
          <h3>⚑ Gap Auditor agent</h3>
          <p className="muted">Finds what would be lost if the person left today: contradictions between documents, tasks with no owner,
            decisions with no reason, undocumented access and critical bugs. With GenAI on, an autonomous agent then
            investigates the records and source text and asks its own follow-up questions.</p>
        </div>
        <button className="primary lg" onClick={audit} disabled={busy}>{busy ? <Spinner label="Auditing…" /> : 'Run Gap Auditor'}</button>
      </div>
      {res && (
        <div className="card result">
          <b>Audit result:</b> {res.summary}
          <div className="row gap mt"><Badge>{res.rule_questions} from checks</Badge><Badge kind="violet">{res.agent_questions} from AI agent</Badge>
            <Badge kind="amber">{res.flagged} flagged records</Badge>{runId && <button className="link" onClick={() => setRes({ ...res, showTrace: true })}>View agent trace →</button>}</div>
        </div>
      )}
      {res?.showTrace && runId && <RunModal projectId={projectId} runId={runId} onClose={() => setRes({ ...res, showTrace: false })} />}
      {!qs ? <Spinner /> : qs.length === 0 ? <Empty icon="⚑" title="No questions yet">Run the Gap Auditor after uploading documents.</Empty> : (
        <>
          <div className="toolbar">
            <div className="chips">
              {[['open', `Open (${openCount})`], ['closed', 'Answered'], ['all', 'All']].map(([k, l]) => (
                <button key={k} className={filter === k ? 'chip on' : 'chip'} onClick={() => setFilter(k)}>{l}</button>
              ))}
            </div>
            {openCount > 0 && <button className="ghost" onClick={copy}>⧉ Copy open questions for the outgoing member</button>}
          </div>
          <div className="stack sm">{shown.map((q) => <Question key={q.id} q={q} projectId={projectId} onDone={() => { load(); reload() }} openSource={openSource} />)}</div>
        </>
      )}
    </div>
  )
}
