import { Routes, Route, Navigate } from 'react-router-dom'
import LiveDashboardNoAuth from './pages/LiveDashboardNoAuth'

function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<LiveDashboardNoAuth />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </div>
  )
}

export default App
