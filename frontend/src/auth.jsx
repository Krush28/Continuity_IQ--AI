import { createContext, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const demo = () => api('/auth/demo', { method: 'POST' })
      .then((r) => { setToken(r.token); setUser(r.user); if (window.location.pathname === '/' || window.location.pathname === '/login') window.history.replaceState(null, '', '/projects/1') })
      .catch(() => {})
    if (!getToken()) { demo().finally(() => setReady(true)); return }
    api('/auth/me').then(setUser).catch(() => { setToken(null); return demo() }).finally(() => setReady(true))
  }, [])

  const signIn = async (path, body) => {
    const res = await api(path, { method: 'POST', body })
    setToken(res.token)
    setUser(res.user)
    return res.user
  }
  const signOut = () => { setToken(null); setUser(null) }

  return <AuthCtx.Provider value={{ user, ready, signIn, signOut }}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
