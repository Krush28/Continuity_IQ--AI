import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import { CATEGORY, CatBadge, Empty, Spinner, Status } from '../../components/ui'

export default function SearchTab({ projectId, openSource }) {
  const [params] = useSearchParams()
  const [q, setQ] = useState(params.get('q') || '')
  const [cat, setCat] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async (e) => {
    e?.preventDefault()
    if (!q.trim()) return
    setBusy(true)
    try { setRes(await api(`/projects/${projectId}/search?q=${encodeURIComponent(q)}&category=${cat}`)) } finally { setBusy(false) }
  }
  useEffect(() => { if (params.get('q')) run() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="stack">
      <form className="searchbar" onSubmit={run}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search tasks, decisions, bugs, people, file names…" autoFocus />
        <select value={cat} onChange={(e) => setCat(e.target.value)}><option value="">All categories</option>{Object.entries(CATEGORY).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}</select>
        <button className="primary">Search</button>
      </form>
      {busy && <Spinner />}
      {res && (
        <div className="grid g2 top">
          <div>
            <h3 className="card-title">Records ({res.records.length})</h3>
            {res.records.length === 0 ? <Empty title="No records match" /> : res.records.map((r) => (
              <div key={r.id} className="card hit" onClick={() => openSource(r.id)}>
                <div className="row gap wrap"><span className="rid">R{r.id}</span><CatBadge c={r.category} /><Status s={r.status} />{r.owner && <span className="owner">👤 {r.owner}</span>}</div>
                <b>{r.title}</b>
                <small className="muted">📄 {r.source_location}</small>
              </div>
            ))}
          </div>
          {res.source && (
            <div>
              <h3 className="card-title">Raw document text ({res.source.length})</h3>
              {res.source.map((s) => (
                <div key={s.chunk_id} className="card hit">
                  <small className="muted">📄 {s.filename}{s.page ? ` · p.${s.page}` : ''}{s.section ? ` · ${s.section}` : ''}</small>
                  <div className="small">{s.snippet}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
