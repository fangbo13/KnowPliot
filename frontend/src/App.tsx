import { Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './layout/AppLayout';
import ChatPage from './pages/ChatPage';
import HistoryPage from './pages/HistoryPage';
import ProfilePage from './pages/ProfilePage';
import KnowledgeBasePage from './pages/admin/KnowledgeBasePage';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { useAuth } from './auth/AuthProvider';
import { useState, useEffect } from 'react';
import { Form, Input, Button, Typography, Alert, Layout, Space } from 'antd';
import { MailOutlined, LockOutlined, LoginOutlined } from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
const { Content } = Layout;

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [isNarrow, setIsNarrow] = useState(window.innerWidth < 800);

  // Responsive: hide brand panel on narrow screens
  useEffect(() => {
    const handler = () => setIsNarrow(window.innerWidth < 800);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  const handleLogin = async (values: { email: string; password: string }) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/v1/auth/token/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: values.email, password: values.password }),
      });

      if (!response.ok) {
        throw new Error('Login failed. Please check your credentials.');
      }

      const tokenData = await response.json();

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
    <Layout style={{
      minHeight: '100vh',
      background: 'var(--color-bg-body)',
    }}>
      <Content style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
      }}>
        <div style={{
          display: 'flex',
          flexDirection: isNarrow ? 'column' : 'row',
          width: '100%',
          maxWidth: 900,
          minHeight: isNarrow ? 'auto' : 520,
          borderRadius: 16,
          overflow: 'hidden',
          boxShadow: 'var(--shadow-xl)',
          background: 'var(--color-bg-container)',
          animation: 'fadeInUp 0.4s ease-out',
        }}>
          {/* Left: Brand Panel (hidden on narrow screens) */}
          {!isNarrow && (
            <div style={{
              flex: '0 0 380px',
              background: 'linear-gradient(135deg, #262626 0%, #1a1a1a 50%, #262626 100%)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 48,
              position: 'relative',
            }}>
              {/* Yellow accent stripe - top */}
              <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: 4,
                background: '#FFE500',
              }} />

              {/* Yellow accent stripe - left edge */}
              <div style={{
                position: 'absolute',
                top: '10%',
                left: 0,
                width: 3,
                height: '80%',
                background: 'linear-gradient(to bottom, transparent, #FFE500, transparent)',
                borderRadius: 2,
              }} />

              {/* EY Logo */}
              <div style={{
                width: 100,
                height: 100,
                borderRadius: 20,
                background: '#FFE500',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 32,
                boxShadow: '0 8px 32px rgba(255, 229, 0, 0.3)',
              }}>
                <span style={{
                  fontSize: 48,
                  fontWeight: 800,
                  color: '#262626',
                  letterSpacing: -2,
                }}>EY</span>
              </div>

              <Title level={2} style={{ color: 'white', margin: 0, fontWeight: 600 }}>
                Onboarding AI
              </Title>
              <Paragraph style={{
                color: 'rgba(255,255,255,0.6)',
                textAlign: 'center',
                marginTop: 12,
                fontSize: 14,
                maxWidth: 280,
              }}>
                Your intelligent onboarding assistant. Ask me anything about policies, benefits, and more.
              </Paragraph>

              {/* Feature list */}
              <Space direction="vertical" size={12} style={{ marginTop: 40 }}>
                {['Smart Q&A powered by AI', 'Knowledge base integration', 'Personalized assistance'].map((item) => (
                  <Space key={item} style={{ color: 'rgba(255,255,255,0.7)' }}>
                    <div style={{
                      width: 6,
                      height: 6,
                      borderRadius: 3,
                      background: '#FFE500',
                      flexShrink: 0,
                    }} />
                    <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: 13 }}>{item}</Text>
                  </Space>
                ))}
              </Space>
            </div>
          )}

          {/* Right: Login Form */}
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            padding: isNarrow ? '40px 24px' : '48px 40px',
            minWidth: isNarrow ? 'auto' : 340,
          }}>
            <Title level={3} style={{ marginTop: 0, fontWeight: 600 }}>
              Welcome Back
            </Title>
            <Text type="secondary" style={{ marginBottom: 32, display: 'block' }}>
              Sign in to your account to continue
            </Text>

            {error && (
              <Alert
                message="Login Error"
                description={error}
                type="error"
                showIcon
                closable
                style={{ marginBottom: 24 }}
                onClose={() => setError('')}
              />
            )}

            <Form
              layout="vertical"
              size="large"
              initialValues={{ email: 'admin@ey.com', password: 'admin123' }}
              onFinish={handleLogin}
              requiredMark={false}
            >
              <Form.Item
                name="email"
                rules={[
                  { required: true, message: 'Please enter your email' },
                  { type: 'email', message: 'Please enter a valid email' },
                ]}
              >
                <Input
                  prefix={<MailOutlined />}
                  placeholder="your.email@ey.com"
                  autoComplete="email"
                />
              </Form.Item>

              <Form.Item
                name="password"
                rules={[{ required: true, message: 'Please enter your password' }]}
              >
                <Input.Password
                  prefix={<LockOutlined />}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                />
              </Form.Item>

              <Form.Item style={{ marginTop: 8 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<LoginOutlined />}
                  loading={loading}
                  block
                  className="login-submit"
                  style={{ height: 44, fontWeight: 600 }}
                >
                  Sign In
                </Button>
              </Form.Item>
            </Form>

            <Text
              type="secondary"
              style={{
                display: 'block',
                textAlign: 'center',
                marginTop: 16,
                fontSize: 12,
              }}
            >
              Demo: admin@ey.com / admin123
            </Text>
          </div>
        </div>
      </Content>
    </Layout>
  );
}

export default App;
