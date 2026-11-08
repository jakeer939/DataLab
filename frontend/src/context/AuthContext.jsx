import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import api from '../api/client'

const AuthContext = createContext(null)

const TOKEN_KEY = 'datalab_token'
const USER_KEY = 'datalab_user'

function readStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState(readStoredUser)
  const [loading, setLoading] = useState(Boolean(localStorage.getItem(TOKEN_KEY)))

  const clearSession = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }, [])

  const applySession = useCallback((data) => {
    if (!data?.access_token) {
      throw new Error('The server did not return an access token')
    }
    localStorage.setItem(TOKEN_KEY, data.access_token)
    const nextUser = data.user || null
    if (nextUser) {
      localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
    }
    setToken(data.access_token)
    setUser(nextUser)
    return nextUser
  }, [])

  useEffect(() => {
    let active = true
    if (!token) {
      setLoading(false)
      return undefined
    }

    api
      .get('/auth/me')
      .then((response) => {
        if (!active) return
        const nextUser = response.data
        localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
        setUser(nextUser)
      })
      .catch(() => {
        if (!active) return
        clearSession()
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [token, clearSession])

  const login = useCallback(
    async (credentials) => {
      const response = await api.post('/auth/login', credentials)
      return applySession(response.data)
    },
    [applySession],
  )

  const register = useCallback(
    async (payload) => {
      const response = await api.post('/auth/register', payload)
      return applySession(response.data)
    },
    [applySession],
  )

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // Logout is stateless; clearing the local session is what matters.
    }
    clearSession()
  }, [clearSession])

  const value = useMemo(
    () => ({ user, token, loading, login, register, logout, clearSession }),
    [user, token, loading, login, register, logout, clearSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return context
}
