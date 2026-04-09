import { Routes, Route, Navigate } from 'react-router-dom'
import LiveDashboardNoAuth from './pages/LiveDashboardNoAuth'
import Login from './pages/Login'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import ChatLive from './pages/ChatLive'
import ConnectTelegram from './pages/ConnectTelegram'
import PhoneForgotPassword from './pages/PhoneForgotPassword'

function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<LiveDashboardNoAuth />} />
        <Route path="/dashboard" element={<LiveDashboardNoAuth />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/phone-forgot-password" element={<PhoneForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/chat" element={<ChatLive />} />
        <Route path="/connect" element={<ConnectTelegram />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

export default App
