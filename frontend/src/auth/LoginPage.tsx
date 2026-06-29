import { useState } from 'react';
import { Form, Input, Button, Alert } from 'antd';
import { MailOutlined, LockOutlined, LoginOutlined, UserSwitchOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthProvider';
import { useBreakpoint } from '../hooks/useBreakpoint';

export default function LoginPage() {
  const { t } = useTranslation('common');
  const { login } = useAuth();
  const bp = useBreakpoint();
  const isNarrow = bp.sm;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [form] = Form.useForm();

  // NOTE: auth data-flow preserved verbatim from the hardened V4.3 implementation.
  const handleLogin = async (values: { email: string; password: string }) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/v1/auth/token/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: values.email, password: values.password }),
      });
      if (!response.ok) throw new Error('login_failed');
      const tokenData = await response.json();

      const profileResponse = await fetch('/api/v1/auth/me/', {
        headers: { Authorization: `Bearer ${tokenData.access}` },
      });
      if (!profileResponse.ok) throw new Error('profile_load_failed');
      const user = await profileResponse.json();

      login({
        token: tokenData.access,
        user: {
          id: user.id,
          email: user.email,
          username: user.username,
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
    <div style={{ minHeight: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, background: 'var(--color-bg-body)' }}>
      <div
        style={{
          display: 'flex', flexDirection: isNarrow ? 'column' : 'row',
          width: '100%', maxWidth: 940, minHeight: isNarrow ? 'auto' : 540,
          borderRadius: 24, overflow: 'hidden',
          boxShadow: 'var(--shadow-xl)', background: 'var(--color-bg-container)',
          border: '1px solid var(--color-border-secondary)',
          animation: 'fadeInUp var(--dur-slow) var(--ease-out)',
        }}
      >
        {/* Brand panel — warm espresso editorial */}
        {!isNarrow && (
          <div style={{
            flex: '0 0 400px', position: 'relative', overflow: 'hidden',
            padding: 48, display: 'flex', flexDirection: 'column', justifyContent: 'center',
            background: 'linear-gradient(165deg, #2C2722 0%, #1B1815 100%)', color: '#F3EFE6',
          }}>
            <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 4, background: 'var(--gradient-accent)' }} />
            <div style={{ position: 'absolute', width: 360, height: 360, borderRadius: '50%', right: -120, top: -80, background: 'radial-gradient(circle, rgba(217,128,92,0.18) 0%, transparent 70%)', pointerEvents: 'none' }} />
            <div style={{
              width: 64, height: 64, borderRadius: 18, background: 'var(--gradient-accent)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 28,
              boxShadow: 'var(--shadow-accent-lg)', color: '#fff', fontFamily: "'Fraunces', serif", fontWeight: 600, fontSize: 30,
            }}>K</div>
            <h1 style={{ fontFamily: "'Fraunces', serif", fontWeight: 500, fontSize: 34, margin: 0, letterSpacing: '-0.02em', color: '#F8F5EE' }}>KnowPilot</h1>
            <p style={{ color: 'rgba(243,239,230,0.62)', marginTop: 12, fontSize: 14.5, lineHeight: 1.6, maxWidth: 280 }}>{t('login_brand_desc')}</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 40 }}>
              {[t('login_feature_1'), t('login_feature_2'), t('login_feature_3')].map((item) => (
                <div key={item} style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'rgba(243,239,230,0.78)', fontSize: 13.5 }}>
                  <span style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--accent)', flexShrink: 0 }} />
                  {item}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Form */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: isNarrow ? '40px 24px' : '52px 44px', minWidth: isNarrow ? 'auto' : 340 }}>
          <h2 style={{ fontFamily: "'Fraunces', serif", fontWeight: 500, fontSize: 26, margin: '0 0 6px' }}>{t('login_title')}</h2>
          <p style={{ color: 'var(--color-text-secondary)', margin: '0 0 28px', fontSize: 14 }}>{t('login_subtitle')}</p>

          {error && (
            <Alert message={t('login_error')} description={error} type="error" showIcon closable style={{ marginBottom: 20, borderRadius: 12 }} onClose={() => setError('')} />
          )}

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 20, padding: '10px 14px', background: 'var(--accent-soft)', border: '1px solid var(--color-border-secondary)', borderRadius: 12 }}>
            <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{t('demo_hint')}</span>
            <Button type="text" size="small" icon={<UserSwitchOutlined />} onClick={() => form.setFieldsValue({ email: 'admin@test.ey.com', password: 'admin123' })} style={{ color: 'var(--accent-text)', fontWeight: 600, flexShrink: 0 }}>
              {t('demo_fill_btn')}
            </Button>
          </div>

          <Form form={form} layout="vertical" size="large" initialValues={{ email: '', password: '' }} onFinish={handleLogin} requiredMark={false} validateTrigger="onChange">
            <Form.Item name="email" label={t('email_label')} rules={[{ required: true, message: t('validation_email_required') }, { type: 'email', message: t('validation_email_invalid') }]}>
              <Input prefix={<MailOutlined />} placeholder={t('email_placeholder')} autoComplete="email" />
            </Form.Item>
            <Form.Item name="password" label={t('password_label')} rules={[{ required: true, message: t('validation_password_required') }]}>
              <Input.Password prefix={<LockOutlined />} placeholder={t('password_placeholder')} autoComplete="current-password" />
            </Form.Item>
            <Form.Item style={{ marginTop: 8, marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" icon={<LoginOutlined />} loading={loading} block style={{ height: 46, fontWeight: 600, borderRadius: 14 }}>
                {t('sign_in')}
              </Button>
            </Form.Item>
          </Form>
        </div>
      </div>
    </div>
  );
}
