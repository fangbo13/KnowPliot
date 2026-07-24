/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Alert } from 'antd';
import {
  MailOutlined, LockOutlined, LoginOutlined, GlobalOutlined,
  SunOutlined, MoonOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthProvider';
import { useBreakpoint } from '../hooks/useBreakpoint';
import { useTheme } from '../hooks/useTheme';

export default function AdminLoginPage() {
  const { t, i18n } = useTranslation('common');
  const { login } = useAuth();
  const navigate = useNavigate();
  const bp = useBreakpoint();
  const isNarrow = bp.sm;
  const { effective, setThemeMode } = useTheme();
  const isDark = effective === 'dark';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const toggleLanguage = () => {
    const nextLang = i18n.language.startsWith('zh') ? 'en' : 'zh';
    i18n.changeLanguage(nextLang);
    localStorage.setItem('ey-language', nextLang);
  };

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
        setError(t('admin_login_mfa_required', 'This account has MFA enabled. Please use the regular login page.'));
        return;
      }

      const profileResponse = await fetch('/api/v1/auth/me/', {
        headers: { Authorization: `Bearer ${tokenData.access}` },
      });
      if (!profileResponse.ok) throw new Error('profile_load_failed');
      const user = await profileResponse.json();

      // Only allow superuser login through this entry point.
      if (!user.is_superuser && !user.is_super_admin) {
        setError(t('admin_login_not_super', 'Access denied. This entrance is reserved for the platform super admin.'));
        return;
      }

      login({ token: tokenData.access, user });

      // Sync language preference
      const pref = user.language_preference;
      if (pref && (pref === 'en' || pref === 'zh')) {
        i18n.changeLanguage(pref);
        localStorage.setItem('ey-language', pref);
      }

      navigate('/platform-admin/dashboard', { replace: true });
    } catch {
      setError(t('login_failed'));
    } finally {
      setLoading(false);
    }
  };

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
          <section className="kp-login__brand" aria-labelledby="admin-login-brand-title">
            <div className="kp-login__mark" aria-hidden="true" style={{ background: 'var(--gradient-accent)' }}>K</div>
            <h1 id="admin-login-brand-title">KnowPilot</h1>
            <p>{t('admin_login_brand_desc', 'Platform administration portal — restricted to authorized super admins.')}</p>
            <div className="kp-login__features">
              {[
                t('admin_login_feature_1', 'Centralized platform control'),
                t('admin_login_feature_2', 'User & role management'),
                t('admin_login_feature_3', 'Audit & compliance oversight'),
              ].map((item) => (
                <div key={item} className="kp-login__feature">
                  <span aria-hidden="true" />
                  {item}
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="kp-login__form" aria-labelledby="admin-login-form-title">
          <h2 id="admin-login-form-title">
            <SafetyCertificateOutlined style={{ marginRight: 8, color: 'var(--accent)' }} />
            {t('admin_login_title', 'Super Admin Login')}
          </h2>
          <p className="kp-login__subtitle">{t('admin_login_subtitle', 'Authorized personnel only')}</p>

          {error && (
            <Alert message={t('login_error')} description={error} type="error" showIcon closable
              style={{ marginBottom: 16, borderRadius: 12 }}
              onClose={() => setError('')} />
          )}

          <div className="login-input-wrapper">
            <Form layout="vertical" size="large" onFinish={handleLogin} requiredMark={false} validateTrigger="onChange">
              <Form.Item name="email" label={t('email_label')}
                rules={[{ required: true, message: t('validation_email_required') }, { type: 'email', message: t('validation_email_invalid') }]}>
                <Input prefix={<MailOutlined />} placeholder={t('email_placeholder')} autoComplete="email" className="input-focus-float" />
              </Form.Item>
              <Form.Item name="password" label={t('password_label')}
                rules={[{ required: true, message: t('validation_password_required') }]}>
                <Input.Password prefix={<LockOutlined />} placeholder={t('password_placeholder')} autoComplete="current-password" className="input-focus-float" />
              </Form.Item>
              <Form.Item style={{ marginTop: 12, marginBottom: 0 }}>
                <Button type="primary" htmlType="submit" icon={<LoginOutlined />} loading={loading} block
                  className="login-btn-premium"
                  style={{ height: 48, fontWeight: 600, borderRadius: 14 }}>
                  {t('sign_in')}
                </Button>
              </Form.Item>
            </Form>
          </div>
        </section>
      </main>
    </div>
  );
}
