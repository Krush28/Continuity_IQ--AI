import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import { RunModal } from '../../components/Trace'
import { Badge, CatBadge, RichText, Spinner } from '../../components/ui'

const SUGGESTIONS = [
  'What is still pending and who owns it?',
  'Why did we choose PostgreSQL?',
  'Where are the payment API keys?',
  'What known bugs should I fix first?',
  'Who do I contact for warehouse API access?',
]

export default function Ask({ projectId, role, openSource }) {
  const [msgs, setMsgs] = useState([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [run, setRun] = useState(null)
  const end = useRef()
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, busy])

  const send = async (text) => {
    const question = (text ?? q).trim()
    if (!question || busy) return
    setQ('')
    setMsgs((m) => [...m, { who: 'me', text: question }])
    setBusy(true)
    try {
      const res = await api(`/projects/${projectId}/ask`, { method: 'POST', body: { question } })
      setMsgs((m) => [...m, { who: 'ai', ...res }])
    } catch (e) {
      setMsgs((m) => [...m, { who: 'ai', answer: `Error: ${e.message}`, sources: [] }])
    } finally { setBusy(false) }
  }

  return (
    <div className="chat card">
      <div className="chat-head">
        <div><b>✦ Ask ContinuityIQ</b><small className="muted"> — answers only from {role === 'incoming' ? 'approved' : 'project'} records, with sources</small></div>
      </div>
      <div className="chat-body">
        {msgs.length === 0 && (
          <div className="chat-empty">
            <h3>What do you need to know about this project?</h3>
            <p className="muted">The agent searches the records step by step and cites every fact. If something was never uploaded, it says so instead of guessing.</p>
            <div className="chips center">{SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}</div>
          </div>
        )}
        {msgs.map((m, i) => m.who === 'me' ? (
          <div key={i} className="bubble me">{m.text}</div>
        ) : (
          <div key={i} className="bubble ai">
            <RichText text={m.answer} onCite={openSource} />
            {m.sources?.length > 0 && (
              <div className="sources">
                <div className="muted small">Sources</div>
                {m.sources.map((s) => (
                  <button key={s.id} className="source" onClick={() => openSource(s.id)}>
                    <span className="rid">R{s.id}</span><CatBadge c={s.category} /><span className="ellipsis">{s.title}</span>
                    <small className="muted ellipsis">📄 {s.source}</small>
                  </button>
                ))}
              </div>
            )}
            <div className="row gap small muted mt">
              {m.engine && <Badge kind={m.engine.includes('offline') ? 'gray' : 'violet'}>{m.engine}</Badge>}
              {m.run_id && <button className="link" onClick={() => setRun(m.run_id)}>How did the agent find this?</button>}
            </div>
          </div>
        ))}
        {busy && <div className="bubble ai"><Spinner label="Searching records, reading sources…" /></div>}
        <div ref={end} />
      </div>
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send() }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about tasks, decisions, bugs, access, people…" />
        <button className="primary" disabled={busy || !q.trim()}>Ask</button>
      </form>
      {run && <RunModal projectId={projectId} runId={run} onClose={() => setRun(null)} />}
    </div>
  )
}
