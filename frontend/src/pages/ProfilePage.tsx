import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { Card, Form, Input, Select, Button, message, Segmented } from 'antd';
import { SunOutlined, MoonOutlined, DesktopOutlined } from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';
import { useTheme } from '../hooks/useTheme';
import apiClient from '../api/client';
import i18n from '../i18n';

export default function ProfilePage() {
  const { t } = useTranslation('common');
  const { user, login } = useAuth();
  const { mode, setThemeMode } = useTheme();
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
            <Input disabled />
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

      <Card
        title={
          <span style={{ fontFamily: "'Calistoga', Georgia, serif", fontWeight: 400 }}>
            {t('appearance')}
          </span>
        }
      >
        <p style={{ marginBottom: 12, color: 'var(--color-text-secondary)' }}>
          {t('theme_desc')}
        </p>
        <Segmented
          size="large"
          value={mode}
          onChange={(val) => setThemeMode(val as 'light' | 'dark' | 'system')}
          options={[
            { label: t('light'), value: 'light', icon: <SunOutlined /> },
            { label: t('dark'), value: 'dark', icon: <MoonOutlined /> },
            { label: t('system'), value: 'system', icon: <DesktopOutlined /> },
          ]}
        />
      </Card>
    </div>
  );
}
