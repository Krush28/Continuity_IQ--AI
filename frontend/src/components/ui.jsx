import { createContext, useCallback, useContext, useEffect, useState } from 'react'

export const CATEGORY = {
  task: { label: 'Task', icon: '☑' },
  decision: { label: 'Decision', icon: '◆' },
  issue: { label: 'Issue', icon: '⚠' },
  dependency: { label: 'Dependency', icon: '⛓' },
  contact: { label: 'Contact', icon: '☺' },
  note: { label: 'Context', icon: '¶' },
}

export function Badge({ kind = 'gray', children, title }) {
  return <span className={`badge b-${kind}`} title={title}>{children}</span>
}

export function CatBadge({ c }) {
  const m = CATEGORY[c] || { label: c, icon: '•' }
  return <span className={`cat cat-${c}`}>{m.icon} {m.label}</span>
}

const STATUS_KIND = { completed: 'green', ongoing: 'blue', pending: 'amber', open: 'red', resolved: 'green',
  approved: 'green', rejected: 'red', unreviewed: 'gray', draft: 'amber', answered: 'green', dismissed: 'gray',
  high: 'red', medium: 'amber', low: 'gray', processed: 'green', failed: 'red', completed_run: 'green', running: 'blue' }
export function Status({ s }) {
  if (!s) return null
  return <Badge kind={STATUS_KIND[s] || 'gray'}>{s}</Badge>
}

export function Spinner({ label }) {
  return <span className="spin-wrap"><span className="spinner" />{label && <span>{label}</span>}</span>
}

export function Empty({ icon = '◌', title, children }) {
  return <div className="empty"><div className="empty-icon">{icon}</div><h3>{title}</h3><div>{children}</div></div>
}

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="modal-bg" onMouseDown={onClose}>
      <div className={`modal ${wide ? 'wide' : ''}`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose}>✕</button></div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

export function Ring({ value = 0, size = 120, label = 'ready' }) {
  const r = (size - 14) / 2
  const circ = 2 * Math.PI * r
  const color = value >= 80 ? 'var(--green)' : value >= 50 ? 'var(--amber)' : 'var(--red)'
  return (
    <svg width={size} height={size} className="ring">
      <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--line)" strokeWidth="10" fill="none" />
      <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth="10" fill="none" strokeLinecap="round"
        strokeDasharray={circ} strokeDashoffset={circ * (1 - value / 100)} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset .8s ease' }} />
      <text x="50%" y="48%" textAnchor="middle" className="ring-num">{value}%</text>
      <text x="50%" y="64%" textAnchor="middle" className="ring-lbl">{label}</text>
    </svg>
  )
}

/** Renders light markdown (bold, bullets, numbered lists) and turns [R12] into clickable source chips. */
export function RichText({ text = '', onCite }) {
  const inline = (s, key) => {
    const parts = s.split(/(\[R\d+\]|\*\*[^*]+\*\*)/g)
    return parts.map((p, i) => {
      const m = p.match(/^\[R(\d+)\]$/)
      if (m) return <button key={`${key}-${i}`} className="cite" onClick={() => onCite?.(Number(m[1]))} title="Open source record">R{m[1]}</button>
      if (p.startsWith('**') && p.endsWith('**')) return <strong key={`${key}-${i}`}>{p.slice(2, -2)}</strong>
      return <span key={`${key}-${i}`}>{p}</span>
    })
  }
  const lines = String(text).split('\n')
  const out = []
  let list = null
  lines.forEach((ln, i) => {
    const b = ln.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)/)
    if (b) {
      if (!list) { list = []; out.push(list) }
      list.push(<li key={i}>{inline(b[1], i)}</li>)
    } else {
      list = null
      if (ln.trim()) out.push(<p key={i}>{inline(ln, i)}</p>)
    }
  })
  return <div className="rich">{out.map((x, i) => (Array.isArray(x) ? <ul key={`l${i}`}>{x}</ul> : x))}</div>
}

const ToastCtx = createContext(() => {})
export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((msg, kind = 'ok') => {
    const id = Math.random()
    setItems((x) => [...x, { id, msg, kind }])
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 4200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts">{items.map((t) => <div key={t.id} className={`toast t-${t.kind}`}>{t.msg}</div>)}</div>
    </ToastCtx.Provider>
  )
}
export const useToast = () => useContext(ToastCtx)

export function timeAgo(d) {
  if (!d) return ''
  const s = (Date.now() - new Date(d.endsWith?.('Z') || d.includes?.('+') ? d : d + 'Z').getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return new Date(d).toLocaleDateString()
}
