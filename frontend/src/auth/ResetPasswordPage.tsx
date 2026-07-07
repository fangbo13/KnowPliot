import { useState } from 'react';
import { Alert, Button, Card, Form, Input } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { accountApi } from '../api/account';

export default function ResetPasswordPage() {
  const { t } = useTranslation('common');
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async ({ password }: { password: string }) => {
    setLoading(true);
    try {
      await accountApi.confirmPasswordReset(
        params.get('uid') || '',
        params.get('token') || '',
        password,
      );
      navigate('/login', { replace: true });
    } catch {
      setError(t('password_reset_invalid'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <Card title={t('password_reset_title')} style={{ width: '100%', maxWidth: 440 }}>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
        <Form layout="vertical" onFinish={submit}>
          <Form.Item name="password" label={t('new_password')} rules={[{ required: true }, { min: 8 }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            {t('password_reset_submit')}
          </Button>
        </Form>
      </Card>
    </div>
  );
}
