import { useState } from 'react';
import { Form, Input, Button, Typography, Alert, Layout, Space } from 'antd';
import { MailOutlined, LockOutlined, LoginOutlined, UserSwitchOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthProvider';
import { useBreakpoint } from '../hooks/useBreakpoint';

const { Title, Text, Paragraph } = Typography;
const { Content } = Layout;

export default function LoginPage() {
  const { t } = useTranslation('common');
  const { login } = useAuth();
  const bp = useBreakpoint();
  const isNarrow = bp.sm; // P1-7: unified breakpoint
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [form] = Form.useForm(); // P1-1: Demo account one-click fill

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
        throw new Error('login_failed');
      }

      const tokenData = await response.json();

      const profileResponse = await fetch('/api/v1/auth/me/', {
        headers: { Authorization: `Bearer ${tokenData.access}` },
      });

      if (!profileResponse.ok) {
        throw new Error('profile_load_failed');
      }

      const user = await profileResponse.json();

      login({
        token: tokenData.access,
        user: {
          id: user.id,
          email: user.email,
          username: user.username,
          // V4.3 UAT FIX: Previously omitted roles/permissions/is_superuser from profile API,
          // causing RoleGuard to deny admin access. The backend /api/v1/auth/me/ endpoint
          // (UserSerializer) returns roles[] and permissions[], but LoginPage only passed
          // role_level (which is an organizational value like "partner", not RBAC "admin").
          // AuthProvider.login() then tried to derive roles from role_level, which failed
          // because role_level="partner" is not in the roleLevelMap.
          // Now: pass all RBAC fields from the profile response.
          is_hr_admin: user.is_hr_admin,
          is_superuser: user.is_superuser ?? false,
          roles: user.roles,
          permissions: user.permissions,
          language_preference: user.language_preference,
          service_line: user.service_line,
          office_location: user.office_location,
          role_level: user.role_level,
        },
      });

      // Sync i18n language after login
      const { default: i18n } = await import('../i18n');
      if (user.language_preference && user.language_preference !== i18n.language) {
        i18n.changeLanguage(user.language_preference);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'login_failed';
      setError(t(message) || t('login_failed'));
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
              background: 'linear-gradient(135deg, #0F172A 0%, #0B1120 50%, #0F172A 100%)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 48,
              position: 'relative',
            }}>
              {/* Blue accent stripe - top */}
              <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: 4,
                background: 'var(--gradient-accent)',
              }} />

              {/* Blue accent stripe - left edge */}
              <div style={{
                position: 'absolute',
                top: '10%',
                left: 0,
                width: 3,
                height: '80%',
                background: `linear-gradient(to bottom, transparent, var(--accent), transparent)`,
                borderRadius: 2,
              }} />

              {/* EY Logo */}
              <div style={{
                width: 100,
                height: 100,
                borderRadius: 20,
                background: 'var(--gradient-accent)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 32,
                boxShadow: 'var(--shadow-accent-lg)',
              }}>
                <span style={{
                  fontSize: 48,
                  fontWeight: 800,
                  color: '#FFFFFF',
                  letterSpacing: -2,
                }}>EY</span>
              </div>

              <Title level={2} style={{
                color: 'white',
                margin: 0,
                fontWeight: 400,
                fontFamily: "'Calistoga', Georgia, serif",
              }}>
                KnowPilot
              </Title>
              <Paragraph style={{
                color: 'rgba(255,255,255,0.6)',
                textAlign: 'center',
                marginTop: 12,
                fontSize: 14,
                maxWidth: 280,
              }}>
                {t('login_brand_desc')}
              </Paragraph>

              {/* Feature list */}
              <Space direction="vertical" size={12} style={{ marginTop: 40 }}>
                {[t('login_feature_1'), t('login_feature_2'), t('login_feature_3')].map((item) => (
                  <Space key={item} style={{ color: 'rgba(255,255,255,0.7)' }}>
                    <div style={{
                      width: 6,
                      height: 6,
                      borderRadius: 3,
                      background: 'var(--accent)',
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
            <Title level={3} style={{ marginTop: 0, fontWeight: 400, fontFamily: "'Calistoga', Georgia, serif" }}>
              {t('login_title')}
            </Title>
            <Text type="secondary" style={{ marginBottom: 32, display: 'block' }}>
              {t('login_subtitle')}
            </Text>

            {error && (
              <Alert
                message={t('login_error')}
                description={error}
                type="error"
                showIcon
                closable
                style={{ marginBottom: 24 }}
                onClose={() => setError('')}
              />
            )}

            <Alert
              type="info"
              message={t('demo_hint')}
              showIcon
              closable
              style={{ marginBottom: 16 }}
            />

            {/* P1-1: Demo account one-click fill button */}
            <Button
              type="link"
              size="small"
              icon={<UserSwitchOutlined />}
              onClick={() => form.setFieldsValue({ email: 'admin@test.ey.com', password: 'admin123' })}
              style={{ marginBottom: 24, color: 'var(--accent)', fontWeight: 500 }}
            >
              {t('demo_fill_btn')}
            </Button>

            <Form
              form={form}
              layout="vertical"
              size="large"
              initialValues={{ email: '', password: '' }}
              onFinish={handleLogin}
              requiredMark={false}
              validateTrigger="onChange"
            >
              <Form.Item
                name="email"
                label={t('email_label')}
                rules={[
                  { required: true, message: t('validation_email_required') },
                  { type: 'email', message: t('validation_email_invalid') },
                ]}
              >
                <Input
                  prefix={<MailOutlined />}
                  placeholder={t('email_placeholder')}
                  autoComplete="email"
                />
              </Form.Item>

              <Form.Item
                name="password"
                label={t('password_label')}
                rules={[{ required: true, message: t('validation_password_required') }]}
              >
                <Input.Password
                  prefix={<LockOutlined />}
                  placeholder={t('password_placeholder')}
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
                  {t('sign_in')}
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
              {t('demo_hint')}
            </Text>
          </div>
        </div>
      </Content>
    </Layout>
  );
}
