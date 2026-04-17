import { Routes, Route, Navigate } from 'react-router-dom'
import LiveDashboardNoAuth from './pages/LiveDashboardNoAuth'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import ChatLive from './pages/ChatLive'
import ConnectTelegram from './pages/ConnectTelegram'
import PhoneForgotPassword from './pages/PhoneForgotPassword'

function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<LiveDashboardNoAuth />} />
        <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        <Route path="/register" element={<Navigate to="/dashboard" replace />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/phone-forgot-password" element={<PhoneForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/chat" element={<ChatLive />} />
        <Route path="/connect" element={<ConnectTelegram />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </div>
  )
}

export default App
