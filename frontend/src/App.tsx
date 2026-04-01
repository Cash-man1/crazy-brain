import { Routes, Route, Navigate } from 'react-router-dom'
import LiveDashboardNoAuth from './pages/LiveDashboardNoAuth'

function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<LiveDashboardNoAuth />} />
        <Route path="/dashboard" element={<LiveDashboardNoAuth />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

export default App
