import { Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './layout/AppLayout';
import ChatPage from './pages/ChatPage';
import HistoryPage from './pages/HistoryPage';
import ProfilePage from './pages/ProfilePage';
import KnowledgeBasePage from './pages/admin/KnowledgeBasePage';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { useAuth } from './auth/AuthProvider';
import { useState } from 'react';

function App() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/chat" /> : <LoginPage />}
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="admin/knowledge" element={<KnowledgeBasePage />} />
      </Route>
    </Routes>
  );
}

function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('admin@ey.com');
  const [password, setPassword] = useState('admin123');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async () => {
    setLoading(true);
    setError('');
    try {
      // Authenticate with backend
      const response = await fetch('/api/v1/auth/token/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        throw new Error('Login failed. Please check your credentials.');
      }

      const tokenData = await response.json();

      // Get user profile
      const profileResponse = await fetch('/api/v1/auth/me/', {
        headers: { Authorization: `Bearer ${tokenData.access}` },
      });

      if (!profileResponse.ok) {
        throw new Error('Failed to load user profile.');
      }

      const user = await profileResponse.json();

      login({
        token: tokenData.access,
        user: {
          id: user.id,
          email: user.email,
          username: user.username,
          is_hr_admin: user.is_hr_admin,
          language_preference: user.language_preference,
          service_line: user.service_line,
          office_location: user.office_location,
          role_level: user.role_level,
        },
      });
    } catch (err: any) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100vh',
      background: 'linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%)',
    }}>
      <div style={{
        padding: 48,
        background: 'white',
        borderRadius: 12,
        boxShadow: '0 4px 24px rgba(0,0,0,0.1)',
        width: 400,
        textAlign: 'center',
      }}>
        <h1 style={{ color: '#E00033', margin: 0, fontSize: 48, fontWeight: 700 }}>EY</h1>
        <h2 style={{ marginBottom: 8, fontWeight: 400, color: '#333' }}>Onboarding AI</h2>
        <p style={{ color: '#999', marginBottom: 32, fontSize: 14 }}>
          Your intelligent onboarding assistant
        </p>

        <div style={{ textAlign: 'left', marginBottom: 24 }}>
          <label style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#666' }}>
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
            style={{
              width: '100%',
              padding: '10px 12px',
              border: '1px solid #d9d9d9',
              borderRadius: 6,
              fontSize: 14,
              boxSizing: 'border-box',
              outline: 'none',
            }}
            placeholder="your.email@ey.com"
          />
        </div>

        <div style={{ textAlign: 'left', marginBottom: 24 }}>
          <label style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#666' }}>
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
            style={{
              width: '100%',
              padding: '10px 12px',
              border: '1px solid #d9d9d9',
              borderRadius: 6,
              fontSize: 14,
              boxSizing: 'border-box',
              outline: 'none',
            }}
            placeholder="Enter your password"
          />
        </div>

        {error && (
          <div style={{
            background: '#fff2f0',
            border: '1px solid #ffccc7',
            borderRadius: 6,
            padding: '8px 12px',
            marginBottom: 16,
            color: '#cf1322',
            fontSize: 13,
            textAlign: 'left',
          }}>
            {error}
          </div>
        )}

        <button
          onClick={handleLogin}
          disabled={loading}
          style={{
            width: '100%',
            padding: '12px 0',
            background: loading ? '#ccc' : '#E00033',
            color: 'white',
            border: 'none',
            borderRadius: 6,
            cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: 16,
            fontWeight: 500,
            transition: 'background 0.2s',
          }}
        >
          {loading ? 'Logging in...' : 'Login'}
        </button>

        <p style={{ marginTop: 16, fontSize: 12, color: '#999' }}>
          Demo: admin@ey.com / admin123
        </p>
      </div>
    </div>
  );
}

export default App;
