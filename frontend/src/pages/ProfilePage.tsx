import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { Card, Form, Select, Button, message, Typography, Avatar, Divider, Row, Col } from 'antd';
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
    <div className="page"><div className="page-inner" style={{ maxWidth: 680 }}>
      <div className="page-head">
        <h1 className="page-title">{t('account_info')}</h1>
      </div>
      {/* P1-2: Account Info Card — display all user model fields */}
      <Card
        title={
          <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500 }}>
            {t('account_info')}
          </span>
        }
        style={{ marginBottom: 16 }}
      >
        {/* Avatar + Username header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <Avatar
            size={64}
            icon={<UserOutlined />}
            style={{
              background: 'var(--gradient-accent)',
              fontSize: 28,
              color: '#FFFFFF',
            }}
          >
            {user?.username?.charAt(0)?.toUpperCase()}
          </Avatar>
          <div>
            <Typography.Text strong style={{ fontSize: 16 }}>
              {user?.username || user?.email}
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
              {user?.email}
            </Typography.Text>
          </div>
        </div>

        <Divider style={{ margin: '0 0 16px' }} />

        {/* Detail fields in a responsive grid */}
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12}>
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 500 }}>
                {t('service_line')}
              </Typography.Text>
              <div style={{ fontWeight: 500, fontSize: 14, marginTop: 2 }}>
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
              <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 500 }}>
                {t('office_location')}
              </Typography.Text>
              <div style={{ fontWeight: 500, fontSize: 14, marginTop: 2 }}>
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
              <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 500 }}>
                {t('role_level')}
              </Typography.Text>
              <div style={{ fontWeight: 500, fontSize: 14, marginTop: 2 }}>
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
              <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 500 }}>
                {t('email')}
              </Typography.Text>
              <div style={{ fontWeight: 500, fontSize: 14, marginTop: 2 }}>
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
        style={{ marginBottom: 16 }}
      >
        <Form
          layout="vertical"
          initialValues={{
            language_preference: user?.language_preference || 'en',
          }}
          onFinish={handleFinish}
        >
          <Form.Item label={t('language_pref')} name="language_preference">
            <Select>
              <Select.Option value="en">English</Select.Option>
              <Select.Option value="zh">中文</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              {t('save_changes')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div></div>
  );
}
