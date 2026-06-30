/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { Card, Form, Select, Button, message, Typography, Avatar, Row, Col } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';
import apiClient from '../api/client';
import i18n from '../i18n';

export default function ProfilePage() {
  const { t } = useTranslation('common');
  const { user, login } = useAuth();
  const [loading, setLoading] = useState(false);

  const handleFinish = async (values: { language_preference: string }) => {
    setLoading(true);
    try {
      const response = await apiClient.patch('/auth/me/preferences/', values);
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
        </div>
        {/* P1-2: Account Info Card — display all user model fields */}
        <Card
          title={
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500 }}>
              {t('account_info')}
            </span>
          }
          styles={{ body: { padding: '32px 32px 36px' } }}
          style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}
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
                boxShadow: 'var(--shadow-sm)',
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
          style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}
        >
          <Form
            layout="vertical"
            initialValues={{
              language_preference: user?.language_preference || 'en',
            }}
            onFinish={handleFinish}
          >
            <Form.Item label={t('language_pref')} name="language_preference" style={{ marginBottom: 24 }}>
              <Select size="large" popupClassName="menu-pop-dropdown" style={{ borderRadius: 10 }}>
                <Select.Option value="en">English</Select.Option>
                <Select.Option value="zh">中文</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" loading={loading} size="large" style={{ height: 44, borderRadius: 12, fontWeight: 600, padding: '0 24px', transition: 'all var(--dur) var(--ease-spring)' }}>
                {t('save_changes')}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    </div>
  );
}
