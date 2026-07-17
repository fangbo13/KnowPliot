/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { Card, Form, Select, Button, message, Typography, Avatar, Row, Col, Input, List, Modal, Switch } from 'antd';
import { UserOutlined, SafetyCertificateOutlined, LockOutlined, CheckOutlined } from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';
import apiClient from '../api/client';
import i18n from '../i18n';
import { accountApi, type AuthSession } from '../api/account';
import { useSpaceStore } from '../store/spaceStore';
import { useTheme } from '../hooks/useTheme';

export default function ProfilePage() {
  const { t } = useTranslation('common');
  const { user, login } = useAuth();
  const [loading, setLoading] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const spaces = useSpaceStore((state) => state.spaces);
  const { setThemeMode } = useTheme();
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [mfaOpen, setMfaOpen] = useState(false);
  const [mfaSecret, setMfaSecret] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);

  const loadSessions = async () => {
    try { setSessions(await accountApi.sessions()); } catch { setSessions([]); }
  };
  useEffect(() => { loadSessions(); }, []);

  const handleFinish = async (values: {
    language_preference: string;
    theme_preference: 'system' | 'light' | 'dark';
    default_space?: string;
    announcements?: boolean;
    quality?: boolean;
  }) => {
    setLoading(true);
    try {
      const response = await apiClient.patch('/auth/me/preferences/', {
        language_preference: values.language_preference,
        theme_preference: values.theme_preference,
        default_space: values.default_space || null,
        notification_preferences: {
          announcements: Boolean(values.announcements),
          quality: Boolean(values.quality),
        },
      });
      message.success(t('save_success'));
      if (user) {
        const saved = localStorage.getItem('ey-auth');
        const token = saved ? JSON.parse(saved).token : null;
        login({
          token,
          user: { ...user, ...response.data },
        });
      }
      
      // Sync i18n language
      const newLang = values.language_preference;
      if (newLang === 'en' || newLang === 'zh') {
        i18n.changeLanguage(newLang);
        localStorage.setItem('ey-language', newLang);
      }
      setThemeMode(values.theme_preference);
      
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch {
      message.error(t('save_error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page" style={{ background: 'transparent' }}>
      <div className="page-inner" style={{ maxWidth: 680 }}>
        <div className="page-head" style={{ marginBottom: 32 }}>
          <h1 className="page-title">{t('account_info')}</h1>
          <p className="page-subtitle" style={{ marginTop: 8 }}>{t('account_info_desc', 'Manage your personal information and preferences.')}</p>
        </div>
        {/* P1-2: Account Info Card — display all user model fields */}
        <Card
          title={
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500 }}>
              {t('account_info')}
            </span>
          }
          styles={{ body: { padding: '32px 32px 36px' } }}
          className="glass-panel hover-lift section-enter"
          style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)' }}
        >
          {/* Avatar + Username header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 32 }}>
            <Avatar
              size={72}
              icon={<UserOutlined />}
              style={{
                background: 'var(--gradient-accent)',
                fontSize: 32,
                color: '#FFFFFF',
                boxShadow: 'var(--shadow-sm), 0 0 24px rgba(var(--accent-rgb), 0.4)',
              }}
            >
              {user?.username?.charAt(0)?.toUpperCase()}
            </Avatar>
            <div>
              <Typography.Text strong style={{ fontSize: 18, color: 'var(--color-text)' }}>
                {user?.username || user?.email}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 13, display: 'block', marginTop: 4 }}>
                {user?.email}
              </Typography.Text>
            </div>
          </div>

          {/* Detail fields in a responsive grid */}
          <Row gutter={[24, 24]}>
            <Col xs={24} sm={12}>
              <div>
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {t('service_line')}
                </Typography.Text>
                <div style={{ fontWeight: 500, fontSize: 14.5, marginTop: 6, color: 'var(--color-text)' }}>
                  {user?.service_line || (
                    <span style={{ color: 'var(--color-text-tertiary)', fontStyle: 'italic', fontSize: 13 }}>
                      {t('field_not_set')}
                    </span>
                  )}
                </div>
              </div>
            </Col>
            <Col xs={24} sm={12}>
              <div>
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {t('office_location')}
                </Typography.Text>
                <div style={{ fontWeight: 500, fontSize: 14.5, marginTop: 6, color: 'var(--color-text)' }}>
                  {user?.office_location || (
                    <span style={{ color: 'var(--color-text-tertiary)', fontStyle: 'italic', fontSize: 13 }}>
                      {t('field_not_set')}
                    </span>
                  )}
                </div>
              </div>
            </Col>
            <Col xs={24} sm={12}>
              <div>
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {t('role_level')}
                </Typography.Text>
                <div style={{ fontWeight: 500, fontSize: 14.5, marginTop: 6, color: 'var(--color-text)' }}>
                  {user?.role_level || (
                    <span style={{ color: 'var(--color-text-tertiary)', fontStyle: 'italic', fontSize: 13 }}>
                      {t('field_not_set')}
                    </span>
                  )}
                </div>
              </div>
            </Col>
            <Col xs={24} sm={12}>
              <div>
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {t('email')}
                </Typography.Text>
                <div style={{ fontWeight: 500, fontSize: 14.5, marginTop: 6, color: 'var(--color-text)' }}>
                  {user?.email || '—'}
                </div>
              </div>
            </Col>
          </Row>
        </Card>

        {/* P1-2: Preferences Card — language preference (editable) */}
        <Card
          title={
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500 }}>
              {t('preferences')}
            </span>
          }
          styles={{ body: { padding: '32px 32px 28px' } }}
          className="glass-panel hover-lift section-enter"
          style={{ borderRadius: 'var(--radius-lg)' }}
        >
          <Form
            layout="vertical"
            initialValues={{
              language_preference: user?.language_preference || 'en',
              theme_preference: user?.theme_preference || 'system',
              default_space: user?.default_space || undefined,
              announcements: user?.notification_preferences?.announcements ?? true,
              quality: user?.notification_preferences?.quality ?? true,
            }}
            onFinish={handleFinish}
          >
            <Form.Item label={t('language_pref')} name="language_preference" style={{ marginBottom: 24 }}>
              <Select size="large" popupClassName="menu-pop-dropdown" style={{ borderRadius: 10 }}>
                <Select.Option value="en">English</Select.Option>
                <Select.Option value="zh">中文</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item label={t('theme')} name="theme_preference">
              <Select options={['system', 'light', 'dark'].map((value) => ({ value, label: value }))} />
            </Form.Item>
            <Form.Item label={t('default_space')} name="default_space">
              <Select allowClear options={spaces.map((space) => ({ value: space.id, label: space.name }))} />
            </Form.Item>
            <Form.Item label={t('notification_announcements')} name="announcements" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item label={t('notification_quality')} name="quality" valuePropName="checked">
              <Switch />
            </Form.Item>

            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" loading={loading} size="large" className="btn-press" 
                icon={saveSuccess ? <CheckOutlined /> : undefined}
                style={{ height: 44, borderRadius: 12, fontWeight: 600, padding: '0 24px', transition: 'all var(--dur) var(--ease-spring)' }}
              >
                {saveSuccess ? t('saved', 'Saved') : t('save_changes')}
              </Button>
            </Form.Item>
          </Form>
        </Card>
        <Card 
          title={<><SafetyCertificateOutlined style={{ marginRight: 8, color: 'var(--accent)' }}/>{t('account_security')}</>} 
          className="glass-panel hover-lift section-enter" 
          style={{ marginTop: 24, borderRadius: 'var(--radius-lg)' }}
        >
          <Button icon={<LockOutlined />} className="btn-press" onClick={() => setPasswordOpen(true)}>{t('change_password')}</Button>
          <Button icon={<SafetyCertificateOutlined />} className="btn-press" style={{ marginLeft: 8 }} onClick={() => setMfaOpen(true)}>
            {user?.mfa_enabled ? t('mfa_manage') : t('mfa_enable')}
          </Button>
          <List
            style={{ marginTop: 20 }}
            dataSource={sessions}
            renderItem={(session) => (
              <List.Item actions={[
                <Button danger type="link" key="revoke" onClick={async () => {
                  await accountApi.revokeSession(session.id);
                  await loadSessions();
                }}>{t('revoke')}</Button>,
              ]}>
                <List.Item.Meta title={session.current ? t('current_session') : session.user_agent || t('unknown_device')}
                  description={`${session.ip_address || '-'} · ${new Date(session.last_seen_at).toLocaleString()}`} />
              </List.Item>
            )}
          />
        </Card>
        <Modal 
          open={passwordOpen} title={t('change_password')} footer={null} onCancel={() => setPasswordOpen(false)}
          styles={{ mask: { backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' } }}
        >
          <Form layout="vertical" onFinish={async (values) => {
            await accountApi.changePassword(values.current, values.next);
            message.success(t('save_success'));
            setPasswordOpen(false);
          }}>
            <Form.Item name="current" label={t('current_password')} rules={[{ required: true }]}><Input.Password /></Form.Item>
            <Form.Item name="next" label={t('new_password')} rules={[{ required: true }, { min: 8 }]}><Input.Password /></Form.Item>
            <Button type="primary" htmlType="submit">{t('save')}</Button>
          </Form>
        </Modal>
        <Modal 
          open={mfaOpen} title={t('mfa_enable')} footer={null} onCancel={() => setMfaOpen(false)}
          styles={{ mask: { backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' } }}
        >
          {!mfaSecret ? (
            <Form layout="vertical" onFinish={async ({ password }) => {
              const { data } = await accountApi.setupMfa(password);
              setMfaSecret(data.secret);
            }}>
              <Form.Item name="password" label={t('current_password')} rules={[{ required: true }]}><Input.Password /></Form.Item>
              <Button htmlType="submit" type="primary">{t('mfa_start')}</Button>
            </Form>
          ) : recoveryCodes.length ? (
            <Typography.Paragraph copyable>{recoveryCodes.join('\n')}</Typography.Paragraph>
          ) : (
            <>
              <Typography.Paragraph copyable>{mfaSecret}</Typography.Paragraph>
              <Form onFinish={async ({ code }) => {
                const { data } = await accountApi.confirmMfa(code);
                setRecoveryCodes(data.recovery_codes);
              }}>
                <Form.Item name="code" rules={[{ required: true }]}><Input autoComplete="one-time-code" /></Form.Item>
                <Button htmlType="submit" type="primary">{t('mfa_confirm')}</Button>
              </Form>
            </>
          )}
        </Modal>
      </div>
    </div>
  );
}
