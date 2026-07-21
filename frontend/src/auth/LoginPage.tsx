/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useState } from 'react';
import { Form, Input, Button, Alert, Tabs, Select, Modal } from 'antd';
import {
  MailOutlined, LockOutlined, LoginOutlined, UserSwitchOutlined, GlobalOutlined,
  SunOutlined, MoonOutlined, UserAddOutlined, SafetyCertificateOutlined, TeamOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthProvider';
import { useBreakpoint } from '../hooks/useBreakpoint';
import { useTheme } from '../hooks/useTheme';
import { accountApi } from '../api/account';

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
  const [mfaChallenge, setMfaChallenge] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [resetOpen, setResetOpen] = useState(false);
  const [resetEmail, setResetEmail] = useState('');

  // Admin registration entry is hidden by default; shown only via ?admin=1 query param
  // to keep the public login page clean for regular users.
  const showAdminTab = new URLSearchParams(window.location.search).get('admin') === '1';

  const toggleLanguage = () => {
    const nextLang = i18n.language.startsWith('zh') ? 'en' : 'zh';
    i18n.changeLanguage(nextLang);
    localStorage.setItem('ey-language', nextLang);
  };

  const syncLanguage = (pref?: string) => {
    if (pref && pref !== i18n.language) i18n.changeLanguage(pref);
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
      if (tokenData.mfa_required) {
        setMfaChallenge(tokenData.challenge);
        return;
      }

      const profileResponse = await fetch('/api/v1/auth/me/', {
        headers: { Authorization: `Bearer ${tokenData.access}` },
      });
      if (!profileResponse.ok) throw new Error('profile_load_failed');
      const user = await profileResponse.json();

      login({ token: tokenData.access, user });
      syncLanguage(user.language_preference);
    } catch (err: unknown) {
      const messageKey = err instanceof Error ? err.message : 'login_failed';
      setError(t(messageKey) || t('login_failed'));
    } finally {
      setLoading(false);
    }
  };

  const completeMfa = async () => {
    setLoading(true);
    setError('');
    try {
      const tokenData = await accountApi.completeMfa(mfaChallenge, mfaCode);
      login({ token: tokenData.access, user: tokenData.user });
      syncLanguage(tokenData.user?.language_preference);
      setMfaChallenge('');
      setMfaCode('');
    } catch {
      setError(t('login_failed'));
    } finally {
      setLoading(false);
    }
  };

  const requestReset = async () => {
    setLoading(true);
    try {
      await accountApi.requestPasswordReset(resetEmail);
      setResetOpen(false);
      setInfo(t('password_reset_sent'));
    } catch {
      setError(t('save_error'));
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
      syncLanguage(data.user?.language_preference);
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
      syncLanguage(data.user?.language_preference);
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
              <Input prefix={<MailOutlined />} placeholder={t('email_placeholder')} autoComplete="email" className="input-focus-float" />
            </Form.Item>
            <Form.Item name="password" label={t('password_label')} rules={[{ required: true, message: t('validation_password_required') }]}>
              <Input.Password prefix={<LockOutlined />} placeholder={t('password_placeholder')} autoComplete="current-password" className="input-focus-float" />
            </Form.Item>
            <Button type="link" onClick={() => setResetOpen(true)} style={{ padding: 0, marginBottom: 8 }}>
              {t('forgot_password')}
            </Button>
            <Form.Item style={{ marginTop: 12, marginBottom: 0 }}>
              <div>
                <Button type="primary" htmlType="submit" icon={<LoginOutlined />} loading={loading} block className="login-btn-premium" style={{ height: 48, fontWeight: 600, borderRadius: 14 }}>
                  {t('sign_in')}
                </Button>
              </div>
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
              <Input prefix={<MailOutlined />} placeholder={t('email_placeholder')} autoComplete="email" className="input-focus-float" />
            </Form.Item>
            <Form.Item name="service_line" label={t('service_line_label')} rules={[{ required: true, message: t('validation_service_line_required') }]}>
              <Select
                placeholder={t('service_line_placeholder')}
                suffixIcon={<TeamOutlined />}
                options={SERVICE_LINES.map((sl) => ({ value: sl, label: t(`sl_${sl}`) }))}
                className="input-focus-float"
              />
            </Form.Item>
            <Form.Item name="password" label={t('password_label')} rules={passwordRules}>
              <Input.Password prefix={<LockOutlined />} placeholder={t('password_placeholder')} autoComplete="new-password" className="input-focus-float" />
            </Form.Item>
            {confirmPasswordField}
            <Form.Item style={{ marginTop: 12, marginBottom: 0 }}>
              <div>
                <Button type="primary" htmlType="submit" icon={<UserAddOutlined />} loading={loading} block className="login-btn-premium" style={{ height: 48, fontWeight: 600, borderRadius: 14 }}>
                  {t('create_account')}
                </Button>
              </div>
            </Form.Item>
          </Form>
        </div>
      ),
    },
    ...(showAdminTab ? [{
      key: 'admin',
      label: <span><SafetyCertificateOutlined /> {t('auth_tab_admin')}</span>,
      children: (
        <div className="login-input-wrapper">
          <p style={{ color: 'var(--color-text-secondary)', margin: '0 0 18px', fontSize: 13 }}>{t('admin_register_subtitle')}</p>
          <Form layout="vertical" size="large" onFinish={handleAdminRegister} requiredMark={false} validateTrigger="onBlur">
            <Form.Item name="email" label={t('email_label')} rules={[{ required: true, message: t('validation_email_required') }, { type: 'email', message: t('validation_email_invalid') }]}>
              <Input prefix={<MailOutlined />} placeholder={t('email_placeholder')} autoComplete="email" className="input-focus-float" />
            </Form.Item>
            <Form.Item name="code" label={t('admin_code_label')} rules={[{ required: true, message: t('validation_code_required') }]}>
              <Input prefix={<SafetyCertificateOutlined />} placeholder={t('admin_code_placeholder')} autoComplete="off" className="input-focus-float" />
            </Form.Item>
            <Form.Item name="password" label={t('password_label')} rules={passwordRules}>
              <Input.Password prefix={<LockOutlined />} placeholder={t('password_placeholder')} autoComplete="new-password" className="input-focus-float" />
            </Form.Item>
            {confirmPasswordField}
            <Form.Item style={{ marginTop: 12, marginBottom: 0 }}>
              <div>
                <Button type="primary" htmlType="submit" icon={<SafetyCertificateOutlined />} loading={loading} block className="login-btn-premium" style={{ height: 48, fontWeight: 600, borderRadius: 14 }}>
                  {t('register_admin_btn')}
                </Button>
              </div>
            </Form.Item>
          </Form>
        </div>
      ),
    }] : []),
  ];

  const headerTitle = activeTab === 'signin' ? t('login_title')
    : activeTab === 'register' ? t('register_title')
    : showAdminTab ? t('admin_register_title') : t('login_title');
  const headerSubtitle = activeTab === 'signin' ? t('login_subtitle')
    : activeTab === 'register' ? t('register_subtitle')
    : showAdminTab ? t('admin_register_subtitle') : t('login_subtitle');

  return (
    <div className="kp-login">
      <div className="kp-login__tools">
        <Button
          shape="circle"
          icon={<GlobalOutlined />}
          onClick={toggleLanguage}
          title={i18n.language.startsWith('zh') ? 'Switch to English' : '切换为中文'}
        />
        <Button
          shape="circle"
          icon={isDark ? <SunOutlined /> : <MoonOutlined />}
          onClick={() => setThemeMode(isDark ? 'light' : 'dark')}
          title={isDark ? t('switch_to_light') : t('switch_to_dark')}
        />
      </div>
      <main className={`kp-login__card${isNarrow ? ' is-narrow' : ''}`}>
        {!isNarrow && (
          <section className="kp-login__brand" aria-labelledby="login-brand-title">
            <div className="kp-login__mark" aria-hidden="true">K</div>
            <h1 id="login-brand-title">KnowPilot</h1>
            <p>{t('login_brand_desc')}</p>
            <div className="kp-login__features">
              {[t('login_feature_1'), t('login_feature_2'), t('login_feature_3')].map((item) => (
                <div key={item} className="kp-login__feature">
                  <span aria-hidden="true" />
                  {item}
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="kp-login__form" aria-labelledby="login-form-title">
          <h2 id="login-form-title">{headerTitle}</h2>
          <p className="kp-login__subtitle">{headerSubtitle}</p>

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
          <Modal open={Boolean(mfaChallenge)} title={t('mfa_challenge_title')}
            onCancel={() => setMfaChallenge('')} onOk={completeMfa} confirmLoading={loading}
            className="section-enter"
          >
            <Input value={mfaCode} onChange={(event) => setMfaCode(event.target.value)}
              autoComplete="one-time-code" placeholder={t('mfa_code')} className="input-focus-float" />
          </Modal>
          <Modal open={resetOpen} title={t('forgot_password')}
            onCancel={() => setResetOpen(false)} onOk={requestReset} confirmLoading={loading}>
            <Input value={resetEmail} onChange={(event) => setResetEmail(event.target.value)}
              autoComplete="email" placeholder={t('email_placeholder')} />
          </Modal>
        </section>
      </main>
    </div>
  );
}
