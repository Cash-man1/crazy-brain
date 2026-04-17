import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const token = localStorage.getItem('token')

  if (loading) {
    return <div className="route-loading">Checking session...</div>
  }

  if (!token || !user) {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}