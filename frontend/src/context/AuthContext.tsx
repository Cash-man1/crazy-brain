import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-api.onrender.com'

interface User {
  id: number
  email: string
  role: 'admin' | 'vip' | 'user'
  subscription_status: string
  trial_end?: string | null
  is_active?: boolean
}

interface AuthContextType {
  user: User | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
  error: string | null
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 🔥 AUTO LOGIN FIX
  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('token')

      if (!token) {
        setLoading(false)
        return
      }

      try {
        const res = await fetch(`${API_URL}/api/auth/me`, {
          headers: {
            Authorization: `Bearer ${token}`
          }
        })

        if (!res.ok) throw new Error('Session expired')

        const data = await res.json()
        setUser(data)

      } catch {
        localStorage.removeItem('token')
        setUser(null)
      } finally {
        setLoading(false)
      }
    }

    initAuth()
  }, [])

  const login = async (email: string, password: string) => {
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })

      const data = await res.json()

      if (!res.ok) throw new Error(data.detail || 'Login failed')

      localStorage.setItem('token', data.access_token)
      setUser(data.user)

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login error')
      throw err
    } finally {
      setLoading(false)
    }
  }

  const register = async (email: string, password: string) => {
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${API_URL}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })

      const data = await res.json()

      if (!res.ok) throw new Error(data.detail || 'Register failed')

      localStorage.setItem('token', data.access_token)
      setUser(data.user)

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Register error')
      throw err
    } finally {
      setLoading(false)
    }
  }

  const logout = () => {
    localStorage.removeItem('token')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, login, register, logout, loading, error }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}