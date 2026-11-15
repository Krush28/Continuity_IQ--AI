import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { speak, stopSpeaking, useRecognizer } from './speech'
import { Badge, Modal, Spinner, Status } from './ui'

const isCmd = (t, words) => new RegExp(`^(${words})[.! ]*$`, 'i').test(t.trim())

/**
 * Voice exit interview: reads each open Gap Auditor question aloud to the outgoing member,
 * listens to the spoken answer and saves it. Say "skip", "repeat", "not relevant" or "stop".
 */
export default function ExitInterview({ projectId, lang, onClose }) {
  const [qs, setQs] = useState(null)
  const [i, setI] = useState(0)
  const [log, setLog] = useState([])
  const [typed, setTyped] = useState('')
  const [phase, setPhase] = useState('idle') // idle | asking | listening | saving | done
  const { listening, interim, error, listen, stop } = useRecognizer(lang)
  const alive = useRef(true)

  useEffect(() => {
    api(`/projects/${projectId}/questions`).then((all) => setQs(all.filter((q) => q.status === 'open')))
    return () => { alive.current = false; stopSpeaking() }
  }, [projectId])

  const q = qs?.[i]

  const next = useCallback((entry) => {
    if (entry) setLog((l) => [entry, ...l])
    setTyped('')
    setI((x) => x + 1)
  }, [])

  const handle = useCallback(async (text) => {
    if (!q || !alive.current) return
    if (isCmd(text, 'stop|end|end interview|finish|that\'s all|band karo')) { setPhase('done'); speak('Interview stopped. Thank you.', lang); return }
    if (isCmd(text, 'repeat|say again|again|phir se')) { ask(q); return }
    if (isCmd(text, 'skip|next|pass|later|aage')) { next({ q, status: 'skipped' }); return }
    const dismiss = isCmd(text, 'not relevant|irrelevant|dismiss|not applicable')
    setPhase('saving')
    try {
      await api(`/projects/${projectId}/questions/${q.id}`, { method: 'POST', body: { answer: dismiss ? '' : text, status: dismiss ? 'dismissed' : 'answered' } })
      next({ q, answer: text, status: dismiss ? 'dismissed' : 'answered' })
      window.dispatchEvent(new Event('ciq:refresh'))
    } catch (e) { setPhase('idle'); alert(e.message) }
  }, [q, projectId, lang, next])

  const ask = useCallback((question) => {
    setPhase('asking')
    speak(question.question, lang, () => {
      if (!alive.current) return
      setPhase('listening')
      listen((t) => handle(t))
    })
  }, [lang, listen, handle])

  // Ask each new question automatically once the interview has started.
  useEffect(() => {
    if (!qs || phase === 'idle' || phase === 'done') return
    if (i >= qs.length) { setPhase('done'); speak('All questions are covered. Thank you, this handover is much safer now.', lang); return }
    ask(qs[i])
  }, [i]) // eslint-disable-line react-hooks/exhaustive-deps

  const begin = () => { if (q) ask(q) }
  const answered = log.filter((x) => x.status === 'answered').length

  return (
    <Modal title="🎙 Voice exit interview" onClose={() => { stop(); stopSpeaking(); onClose() }} wide>
      {!qs ? <Spinner /> : qs.length === 0 ? <p>No open questions. Run the Gap Auditor first.</p> : (
        <div className="interview">
          <div className="row between mb">
            <span className="muted">Question {Math.min(i + 1, qs.length)} of {qs.length} · {answered} answered</span>
            <div className="meter w200"><div className="g" style={{ width: `${(100 * i) / qs.length}%` }} /></div>
          </div>
          {phase === 'done' || !q ? (
            <div className="iv-done">✅ Interview finished. {answered} answer(s) saved to the handover.</div>
          ) : (
            <>
              <div className="iv-q">
                <div className="row gap"><Status s={q.severity} />{q.record_id && <Badge kind="violet">about R{q.record_id}</Badge>}</div>
                <p>{q.question}</p>
              </div>
              <div className={`iv-mic ${listening ? 'on' : ''}`}>
                {phase === 'idle' && <button className="primary lg" onClick={begin}>▶ Start interview (questions are read aloud)</button>}
                {phase === 'asking' && <span className="muted">🔊 Reading the question…</span>}
                {listening && <span>🎙 Listening… <i className="muted">{interim || 'answer now, or say “skip”, “repeat”, “stop”'}</i></span>}
                {phase === 'saving' && <Spinner label="Saving answer" />}
                {phase === 'listening' && !listening && <button className="ghost" onClick={() => listen((t) => handle(t))}>🎙 Answer again</button>}
              </div>
              {error && <div className="alert warn">{error}</div>}
              <form className="row gap" onSubmit={(e) => { e.preventDefault(); if (typed.trim()) { stop(); stopSpeaking(); handle(typed.trim()) } }}>
                <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="…or type the answer" />
                <button className="ghost">Save</button>
                <button type="button" className="ghost" onClick={() => { stop(); stopSpeaking(); next({ q, status: 'skipped' }) }}>Skip</button>
              </form>
            </>
          )}
          {log.length > 0 && (
            <ul className="iv-log">
              {log.map((x, k) => (
                <li key={k}><Status s={x.status === 'skipped' ? 'pending' : x.status} /> <b>{x.q.question}</b>{x.answer && <div className="muted">“{x.answer}”</div>}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Modal>
  )
}
