import { useEffect, useState } from 'react'
import { api, download, openInTab } from '../../api'
import { Badge, Empty, Modal, Ring, RichText, Spinner, Status, timeAgo, useToast } from '../../components/ui'

const SECTIONS = [
  ['completed', 'Completed tasks', '✓'], ['ongoing', 'Ongoing tasks', '◔'], ['pending', 'Pending tasks', '○'],
  ['decisions', 'Technical decisions', '◆'], ['issues', 'Known issues', '⚠'], ['dependencies', 'Dependencies', '⛓'], ['contacts', 'Who to ask', '☺'],
]

function Item({ r, onCite }) {
  return (
    <li className="h-item">
      <div className="row gap wrap"><b>{r.title}</b>{r.status && <Status s={r.status} />}{r.priority && <Badge kind={r.priority === 'high' ? 'red' : 'gray'}>{r.priority}</Badge>}
        {r.owner && <span className="owner">👤 {r.owner}</span>}<button className="cite" onClick={() => onCite(r.id)}>R{r.id}</button></div>
      {r.rationale && <div className="small"><b>Why:</b> {r.rationale}</div>}
      {r.detail && r.detail !== r.title && <div className="small muted pre clamp3">{r.detail}</div>}
      <div className="tiny muted">📄 {r.source}</div>
    </li>
  )
}

function Report({ h, onCite }) {
  const c = h.content
  return (
    <div className="report">
      <div className="report-head">
        <div>
          <div className="eyebrow">Handover report · v{h.version}</div>
          <h2>{c.project.name}</h2>
          <div className="row gap wrap muted">
            <span>From <b>{h.outgoing_name || '—'}</b> → To <b>{h.incoming_name || '—'}</b></span>
            <Status s={h.status} /><Badge kind={h.generated_by === 'templates' ? 'gray' : 'violet'}>written by {h.generated_by}</Badge>
            <span>{timeAgo(h.created_at)}</span>
          </div>
        </div>
        <Ring value={h.readiness} size={96} />
      </div>
      {h.manager_note && <div className="note-box"><b>Manager note:</b> {h.manager_note}</div>}
      <section><h3>Project overview</h3><RichText text={c.overview} onCite={onCite} /></section>
      <div className="grid g2">
        <section className="hl"><h3>➜ Recommended next steps</h3><ol>{c.next_steps.map((s, i) => <li key={i}><RichText text={s} onCite={onCite} /></li>)}</ol></section>
        <section className="hl"><h3>🗓 Your first week</h3><ul>{c.first_week.map((s, i) => <li key={i}><RichText text={s} onCite={onCite} /></li>)}</ul></section>
      </div>
      {c.risks?.length > 0 && <section><h3>⚠ Risks to watch</h3><ul>{c.risks.map((s, i) => <li key={i}><RichText text={s} onCite={onCite} /></li>)}</ul></section>}
      <div className="grid g2">
        {SECTIONS.map(([k, t, ic]) => (
          <section key={k}><h3>{ic} {t} <span className="count">{c[k]?.length || 0}</span></h3>
            {c[k]?.length ? <ul className="h-list">{c[k].map((r) => <Item key={r.id} r={r} onCite={onCite} />)}</ul> : <p className="muted">None recorded.</p>}
          </section>
        ))}
        <section><h3>📄 Important documents</h3><ul className="h-list">{c.documents.map((d) => <li key={d.id} className="h-item"><b>{d.filename}</b><div className="tiny muted">{d.records} approved records</div></li>)}</ul></section>
      </div>
      {c.answered_questions?.length > 0 && (
        <section><h3>💬 Clarifications from the outgoing member</h3>
          {c.answered_questions.map((x, i) => <div key={i} className="qa"><b>Q.</b> {x.q}<br /><b>A.</b> {x.a} <span className="muted small">— {x.by}</span></div>)}
        </section>
      )}
      {c.open_questions?.length > 0 && (
        <section><h3>❓ Still unanswered</h3><ul>{c.open_questions.map((x, i) => <li key={i}><Status s={x.severity} /> {x.q}</li>)}</ul></section>
      )}
    </div>
  )
}

export default function Handover({ projectId, project, role, reload, openSource }) {
  const toast = useToast()
  const [list, setList] = useState(null)
  const [cur, setCur] = useState(null)
  const [busy, setBusy] = useState(false)
  const [gen, setGen] = useState(null)
  const [approve, setApprove] = useState(null)

  const open = async (id) => setCur(await api(`/projects/${projectId}/handovers/${id}`))
  const load = async (pick) => {
    const l = await api(`/projects/${projectId}/handovers`)
    setList(l)
    if (pick) open(pick)
    else if (l.length && !cur) open(l[0].id)
  }
  useEffect(() => { load() }, [projectId])

  const generate = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      const h = await api(`/projects/${projectId}/handovers`, { method: 'POST', body: gen })
      setGen(null); toast(`Handover v${h.version} generated`)
      setCur(h); load(h.id); reload()
    } catch (e2) { toast(e2.message, 'err') } finally { setBusy(false) }
  }
  const doApprove = async (e) => {
    e.preventDefault()
    const h = await api(`/projects/${projectId}/handovers/${cur.id}/approve`, { method: 'POST', body: { manager_note: approve } })
    setApprove(null); setCur(h); load(h.id); reload(); toast('Handover approved — the incoming member can now read it')
  }
  const base = (h) => `Handover_${project.name.replace(/\W+/g, '_')}_v${h.version}`

  if (!list) return <Spinner />
  return (
    <div className="ho">
      <aside className="ho-side card">
        {role !== 'incoming' && <button className="primary block" onClick={() => setGen({ outgoing_name: '', incoming_name: '' })}>✦ Generate handover</button>}
        <h4 className="muted">Versions</h4>
        {list.length === 0 && <p className="muted small">{role === 'incoming' ? 'No approved handover yet.' : 'Approve records in Review, then generate.'}</p>}
        {list.map((h) => (
          <button key={h.id} className={`ver ${cur?.id === h.id ? 'on' : ''}`} onClick={() => open(h.id)}>
            <b>v{h.version}</b><Status s={h.status} /><small className="muted">{h.readiness}% · {timeAgo(h.created_at)}</small>
          </button>
        ))}
      </aside>
      <div className="ho-main">
        {!cur ? (list.length ? <Spinner /> : <Empty icon="⎙" title="No handover yet">The Handover Writer agent builds it from manager-approved records only, so every line can be trusted.</Empty>) : (
          <>
            <div className="toolbar">
              <div className="row gap">
                <button className="ghost" onClick={() => download(`/projects/${projectId}/handovers/${cur.id}/export/pdf`, `${base(cur)}.pdf`)}>⬇ PDF</button>
                <button className="ghost" onClick={() => download(`/projects/${projectId}/handovers/${cur.id}/export/html`, `${base(cur)}.html`)}>⬇ HTML</button>
                <button className="ghost" onClick={() => download(`/projects/${projectId}/handovers/${cur.id}/export/md`, `${base(cur)}.md`)}>⬇ Markdown</button>
                <button className="ghost" onClick={() => openInTab(`/projects/${projectId}/handovers/${cur.id}/export/html`)}>⎙ Print view</button>
              </div>
              {role === 'manager' && cur.status !== 'approved' && <button className="primary" onClick={() => setApprove('')}>✓ Approve handover</button>}
            </div>
            <Report h={cur} onCite={openSource} />
          </>
        )}
      </div>
      {gen && (
        <Modal title="Generate handover" onClose={() => setGen(null)}>
          <form className="form" onSubmit={generate}>
            <p className="muted">Uses <b>{project.review?.approved || 0}</b> approved records and all answered gap questions. Unreviewed records are left out.</p>
            <label>Outgoing member<input value={gen.outgoing_name} onChange={(e) => setGen({ ...gen, outgoing_name: e.target.value })} placeholder="e.g. Arjun Mehta" /></label>
            <label>Incoming member<input value={gen.incoming_name} onChange={(e) => setGen({ ...gen, incoming_name: e.target.value })} placeholder="e.g. Karan Shah" /></label>
            <button className="primary" disabled={busy}>{busy ? 'Handover Writer is working…' : 'Generate'}</button>
          </form>
        </Modal>
      )}
      {approve !== null && (
        <Modal title={`Approve handover v${cur.version}`} onClose={() => setApprove(null)}>
          <form className="form" onSubmit={doApprove}>
            {cur.readiness < 70 && <div className="alert warn">Readiness is only {cur.readiness}%. Consider answering the open gap questions first.</div>}
            <label>Note for the incoming member (optional)<textarea rows={3} value={approve} onChange={(e) => setApprove(e.target.value)} /></label>
            <button className="primary">Approve and publish to incoming member</button>
          </form>
        </Modal>
      )}
    </div>
  )
}
