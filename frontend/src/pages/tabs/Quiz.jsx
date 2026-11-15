import { useEffect, useState } from 'react'
import { api } from '../../api'
import { speak } from '../../components/speech'
import { Empty, Ring, Spinner } from '../../components/ui'

/** Onboarding quiz: proves the incoming member actually absorbed the handover. Built only from records. */
export default function Quiz({ projectId, openSource }) {
  const [qs, setQs] = useState(null)
  const [i, setI] = useState(0)
  const [picked, setPicked] = useState(null)
  const [score, setScore] = useState(0)
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 1e6))

  useEffect(() => {
    setQs(null); setI(0); setPicked(null); setScore(0)
    api(`/projects/${projectId}/quiz?seed=${seed}`).then((r) => setQs(r.questions))
  }, [projectId, seed])

  if (!qs) return <Spinner label="Building your quiz from the project records" />
  if (!qs.length) return <Empty icon="🎓" title="Not enough approved knowledge yet">The quiz is built from approved records. Approve records and generate a handover first.</Empty>

  const done = i >= qs.length
  if (done) {
    const pct = Math.round((100 * score) / qs.length)
    return (
      <div className="card quiz center-col">
        <Ring value={pct} size={150} label="score" />
        <h2>{pct >= 80 ? 'Ready to take over! 🎉' : pct >= 50 ? 'Good start — review the handover once more.' : 'Spend more time with the handover.'}</h2>
        <p className="muted">{score} of {qs.length} correct. Your result is recorded in the activity log for the manager.</p>
        <button className="primary" onClick={() => setSeed(seed + 1)}>Try a new set of questions</button>
      </div>
    )
  }

  const q = qs[i]
  const choose = (k) => {
    if (picked !== null) return
    setPicked(k)
    const ok = k === q.answer
    if (ok) setScore((s) => s + 1)
    if (i === qs.length - 1) api(`/projects/${projectId}/quiz/result`, { method: 'POST', body: { score: score + (ok ? 1 : 0), total: qs.length } }).catch(() => {})
  }

  return (
    <div className="card quiz">
      <div className="row between mb">
        <span className="eyebrow">🎓 Onboarding quiz · question {i + 1} of {qs.length}</span>
        <span className="muted">Score {score}</span>
      </div>
      <div className="meter mb"><div className="g" style={{ width: `${(100 * i) / qs.length}%` }} /></div>
      <h2 className="quiz-q">{q.question} <button className="icon-btn" title="Read aloud" onClick={() => speak(q.question)}>🔊</button></h2>
      <div className="options">
        {q.options.map((o, k) => (
          <button key={k} onClick={() => choose(k)}
            className={`opt ${picked === null ? '' : k === q.answer ? 'right' : k === picked ? 'wrong' : 'dim'}`}>
            <span className="opt-k">{'ABCD'[k]}</span>{o}
          </button>
        ))}
      </div>
      {picked !== null && (
        <div className={`explain ${picked === q.answer ? 'ok' : 'no'}`}>
          <b>{picked === q.answer ? 'Correct!' : 'Not quite.'}</b> {q.explanation}
          <button className="link" onClick={() => openSource(q.record_id)}>See source (R{q.record_id})</button>
          <div className="row mt"><button className="primary" onClick={() => { setI(i + 1); setPicked(null) }}>{i === qs.length - 1 ? 'See result' : 'Next question →'}</button></div>
        </div>
      )}
    </div>
  )
}
