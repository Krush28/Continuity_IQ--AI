import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, download } from '../../api'
import { useRecognizer } from '../../components/speech'
import { Badge, Empty, Modal, Spinner, Status, timeAgo, useToast } from '../../components/ui'

const kb = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

export default function Documents({ projectId, reload }) {
  const toast = useToast()
  const nav = useNavigate()
  const [docs, setDocs] = useState(null)
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const [useAi, setUseAi] = useState(true)
  const [results, setResults] = useState(null)
  const [chunks, setChunks] = useState(null)
  const input = useRef()
  const [note, setNote] = useState({ title: '', text: '' })
  const dict = useRecognizer('en-IN')
  const dictate = () => (dict.listening ? dict.stop() : dict.listen((t) => setNote((n) => ({ ...n, text: (n.text ? n.text + '\n' : '') + '- ' + t }))))
  const capture = async () => {
    setBusy(true)
    try {
      const r = await api(`/projects/${projectId}/documents/text`, { method: 'POST', body: { ...note, use_ai: useAi } })
      toast(`Note captured → ${r.stats.records} records`)
      setNote({ title: '', text: '' }); load(); reload()
    } catch (e) { toast(e.message, 'err') } finally { setBusy(false) }
  }

  const load = () => api(`/projects/${projectId}/documents`).then(setDocs)
  useEffect(() => { load() }, [projectId])

  const upload = async (files) => {
    if (!files?.length) return
    const form = new FormData()
    Array.from(files).forEach((f) => form.append('files', f))
    setBusy(true); setResults(null)
    try {
      const res = await api(`/projects/${projectId}/documents?use_ai=${useAi}`, { method: 'POST', form })
      setResults(res.results)
      const ok = res.results.filter((r) => !r.error).length
      toast(`${ok} file(s) processed`)
      load(); reload()
    } catch (e) { toast(e.message, 'err') } finally { setBusy(false); if (input.current) input.current.value = '' }
  }

  const reprocess = async (d) => {
    setBusy(true)
    try {
      const r = await api(`/projects/${projectId}/documents/${d.id}/reprocess?use_ai=${useAi}`, { method: 'POST' })
      toast(`${d.filename}: ${r.stats.records} records (${r.stats.engine || 'rules'})`)
      load(); reload()
    } catch (e) { toast(e.message, 'err') } finally { setBusy(false) }
  }
  const remove = async (d) => {
    if (!confirm(`Delete ${d.filename} and its extracted records?`)) return
    await api(`/projects/${projectId}/documents/${d.id}`, { method: 'DELETE' })
    load(); reload()
  }
  const showChunks = async (d) => setChunks({ doc: d, items: await api(`/projects/${projectId}/documents/${d.id}/chunks`) })

  return (
    <div className="stack">
      <div className={`drop ${drag ? 'over' : ''} ${busy ? 'busy' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files) }}
        onClick={() => !busy && input.current?.click()}>
        <input ref={input} type="file" multiple accept=".pdf,.docx,.txt,.md" hidden onChange={(e) => upload(e.target.files)} />
        {busy ? <Spinner label="Extracting text, categorising and verifying sources…" /> : (
          <>
            <div className="drop-ic">⇪</div>
            <b>Drop the outgoing member's files here</b>
            <span className="muted">Requirements, technical notes, task lists, bug lists, meeting notes · PDF, DOCX, TXT, MD · up to 20 MB</span>
          </>
        )}
      </div>
      <label className="toggle" onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
        Use the GenAI Extraction Agent when configured (falls back to the offline rules engine automatically)
      </label>

      <div className="card capture">
        <div className="row between"><h3 className="card-title">✎ Quick capture — meeting notes, WhatsApp/Slack exports or dictation</h3>
          <button className={`ghost sm ${dict.listening ? 'rec' : ''}`} onClick={dictate}>{dict.listening ? '■ Stop dictation' : '🎙 Dictate'}</button></div>
        <div className="row gap mb"><input placeholder="Title, e.g. Standup 14 Nov" value={note.title} onChange={(e) => setNote({ ...note, title: e.target.value })} /></div>
        <textarea rows={4} placeholder={'Paste or dictate. Headings like "Pending:", "Decisions:", "Bugs:" help the rules engine.\n- Pending: write API docs, owner: Karan Shah'} value={note.text + (dict.listening && dict.interim ? '\n' + dict.interim : '')} onChange={(e) => setNote({ ...note, text: e.target.value })} />
        <div className="row between mt"><span className="muted small">Saved as a source document, so every record still links back to it.</span>
          <button className="primary" disabled={busy || note.text.trim().length < 10} onClick={capture}>Capture & extract</button></div>
      </div>

      {results && (
        <div className="card">
          <h3 className="card-title">Processing results</h3>
          {results.map((r) => (
            <div key={r.filename} className="result-row">
              <b>{r.filename}</b>
              {r.error ? <span className="err">{r.error}</span> : (
                <span className="muted">{r.stats.chunks} text units → <b>{r.stats.records} records</b> via {r.stats.engine}
                  {r.stats.ai_records !== undefined && ` · AI: ${r.stats.verified} verified, ${r.stats.unverified} need checking`}
                  {r.stats.error && <span className="err"> · {r.stats.error}</span>}</span>
              )}
            </div>
          ))}
          <button className="primary mt" onClick={() => nav(`/projects/${projectId}/review`)}>Review the extracted records →</button>
        </div>
      )}

      {!docs ? <Spinner /> : docs.length === 0 ? (
        <Empty icon="📄" title="No documents yet">Upload the files the outgoing member worked with. Try the six files in <code>sample_docs/</code>.</Empty>
      ) : (
        <div className="card p0">
          <table className="tbl">
            <thead><tr><th>Document</th><th>Status</th><th>Engine</th><th>Records</th><th>Uploaded</th><th /></tr></thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td><div className="doc-name"><span className={`ft ft-${d.file_type}`}>{d.file_type}</span><div><b>{d.filename}</b><small className="muted">{kb(d.size_bytes)}{d.pages ? ` · ${d.pages} pages` : ''} · {d.chunks} text units</small></div></div>
                    {d.error && <div className="err small">{d.error}</div>}</td>
                  <td><Status s={d.status} /></td>
                  <td>{d.extracted_by && <Badge kind={d.extracted_by.includes('ai') ? 'violet' : 'gray'}>{d.extracted_by}</Badge>}</td>
                  <td><b>{d.records}</b></td>
                  <td className="muted small">{timeAgo(d.uploaded_at)}</td>
                  <td className="actions">
                    <button className="ghost sm" onClick={() => showChunks(d)}>Text</button>
                    <button className="ghost sm" onClick={() => download(`/projects/${projectId}/documents/${d.id}/file`, d.filename)}>Original</button>
                    <button className="ghost sm" onClick={() => reprocess(d)} disabled={busy}>Re-run</button>
                    <button className="ghost sm danger" onClick={() => remove(d)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {chunks && (
        <Modal title={`Extracted text · ${chunks.doc.filename}`} onClose={() => setChunks(null)} wide>
          <div className="src-ctx">
            {chunks.items.map((c) => (
              <div key={c.id} className="src-line">
                <span className="src-sec">S{c.id}{c.page ? ` · p.${c.page}` : ''}{c.section ? ` · ${c.section}` : ''}</span>{c.text}
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  )
}
