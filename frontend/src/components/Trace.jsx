import { useEffect, useState } from 'react'
import { api } from '../api'
import { Badge, Modal, Spinner, Status, timeAgo } from './ui'

const KIND = {
  thought: { icon: '💭', label: 'Thought' },
  action: { icon: '🛠', label: 'Tool call' },
  observation: { icon: '👁', label: 'Observation' },
  final: { icon: '✅', label: 'Result' },
  error: { icon: '⚠', label: 'Note' },
}

const AGENT_NAME = { voice: 'Voice Agent', extraction: 'Extraction Agent', gap_auditor: 'Gap Auditor', handover_writer: 'Handover Writer', ask: 'Ask ContinuityIQ' }
export const agentName = (a) => AGENT_NAME[a] || a

function show(v) {
  if (typeof v === 'string') return v
  if (v && v.tool) return `${v.tool}(${Object.entries(v.args || {}).map(([k, x]) => `${k}=${JSON.stringify(x)}`).join(', ')})`
  return JSON.stringify(v, null, 2)
}

export function TraceView({ steps = [] }) {
  return (
    <ol className="trace">
      {steps.map((s) => {
        const k = KIND[s.kind] || { icon: '•', label: s.kind }
        return (
          <li key={s.step} className={`tr tr-${s.kind}`}>
            <div className="tr-dot">{k.icon}</div>
            <div className="tr-body">
              <div className="tr-head"><b>{k.label}</b><span className="muted">{(s.ms / 1000).toFixed(2)}s</span></div>
              <pre>{show(s.content)}</pre>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export function RunModal({ projectId, runId, onClose }) {
  const [run, setRun] = useState(null)
  useEffect(() => { api(`/projects/${projectId}/agents/runs/${runId}`).then(setRun) }, [projectId, runId])
  return (
    <Modal title={run ? `${agentName(run.agent)} · run #${run.id}` : 'Agent run'} onClose={onClose} wide>
      {!run ? <Spinner label="Loading trace" /> : (
        <>
          <div className="row gap wrap mb">
            <Status s={run.status} /><Badge kind="violet">{run.provider}</Badge>
            <span className="muted">{timeAgo(run.started_at)}</span>
            {run.input && <span className="muted ellipsis">Input: {run.input}</span>}
          </div>
          <TraceView steps={run.trace} />
        </>
      )}
    </Modal>
  )
}
