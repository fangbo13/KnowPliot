/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { Card, Form, Select, Button, message, Typography, Avatar, Row, Col, Input, Modal, Switch, Tag } from 'antd';
import { UserOutlined, SafetyCertificateOutlined, LockOutlined, CheckOutlined, EnvironmentOutlined } from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';
import apiClient from '../api/client';
import i18n from '../i18n';
import { accountApi } from '../api/account';
import { useSpaceStore } from '../store/spaceStore';
import { useTheme } from '../hooks/useTheme';

// EY China major office locations — 安永各大所地址
const EY_OFFICE_LOCATIONS = [
  '北京', '上海', '广州', '深圳', '成都', '武汉', '杭州', '南京',
  '青岛', '大连', '厦门', '天津', '苏州', '西安', '重庆', '济南',
  '沈阳', '长沙', '郑州', '合肥', '昆明', '海口', '香港', '澳门',
];

export default function ProfilePage() {
  const { t } = useTranslation('common');
  const { user, login } = useAuth();
  const [loading, setLoading] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const spaces = useSpaceStore((state) => state.spaces);
  const { setThemeMode } = useTheme();
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [mfaOpen, setMfaOpen] = useState(false);
  const [mfaSecret, setMfaSecret] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  // office_location is in Card 1 (outside the preferences Form), so it is
  // managed as independent state and manually included in the API call.
  const [officeLocation, setOfficeLocation] = useState(user?.office_location || '');

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
        office_location: officeLocation || null,
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
          user: { ...user, ...response.data, office_location: officeLocation },
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
    <div className="page kp-profile-page">
      <div className="page-inner kp-profile-page__inner" style={{ maxWidth: 820 }}>
        <div className="page-head" style={{ marginBottom: 20 }}>
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
          styles={{ body: { padding: '24px 28px 28px' } }}
          className="glass-panel hover-lift section-enter kp-profile-card kp-profile-card--identity"
          style={{ marginBottom: 16, borderRadius: 'var(--radius-lg)' }}
        >
          {/* Avatar + Username header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
            <Avatar
              size={72}
              icon={<UserOutlined />}
              style={{
                background: 'var(--gradient-accent)',
                fontSize: 32,
                color: 'var(--color-text-on-accent)',
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
          <Row gutter={[20, 16]}>
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
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <EnvironmentOutlined /> {t('office_location')} <span style={{ color: 'var(--color-error)' }}>*</span>
                </Typography.Text>
                <Select
                  size="middle"
                  showSearch
                  value={officeLocation || undefined}
                  onChange={(val) => setOfficeLocation(val)}
                  placeholder={t('office_location_placeholder', '请选择办公地点')}
                  style={{ marginTop: 6, borderRadius: 8, width: '100%' }}
                  popupClassName="menu-pop-dropdown"
                >
                  {EY_OFFICE_LOCATIONS.map((loc) => (
                    <Select.Option key={loc} value={loc}>{loc}</Select.Option>
                  ))}
                </Select>
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
          styles={{ body: { padding: '24px 28px 20px' } }}
          className="glass-panel hover-lift section-enter kp-profile-card kp-profile-card--preferences"
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
            <Row gutter={[16, 12]}>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label={t('language_pref')} name="language_preference" style={{ marginBottom: 12 }}>
                  <Select size="middle" popupClassName="menu-pop-dropdown" style={{ borderRadius: 10 }}>
                    <Select.Option value="en">English</Select.Option>
                    <Select.Option value="zh">中文</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label={t('theme')} name="theme_preference" style={{ marginBottom: 12 }}>
                  <Select size="middle" options={[
                    { value: 'system', label: t('system') },
                    { value: 'light', label: t('light') },
                    { value: 'dark', label: t('dark') },
                  ]} style={{ borderRadius: 10 }} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label={t('default_space')} name="default_space" style={{ marginBottom: 12 }}>
                  <Select size="middle" allowClear options={spaces.map((space) => ({ value: space.id, label: space.name }))} style={{ borderRadius: 10 }} />
                </Form.Item>
              </Col>
              <Col xs={24} lg={24} className="kp-profile-notifications-col">
                <div className="kp-profile-notifications">
                  <Form.Item label={t('notification_announcements')} name="announcements" valuePropName="checked" style={{ marginBottom: 0 }}>
                    <Switch size="small" />
                  </Form.Item>
                  <Form.Item label={t('notification_quality')} name="quality" valuePropName="checked" style={{ marginBottom: 0 }}>
                    <Switch size="small" />
                  </Form.Item>
                </div>
              </Col>
            </Row>

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
          className="glass-panel hover-lift section-enter kp-profile-card kp-profile-card--security"
          style={{ marginTop: 16, borderRadius: 'var(--radius-lg)' }}
        >
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
            <Button icon={<LockOutlined />} className="btn-press" onClick={() => setPasswordOpen(true)}>{t('change_password')}</Button>
            <Button icon={<SafetyCertificateOutlined />} className="btn-press" style={{ marginLeft: 0 }} disabled title={t('mfa_comingsoon_desc', 'MFA功能即将上线')}>
              {t('mfa_enable')} <Tag color="orange" style={{ marginLeft: 4, fontSize: 11 }}>{t('coming_soon', '暂未上线')}</Tag>
            </Button>
          </div>
          <div style={{ padding: '12px 16px', background: 'var(--accent-soft)', borderRadius: 10, border: '1px solid var(--color-border-secondary)' }}>
            <Typography.Text style={{ color: 'var(--color-text)', fontSize: 13.5, lineHeight: 1.6 }}>
              <SafetyCertificateOutlined style={{ color: 'var(--accent)', marginRight: 6 }} />
              {t('security_assurance_msg', 'KnowPilot 将持续保障您的账户安全。我们采用企业级加密和多重防护机制，确保您的数据和隐私得到充分保护。')}
            </Typography.Text>
          </div>
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
