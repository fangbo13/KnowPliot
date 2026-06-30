/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useState } from 'react';
import { Form, Input, Button, Alert, Tabs, Select } from 'antd';
import {
  MailOutlined, LockOutlined, LoginOutlined, UserSwitchOutlined, GlobalOutlined,
  SunOutlined, MoonOutlined, UserAddOutlined, SafetyCertificateOutlined, TeamOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthProvider';
import { useBreakpoint } from '../hooks/useBreakpoint';
import { useTheme } from '../hooks/useTheme';

// Service Line options — values match backend User.SERVICE_LINE_CHOICES.
const SERVICE_LINES = ['assurance', 'consulting', 'tax', 'strategy_transactions', 'core'] as const;

/** Pull a human-readable message out of a DRF error body. */
function firstError(data: any): string {
  if (!data) return '';
  if (typeof data === 'string') return data;
  if (data.detail) return String(data.detail);
  for (const key of Object.keys(data)) {
    const v = data[key];
    if (Array.isArray(v) && v.length) return `${v[0]}`;
    if (typeof v === 'string') return v;
  }
  return '';
}

export default function LoginPage() {
  const { t, i18n } = useTranslation('common');
  const { login } = useAuth();
  const bp = useBreakpoint();
  const isNarrow = bp.sm;
  const { effective, setThemeMode } = useTheme();
  const isDark = effective === 'dark';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [activeTab, setActiveTab] = useState('signin');
  const [form] = Form.useForm();

  const toggleLanguage = () => {
    const nextLang = i18n.language.startsWith('zh') ? 'en' : 'zh';
    i18n.changeLanguage(nextLang);
    localStorage.setItem('ey-language', nextLang);
  };

  const syncLanguage = async (pref?: string) => {
    const { default: i18nModule } = await import('../i18n');
    if (pref && pref !== i18nModule.language) i18nModule.changeLanguage(pref);
  };

  // NOTE: login auth data-flow preserved verbatim from the hardened V4.3 implementation.
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

      login({ token: tokenData.access, user });
      await syncLanguage(user.language_preference);
    } catch (err: unknown) {
      const messageKey = err instanceof Error ? err.message : 'login_failed';
      setError(t(messageKey) || t('login_failed'));
    } finally {
      setLoading(false);
    }
  };

  // V7.0: regular self-registration (Service Line required).
  const handleRegister = async (values: { email: string; password: string; service_line: string }) => {
    setLoading(true);
    setError('');
    setInfo('');
    try {
      const resp = await fetch('/api/v1/auth/register/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: values.email, password: values.password, service_line: values.service_line,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setError(firstError(data) || t('register_failed'));
        return;
      }
      if (data.pending) {
        setInfo(t('register_success_pending'));
        setActiveTab('signin');
        return;
      }
      login({ token: data.access, user: data.user });
      await syncLanguage(data.user?.language_preference);
    } catch {
      setError(t('register_failed'));
    } finally {
      setLoading(false);
    }
  };

  // V7.0: admin registration via a tiered admin registration code.
  const handleAdminRegister = async (values: { email: string; password: string; code: string }) => {
    setLoading(true);
    setError('');
    setInfo('');
    try {
      const resp = await fetch('/api/v1/auth/register-admin/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: values.email, password: values.password, code: values.code }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setError(firstError(data) || t('admin_code_invalid'));
        return;
      }
      login({ token: data.access, user: data.user });
      await syncLanguage(data.user?.language_preference);
    } catch {
      setError(t('register_failed'));
    } finally {
      setLoading(false);
    }
  };

  const passwordRules = [
    { required: true, message: t('validation_password_required') },
    { min: 8, message: t('validation_password_min') },
  ];

  const confirmPasswordField = (
    <Form.Item
      name="confirm"
      label={t('confirm_password_label')}
      dependencies={['password']}
      rules={[
        { required: true, message: t('validation_password_required') },
        ({ getFieldValue }) => ({
          validator(_, value) {
            if (!value || getFieldValue('password') === value) return Promise.resolve();
            return Promise.reject(new Error(t('validation_password_mismatch')));
          },
        }),
      ]}
    >
      <Input.Password prefix={<LockOutlined />} placeholder={t('confirm_password_placeholder')} autoComplete="new-password" />
    </Form.Item>
  );

  const tabItems = [
    {
      key: 'signin',
      label: <span><LoginOutlined /> {t('auth_tab_signin')}</span>,
      children: (
        <div className="login-input-wrapper">
          <div
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
              marginBottom: 24, padding: '10px 14px', background: 'var(--accent-soft)',
              border: '1px solid var(--color-border-secondary)', borderRadius: 12,
            }}
          >
            <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{t('demo_hint')}</span>
            <Button type="text" size="small" icon={<UserSwitchOutlined />}
              onClick={() => form.setFieldsValue({ email: 'admin@test.ey.com', password: 'admin123' })}
              style={{ color: 'var(--accent-text)', fontWeight: 600, flexShrink: 0 }}>
              {t('demo_fill_btn')}
            </Button>
          </div>
          <Form form={form} layout="vertical" size="large" onFinish={handleLogin} requiredMark={false} validateTrigger="onChange">
            <Form.Item name="email" label={t('email_label')} rules={[{ required: true, message: t('validation_email_required') }, { type: 'email', message: t('validation_email_invalid') }]}>
              <Input prefix={<MailOutlined />} placeholder={t('email_placeholder')} autoComplete="email" />
            </Form.Item>
            <Form.Item name="password" label={t('password_label')} rules={[{ required: true, message: t('validation_password_required') }]}>
              <Input.Password prefix={<LockOutlined />} placeholder={t('password_placeholder')} autoComplete="current-password" />
            </Form.Item>
            <Form.Item style={{ marginTop: 12, marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" icon={<LoginOutlined />} loading={loading} block className="login-btn-premium" style={{ height: 48, fontWeight: 600, borderRadius: 14 }}>
                {t('sign_in')}
              </Button>
            </Form.Item>
          </Form>
        </div>
      ),
    },
    {
      key: 'register',
      label: <span><UserAddOutlined /> {t('auth_tab_register')}</span>,
      children: (
        <div className="login-input-wrapper">
          <Form layout="vertical" size="large" onFinish={handleRegister} requiredMark={false} validateTrigger="onBlur">
            <Form.Item name="email" label={t('email_label')} rules={[{ required: true, message: t('validation_email_required') }, { type: 'email', message: t('validation_email_invalid') }]}>
              <Input prefix={<MailOutlined />} placeholder={t('email_placeholder')} autoComplete="email" />
            </Form.Item>
            <Form.Item name="service_line" label={t('service_line_label')} rules={[{ required: true, message: t('validation_service_line_required') }]}>
              <Select
                placeholder={t('service_line_placeholder')}
                suffixIcon={<TeamOutlined />}
                options={SERVICE_LINES.map((sl) => ({ value: sl, label: t(`sl_${sl}`) }))}
              />
            </Form.Item>
            <Form.Item name="password" label={t('password_label')} rules={passwordRules}>
              <Input.Password prefix={<LockOutlined />} placeholder={t('password_placeholder')} autoComplete="new-password" />
            </Form.Item>
            {confirmPasswordField}
            <Form.Item style={{ marginTop: 12, marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" icon={<UserAddOutlined />} loading={loading} block className="login-btn-premium" style={{ height: 48, fontWeight: 600, borderRadius: 14 }}>
                {t('create_account')}
              </Button>
            </Form.Item>
          </Form>
        </div>
      ),
    },
    {
      key: 'admin',
      label: <span><SafetyCertificateOutlined /> {t('auth_tab_admin')}</span>,
      children: (
        <div className="login-input-wrapper">
          <p style={{ color: 'var(--color-text-secondary)', margin: '0 0 18px', fontSize: 13 }}>{t('admin_register_subtitle')}</p>
          <Form layout="vertical" size="large" onFinish={handleAdminRegister} requiredMark={false} validateTrigger="onBlur">
            <Form.Item name="email" label={t('email_label')} rules={[{ required: true, message: t('validation_email_required') }, { type: 'email', message: t('validation_email_invalid') }]}>
              <Input prefix={<MailOutlined />} placeholder={t('email_placeholder')} autoComplete="email" />
            </Form.Item>
            <Form.Item name="code" label={t('admin_code_label')} rules={[{ required: true, message: t('validation_code_required') }]}>
              <Input prefix={<SafetyCertificateOutlined />} placeholder={t('admin_code_placeholder')} autoComplete="off" />
            </Form.Item>
            <Form.Item name="password" label={t('password_label')} rules={passwordRules}>
              <Input.Password prefix={<LockOutlined />} placeholder={t('password_placeholder')} autoComplete="new-password" />
            </Form.Item>
            {confirmPasswordField}
            <Form.Item style={{ marginTop: 12, marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" icon={<SafetyCertificateOutlined />} loading={loading} block className="login-btn-premium" style={{ height: 48, fontWeight: 600, borderRadius: 14 }}>
                {t('register_admin_btn')}
              </Button>
            </Form.Item>
          </Form>
        </div>
      ),
    },
  ];

  const headerTitle = activeTab === 'signin' ? t('login_title')
    : activeTab === 'register' ? t('register_title') : t('admin_register_title');
  const headerSubtitle = activeTab === 'signin' ? t('login_subtitle')
    : activeTab === 'register' ? t('register_subtitle') : t('admin_register_subtitle');

  return (
    <div style={{ minHeight: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, background: 'var(--color-bg-body)', position: 'relative' }}>
      <div style={{ position: 'absolute', top: 24, right: 24, display: 'flex', gap: 12, zIndex: 1000 }}>
        <Button
          shape="circle"
          icon={<GlobalOutlined />}
          onClick={toggleLanguage}
          title={i18n.language.startsWith('zh') ? 'Switch to English' : '切换为中文'}
          style={{ border: '1px solid var(--color-border-secondary)', background: 'var(--color-bg-container)' }}
        />
        <Button
          shape="circle"
          icon={isDark ? <SunOutlined /> : <MoonOutlined />}
          onClick={() => setThemeMode(isDark ? 'light' : 'dark')}
          title={isDark ? t('switch_to_light') : t('switch_to_dark')}
          style={{ border: '1px solid var(--color-border-secondary)', background: 'var(--color-bg-container)' }}
        />
      </div>
      <div
        style={{
          display: 'flex', flexDirection: isNarrow ? 'column' : 'row',
          width: '100%', maxWidth: 940, minHeight: isNarrow ? 'auto' : 540,
          borderRadius: 24, overflow: 'hidden',
          boxShadow: 'var(--shadow-xl)', background: 'var(--color-bg-container)',
          border: '1px solid var(--color-border-secondary)',
          animation: 'softFadeInUp var(--dur-slow) var(--ease-out)',
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
            <div style={{
              position: 'absolute', width: 360, height: 360, borderRadius: '50%', right: -120, top: -80,
              background: 'radial-gradient(circle, rgba(var(--accent-rgb), 0.18) 0%, transparent 70%)',
              pointerEvents: 'none',
              animation: 'ambientGlow 18s infinite ease-in-out',
            }} />
            <div style={{
              width: 64, height: 64, borderRadius: 18, background: 'var(--gradient-accent)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 28,
              boxShadow: 'var(--shadow-accent-lg)', color: '#fff', fontFamily: "'Fraunces', serif", fontWeight: 600, fontSize: 30,
              transition: 'transform var(--dur-slow) var(--ease-spring)',
            }}
            onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.08) rotate(2deg)'}
            onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1) rotate(0deg)'}
            >K</div>
            <h1 style={{ fontFamily: "'Fraunces', serif", fontWeight: 500, fontSize: 34, margin: 0, letterSpacing: '-0.02em', color: '#F8F5EE' }}>KnowPilot</h1>
            <p style={{ color: 'rgba(243,239,230,0.62)', marginTop: 12, fontSize: 14.5, lineHeight: 1.6, maxWidth: 280 }}>{t('login_brand_desc')}</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 40 }}>
              {[t('login_feature_1'), t('login_feature_2'), t('login_feature_3')].map((item, index) => (
                <div
                  key={item}
                  className="login-feature-item"
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    color: 'rgba(243,239,230,0.78)', fontSize: 13.5,
                    animationDelay: `${index * 150 + 200}ms`,
                  }}
                >
                  <span style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--accent)', flexShrink: 0 }} />
                  {item}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Form column */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: isNarrow ? '32px 24px' : '48px 48px', minWidth: isNarrow ? 'auto' : 340 }}>
          <h2 style={{ fontFamily: "'Fraunces', serif", fontWeight: 500, fontSize: 26, margin: '0 0 6px' }}>{headerTitle}</h2>
          <p style={{ color: 'var(--color-text-secondary)', margin: '0 0 20px', fontSize: 14 }}>{headerSubtitle}</p>

          {error && (
            <Alert message={t('login_error')} description={error} type="error" showIcon closable style={{ marginBottom: 16, borderRadius: 12 }} onClose={() => setError('')} />
          )}
          {info && (
            <Alert message={info} type="success" showIcon closable style={{ marginBottom: 16, borderRadius: 12 }} onClose={() => setInfo('')} />
          )}

          <Tabs
            activeKey={activeTab}
            onChange={(k) => { setActiveTab(k); setError(''); setInfo(''); }}
            items={tabItems}
            destroyOnHidden
          />
        </div>
      </div>
    </div>
  );
}
