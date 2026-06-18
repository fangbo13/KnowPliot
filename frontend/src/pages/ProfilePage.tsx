import { Card, Form, Input, Select, Button, Typography } from 'antd';
import { useAuth } from '../auth/AuthProvider';

const { Title } = Typography;

export default function ProfilePage() {
  const { user } = useAuth();

  return (
    <Card>
      <Title level={4}>Profile Settings</Title>
      <Form
        layout="vertical"
        initialValues={{
          email: user?.email,
          username: user?.username,
          language_preference: user?.language_preference || 'en',
        }}
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
          <Button type="primary" htmlType="submit">
            Save Changes
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
