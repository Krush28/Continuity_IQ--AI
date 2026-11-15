import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, download } from '../api'
import ExitInterview from './ExitInterview'
import { speak, stopSpeaking, ttsSupported, useRecognizer } from './speech'
import { Badge, RichText } from './ui'

const LANGS = [['en-IN', 'English'], ['hi-IN', 'हिन्दी']]
const SUGGEST_PROJECT = ['Give me the status', 'Run the gap audit', 'Start the exit interview', 'Approve the safe records',
  'Generate the handover from Arjun Mehta to Karan Shah', 'Approve the handover', 'Download the PDF', "What's pending?",
  'Add a pending high priority task write API docs owned by Karan Shah', 'Where are the payment API keys?']
const SUGGEST_HOME = ['List my projects', 'Open project ShopEase', 'Create project Mobile App Revamp', 'Help']
const isStop = (t) => /^(stop listening|goodbye|bye|that's all|band karo|stop)[.! ]*$/i.test(t.trim())

export default function VoiceAgent() {
  const nav = useNavigate()
  const loc = useLocation()
  const projectId = Number(loc.pathname.match(/^\/projects\/(\d+)/)?.[1]) || null
  const [open, setOpen] = useState(false)
  const [lang, setLang] = useState('en-IN')
  const [talk, setTalk] = useState(true)
  const [handsFree, setHandsFree] = useState(false)
  const [busy, setBusy] = useState(false)
  const [text, setText] = useState('')
  const [log, setLog] = useState([])
  const [interview, setInterview] = useState(null)
  const { listening, interim, error, listen, stop } = useRecognizer(lang)
  const end = useRef()
  const handsFreeRef = useRef(handsFree)
  handsFreeRef.current = handsFree
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [log, busy, interim])

  const run = useCallback(async (utterance) => {
    if (!utterance.trim()) return
    if (isStop(utterance)) { setHandsFree(false); stopSpeaking(); setLog((l) => [...l, { who: 'me', text: utterance }, { who: 'ai', text: 'Okay, I stopped listening.' }]); return }
    setLog((l) => [...l, { who: 'me', text: utterance }])
    setBusy(true)
    try {
      const res = await api('/voice/command', { method: 'POST', body: { text: utterance, project_id: projectId, lang } })
      setLog((l) => [...l, { who: 'ai', text: res.display, answer: res.answer, engine: res.engine }])
      for (const a of res.actions || []) {
        if (a.type === 'navigate') nav(a.to)
        if (a.type === 'download') download(a.path, a.filename).catch(() => {})
        if (a.type === 'interview') setInterview(res.project_id || projectId)
      }
      if (res.refresh) window.dispatchEvent(new Event('ciq:refresh'))
      const startsInterview = (res.actions || []).some((a) => a.type === 'interview')
      const after = () => { if (handsFreeRef.current && !startsInterview) listen(run) }
      if (talk) speak(res.speech, lang, after); else after()
    } catch (e) {
      setLog((l) => [...l, { who: 'ai', text: `Sorry — ${e.message}` }])
      if (talk) speak(`Sorry, ${e.message}`, lang)
    } finally { setBusy(false) }
  }, [projectId, lang, talk, nav, listen])

  // Alt+V toggles the microphone from anywhere.
  useEffect(() => {
    const k = (e) => {
      if (e.altKey && e.key.toLowerCase() === 'v') {
        e.preventDefault()
        setOpen(true)
        listening ? stop() : listen(run)
      }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [listening, listen, stop, run])

  const mic = () => { if (listening) stop(); else { stopSpeaking(); listen(run) } }
  const suggestions = projectId ? SUGGEST_PROJECT : SUGGEST_HOME

  return (
    <>
      <button className={`fab ${listening ? 'live' : ''}`} onClick={() => setOpen((o) => !o)} title="Voice Agent (Alt+V)">
        {listening ? <span className="bars"><i /><i /><i /><i /></span> : '🎙'}
      </button>
      {open && (
        <div className="voice">
          <div className="voice-head">
            <div><b>🎙 Voice Agent</b><small className="muted">Speak to do anything · Alt+V</small></div>
            <div className="row gap">
              <select value={lang} onChange={(e) => setLang(e.target.value)} title="Language">{LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              <button className="icon-btn" onClick={() => { stop(); stopSpeaking(); setOpen(false) }}>✕</button>
            </div>
          </div>
          <div className="voice-body">
            {log.length === 0 && (
              <div className="voice-hello">
                <p>Hi! Tap the mic and say what you need. I can run agents, approve, generate, export, add tasks and answer questions.</p>
                <div className="chips">{suggestions.map((s) => <button key={s} className="chip sm" onClick={() => run(s)}>{s}</button>)}</div>
              </div>
            )}
            {log.map((m, i) => (
              <div key={i} className={`vmsg ${m.who}`}>
                {m.answer ? <RichText text={m.answer.answer} /> : m.text}
                {m.answer?.sources?.length > 0 && <div className="vsrc">{m.answer.sources.map((s) => <span key={s.id}>📄 R{s.id} · {s.source}</span>)}</div>}
                {m.engine && <div><Badge kind={m.engine.includes('offline') ? 'gray' : 'violet'}>{m.engine}</Badge></div>}
              </div>
            ))}
            {listening && <div className="vmsg me live">{interim || 'Listening…'}</div>}
            {busy && <div className="vmsg ai"><span className="dots"><i /><i /><i /></span></div>}
            <div ref={end} />
          </div>
          {error && <div className="voice-err">{error}</div>}
          <div className="voice-foot">
            <button className={`mic ${listening ? 'on' : ''}`} onClick={mic} title={listening ? 'Stop' : 'Speak'}>{listening ? '■' : '🎙'}</button>
            <form className="row gap grow" onSubmit={(e) => { e.preventDefault(); run(text); setText('') }}>
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Speak, or type a command…" />
            </form>
          </div>
          <div className="voice-opts">
            <label className="toggle"><input type="checkbox" checked={talk} onChange={(e) => setTalk(e.target.checked)} disabled={!ttsSupported} />Speak replies</label>
            <label className="toggle" title="After each reply the mic opens again. Say “stop listening” to end."><input type="checkbox" checked={handsFree} onChange={(e) => { setHandsFree(e.target.checked); if (e.target.checked && !listening) listen(run) }} />Hands-free conversation</label>
          </div>
        </div>
      )}
      {interview && <ExitInterview projectId={interview} lang={lang} onClose={() => setInterview(null)} />}
    </>
  )
}
