import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Spinner, useToast } from '../components/ui'

const INFO = {
  none: { t: 'Offline rules engine', d: 'No AI. Rule-based extraction, checks and templates. Works anywhere, no internet.' },
  ollama: { t: 'Ollama (local LLM)', d: 'Fully offline GenAI on your laptop. Install Ollama, run `ollama pull qwen2.5:7b`.' },
  groq: { t: 'Groq', d: 'Very fast hosted open models. Free API key at console.groq.com.' },
  gemini: { t: 'Google Gemini', d: 'Uses Gemini’s OpenAI-compatible endpoint. Key from aistudio.google.com.' },
  openai: { t: 'OpenAI', d: 'GPT models via the OpenAI API.' },
  anthropic: { t: 'Anthropic Claude', d: 'Claude models via the Anthropic API.' },
}

export default function Settings() {
  const { user } = useAuth()
  const toast = useToast()
  const [cfg, setCfg] = useState(null)
  const [f, setF] = useState(null)
  const [test, setTest] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api('/settings/ai').then((c) => { setCfg(c); setF({ provider: c.provider, model: c.model, base_url: c.base_url, api_key: '' }) }) }, [])
  if (!cfg) return <div className="page"><Spinner /></div>
  const isMgr = user.role === 'manager'

  const pick = (p) => setF({ provider: p, model: cfg.providers[p]?.model || '', base_url: cfg.providers[p]?.base_url || '', api_key: '' })
  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      const body = { ...f, api_key: f.api_key ? f.api_key : null }
      const c = await api('/settings/ai', { method: 'PUT', body })
      setCfg(c); toast('AI settings saved')
      setTest(await api('/settings/ai/test', { method: 'POST' }))
    } catch (e2) { toast(e2.message, 'err') } finally { setBusy(false) }
  }
  const needsKey = ['openai', 'groq', 'gemini', 'anthropic'].includes(f.provider)

  return (
    <div className="page narrow">
      <div className="page-head"><div><h1>AI settings</h1><p className="muted">Choose the GenAI engine behind the agents. Everything keeps working offline if AI is off or unreachable.</p></div></div>
      <form className="stack" onSubmit={save}>
        <div className="grid g3">
          {Object.entries(INFO).map(([k, m]) => (
            <button type="button" key={k} disabled={!isMgr} className={`card provider ${f.provider === k ? 'on' : ''}`} onClick={() => pick(k)}>
              <b>{m.t}</b><small className="muted">{m.d}</small>
            </button>
          ))}
        </div>
        {f.provider !== 'none' && (
          <div className="card form">
            <div className="grid g2">
              <label>Model<input value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} disabled={!isMgr} /></label>
              <label>Base URL<input value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} disabled={!isMgr} /></label>
            </div>
            {needsKey && (
              <label>API key {cfg.has_key && cfg.provider === f.provider && <span className="muted">(saved {cfg.key_hint} — leave blank to keep)</span>}
                <input type="password" value={f.api_key} onChange={(e) => setF({ ...f, api_key: e.target.value })} disabled={!isMgr} autoComplete="off" placeholder="Paste key" />
              </label>
            )}
            <p className="muted small">Keys are stored in this server’s database (or set <code>LLM_API_KEY</code> in <code>backend/.env</code>), never in the browser or source code.</p>
          </div>
        )}
        {isMgr ? <div className="row gap"><button className="primary" disabled={busy}>{busy ? 'Saving & testing…' : 'Save and test connection'}</button>
          <button type="button" className="ghost" onClick={async () => setTest(await api('/settings/ai/test', { method: 'POST' }))}>Test only</button></div>
          : <p className="muted">Only managers can change AI settings.</p>}
        {test && <div className={`alert ${test.ok ? 'ok' : ''}`}>{test.message}</div>}
      </form>
    </div>
  )
}
