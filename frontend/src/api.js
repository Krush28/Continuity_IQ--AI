const TOKEN_KEY = 'ciq_token'

export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export const setToken = (t) => {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
}

export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (form) payload = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload })
  if (res.status === 401 && !path.startsWith('/auth/')) {
    setToken(null)
    window.location.href = '/login'
    throw new Error('Session expired')
  }
  const data = res.headers.get('content-type')?.includes('application/json') ? await res.json() : await res.text()
  if (!res.ok) {
    const msg = typeof data === 'object' ? (Array.isArray(data.detail) ? data.detail.map(d => d.msg).join(', ') : data.detail) : data
    throw new Error(msg || `Request failed (${res.status})`)
  }
  return data
}

export async function download(path, filename) {
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${getToken()}` } })
  if (!res.ok) throw new Error('Download failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export async function openInTab(path) {
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${getToken()}` } })
  const html = await res.text()
  const w = window.open('', '_blank')
  if (w) { w.document.open(); w.document.write(html); w.document.close() }
}
