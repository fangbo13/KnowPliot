import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { Card, Form, Input, Select, Button, message, Typography } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';
import apiClient from '../api/client';
import i18n from '../i18n';

const { Text } = Typography;

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
    <div style={{ maxWidth: 'min(680px, 100%)', width: '100%', margin: '0 auto' }}>
      <Card
        title={
          <span style={{ fontFamily: "'Calistoga', Georgia, serif", fontWeight: 400 }}>
            {t('profile_settings')}
          </span>
        }
        style={{ marginBottom: 16 }}
      >
        <Form
          layout="vertical"
          initialValues={{
            email: user?.email,
            username: user?.username,
            language_preference: user?.language_preference || 'en',
          }}
          onFinish={handleFinish}
        >
          <Form.Item label={t('email')} name="email">
            <Input
              disabled
              prefix={<LockOutlined style={{ color: 'var(--color-text-tertiary)' }} />}
              style={{ background: 'var(--color-bg-elevated)', cursor: 'not-allowed' }}
            />
            <div style={{ marginTop: 4 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('email_readonly_hint')}
              </Text>
            </div>
          </Form.Item>

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
    </div>
  );
}
