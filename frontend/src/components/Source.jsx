import { useEffect, useState } from 'react'
import { api, download } from '../api'
import { Badge, CatBadge, Modal, Spinner, Status } from './ui'

/** Shows a record together with the exact source paragraph (and its neighbours) it came from. */
export default function SourceModal({ projectId, recordId, onClose }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    api(`/projects/${projectId}/records/${recordId}/source`).then(setData).catch((e) => setErr(e.message))
  }, [projectId, recordId])
  const r = data?.record
  return (
    <Modal title={`Source of R${recordId}`} onClose={onClose} wide>
      {err && <div className="alert">{err}</div>}
      {!data && !err && <Spinner label="Loading source" />}
      {r && (
        <>
          <div className="row gap wrap mb">
            <CatBadge c={r.category} /><Status s={r.status} /><Status s={r.review_state} />
            <Badge kind="violet">{r.extracted_by}</Badge>
            <span className="muted">confidence {Math.round(r.confidence * 100)}%</span>
          </div>
          <h3 className="mt0">{r.title}</h3>
          {r.owner && <p><b>Owner:</b> {r.owner}</p>}
          {r.rationale && <p><b>Why:</b> {r.rationale}</p>}
          {r.detail && <p className="pre">{r.detail}</p>}
          <div className="src-loc">📄 {r.source_location}
            {data.document && <button className="link" onClick={() => download(`/projects/${projectId}/documents/${data.document.id}/file`, data.document.filename)}>open original</button>}
          </div>
          {data.context.length > 0 ? (
            <div className="src-ctx">
              {data.context.map((c) => (
                <div key={c.id} className={c.current ? 'src-line cur' : 'src-line'}>
                  {c.section && <span className="src-sec">{c.page ? `p.${c.page} · ` : ''}{c.section}</span>}
                  {c.text}
                </div>
              ))}
            </div>
          ) : r.source_excerpt && <blockquote>{r.source_excerpt}</blockquote>}
        </>
      )}
    </Modal>
  )
}
