import { useState } from 'react';
import { Card, Form, Input, Select, Button, Typography, message, Segmented } from 'antd';
import { SunOutlined, MoonOutlined, DesktopOutlined } from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';
import { useTheme } from '../hooks/useTheme';
import apiClient from '../api/client';

const { Title } = Typography;

export default function ProfilePage() {
  const { user, login } = useAuth();
  const { mode, setThemeMode } = useTheme();
  const [loading, setLoading] = useState(false);

  const handleFinish = async (values: { language_preference: string }) => {
    setLoading(true);
    try {
      const response = await apiClient.patch('/auth/me/preferences/', values);
      message.success('Profile updated successfully');
      if (user) {
        const saved = localStorage.getItem('ey-auth');
        const token = saved ? JSON.parse(saved).token : null;
        login({
          token,
          user: { ...user, ...response.data },
        });
      }
    } catch {
      message.error('Failed to update profile');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 'min(680px, 100%)', width: '100%', margin: '0 auto' }}>
      <Card style={{ marginBottom: 16 }}>
        <Title level={4}>Profile Settings</Title>
        <Form
          layout="vertical"
          initialValues={{
            email: user?.email,
            username: user?.username,
            language_preference: user?.language_preference || 'en',
          }}
          onFinish={handleFinish}
        >
          <Form.Item label="Email" name="email">
            <Input disabled />
          </Form.Item>

          <Form.Item label="Language Preference" name="language_preference">
            <Select>
              <Select.Option value="en">English</Select.Option>
              <Select.Option value="zh">中文</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              Save Changes
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card>
        <Title level={4}>Appearance</Title>
        <p style={{ marginBottom: 12, color: 'var(--color-text-secondary)' }}>
          Choose your preferred theme. The dark mode applies to all pages.
        </p>
        <Segmented
          size="large"
          value={mode}
          onChange={(val) => setThemeMode(val as 'light' | 'dark' | 'system')}
          options={[
            { label: 'Light', value: 'light', icon: <SunOutlined /> },
            { label: 'Dark', value: 'dark', icon: <MoonOutlined /> },
            { label: 'System', value: 'system', icon: <DesktopOutlined /> },
          ]}
        />
      </Card>
    </div>
  );
}
