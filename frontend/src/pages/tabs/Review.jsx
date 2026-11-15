import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import { Badge, CATEGORY, CatBadge, Empty, Modal, Spinner, Status, useToast } from '../../components/ui'

const STATUSES = { task: ['completed', 'ongoing', 'pending'], issue: ['open', 'resolved'] }

function RecordForm({ initial, onSave, onClose }) {
  const [f, setF] = useState({ category: 'task', title: '', detail: '', status: '', owner: '', priority: '', rationale: '', ...initial })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  return (
    <Modal title={initial?.id ? `Edit R${initial.id}` : 'Add a record manually'} onClose={onClose}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); onSave(f) }}>
        <div className="grid g2">
          <label>Category<select value={f.category} onChange={set('category')}>{Object.entries(CATEGORY).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}</select></label>
          {STATUSES[f.category] && <label>Status<select value={f.status} onChange={set('status')}><option value="">—</option>{STATUSES[f.category].map((s) => <option key={s}>{s}</option>)}</select></label>}
        </div>
        <label>Title<input value={f.title} onChange={set('title')} required minLength={2} /></label>
        <label>Detail<textarea rows={3} value={f.detail} onChange={set('detail')} /></label>
        <div className="grid g2">
          <label>Owner / person<input value={f.owner} onChange={set('owner')} /></label>
          <label>Priority<select value={f.priority} onChange={set('priority')}><option value="">—</option>{['high', 'medium', 'low'].map((p) => <option key={p}>{p}</option>)}</select></label>
        </div>
        {f.category === 'decision' && <label>Why was it decided?<textarea rows={2} value={f.rationale} onChange={set('rationale')} /></label>}
        <button className="primary">Save</button>
      </form>
    </Modal>
  )
}

export default function Review({ projectId, role, reload, openSource }) {
  const toast = useToast()
  const [recs, setRecs] = useState(null)
  const [cat, setCat] = useState('')
  const [state, setState] = useState('unreviewed')
  const [flagOnly, setFlagOnly] = useState(false)
  const [sel, setSel] = useState(new Set())
  const [edit, setEdit] = useState(null)
  const isMgr = role === 'manager'

  const load = () => api(`/projects/${projectId}/records`).then(setRecs)
  useEffect(() => { load() }, [projectId])

  const shown = useMemo(() => (recs || []).filter((r) => (!cat || r.category === cat) && (!state || r.review_state === state) && (!flagOnly || r.flagged)), [recs, cat, state, flagOnly])
  const counts = useMemo(() => {
    const c = {}
    ;(recs || []).filter((r) => !state || r.review_state === state).forEach((r) => { c[r.category] = (c[r.category] || 0) + 1 })
    return c
  }, [recs, state])

  const review = async (ids, st) => {
    if (!ids.length) return
    await api(`/projects/${projectId}/records/review`, { method: 'POST', body: { ids, state: st } })
    toast(`${ids.length} record(s) ${st}`)
    setSel(new Set()); load(); reload()
  }
  const save = async (f) => {
    try {
      if (f.id) await api(`/projects/${projectId}/records/${f.id}`, { method: 'PATCH', body: f })
      else await api(`/projects/${projectId}/records`, { method: 'POST', body: f })
      setEdit(null); load(); reload(); toast('Saved')
    } catch (e) { toast(e.message, 'err') }
  }
  const remove = async (r) => {
    if (!confirm(`Delete R${r.id}?`)) return
    await api(`/projects/${projectId}/records/${r.id}`, { method: 'DELETE' }); load(); reload()
  }
  const toggle = (id) => { const s = new Set(sel); s.has(id) ? s.delete(id) : s.add(id); setSel(s) }
  const safe = shown.filter((r) => !r.flagged && r.confidence >= 0.7 && r.review_state === 'unreviewed').map((r) => r.id)

  if (!recs) return <Spinner label="Loading records" />
  return (
    <div className="stack">
      <div className="toolbar">
        <div className="chips">
          <button className={!cat ? 'chip on' : 'chip'} onClick={() => setCat('')}>All <b>{Object.values(counts).reduce((a, b) => a + b, 0)}</b></button>
          {Object.entries(CATEGORY).map(([k, m]) => (
            <button key={k} className={cat === k ? 'chip on' : 'chip'} onClick={() => setCat(k)}>{m.icon} {m.label} <b>{counts[k] || 0}</b></button>
          ))}
        </div>
        <div className="row gap">
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="unreviewed">Waiting for review</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="">All states</option>
          </select>
          <label className="toggle"><input type="checkbox" checked={flagOnly} onChange={(e) => setFlagOnly(e.target.checked)} />Flagged only</label>
          <button className="ghost" onClick={() => setEdit({})}>+ Add record</button>
        </div>
      </div>

      {isMgr ? (
        <div className="bulkbar">
          <span>{sel.size ? `${sel.size} selected` : 'Manager review: approve what is correct, fix or reject the rest.'}</span>
          <div className="row gap">
            {safe.length > 0 && <button className="ghost" onClick={() => review(safe, 'approved')}>✓ Approve {safe.length} high-confidence, unflagged</button>}
            <button className="primary" disabled={!sel.size} onClick={() => review([...sel], 'approved')}>Approve selected</button>
            <button className="ghost danger" disabled={!sel.size} onClick={() => review([...sel], 'rejected')}>Reject selected</button>
          </div>
        </div>
      ) : <div className="bulkbar"><span>You can edit and add records. Only the project manager can approve them.</span></div>}

      {shown.length === 0 ? <Empty icon="✓" title="Nothing here">{state === 'unreviewed' ? 'All records in this view are reviewed.' : 'No records match the filters.'}</Empty> : (
        <div className="rec-list">
          {isMgr && (
            <label className="select-all"><input type="checkbox" checked={shown.every((r) => sel.has(r.id))}
              onChange={(e) => setSel(e.target.checked ? new Set(shown.map((r) => r.id)) : new Set())} /> Select all {shown.length}</label>
          )}
          {shown.map((r) => (
            <div key={r.id} className={`rec ${r.flagged ? 'flagged' : ''} ${sel.has(r.id) ? 'sel' : ''}`}>
              {isMgr && <input type="checkbox" checked={sel.has(r.id)} onChange={() => toggle(r.id)} />}
              <div className="rec-main">
                <div className="row gap wrap">
                  <span className="rid">R{r.id}</span><CatBadge c={r.category} /><Status s={r.status} />
                  {r.priority && <Badge kind={r.priority === 'high' || r.priority === 'critical' ? 'red' : 'gray'}>{r.priority}</Badge>}
                  {r.owner && <span className="owner">👤 {r.owner}</span>}
                  <Badge kind={r.extracted_by === 'ai' ? 'violet' : 'gray'} title="How this record was created">{r.extracted_by}</Badge>
                  <span className={`conf ${r.confidence >= 0.75 ? 'hi' : r.confidence >= 0.5 ? 'mid' : 'lo'}`} title="Confidence">{Math.round(r.confidence * 100)}%</span>
                  {r.review_state !== 'unreviewed' && <Status s={r.review_state} />}
                </div>
                <div className="rec-title">{r.title}</div>
                {r.rationale && <div className="small"><b>Why:</b> {r.rationale}</div>}
                {r.detail && r.detail !== r.title && <div className="small muted pre clamp3">{r.detail}</div>}
                {r.flagged && <div className="flag">⚑ {r.flag_reason}</div>}
                <button className="src-link" onClick={() => openSource(r.id)}>📄 {r.source_location}</button>
              </div>
              <div className="rec-actions">
                {isMgr && r.review_state !== 'approved' && <button className="ok sm" onClick={() => review([r.id], 'approved')} title="Approve">✓</button>}
                {isMgr && r.review_state !== 'rejected' && <button className="no sm" onClick={() => review([r.id], 'rejected')} title="Reject">✕</button>}
                <button className="ghost sm" onClick={() => setEdit(r)}>Edit</button>
                <button className="ghost sm danger" onClick={() => remove(r)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {edit && <RecordForm initial={edit} onSave={save} onClose={() => setEdit(null)} />}
    </div>
  )
}
