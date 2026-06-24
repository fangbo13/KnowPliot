import { useState, useEffect } from 'react';
import { Alert } from 'antd';
import { WifiOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

/**
 * NetworkStatusBanner (P0-4) — shows a red alert bar when the browser is offline.
 * Listens to navigator.onLine and online/offline events.
 */
export default function NetworkStatusBanner() {
  const { t } = useTranslation('common');
  const [isOnline, setIsOnline] = useState(() => navigator.onLine);

  useEffect(() => {
    const onOnline = () => setIsOnline(true);
    const onOffline = () => setIsOnline(false);

    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);

    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  if (isOnline) return null;

  return (
    <Alert
      message={t('offline_banner')}
      type="error"
      showIcon
      icon={<WifiOutlined />}
      style={{
        borderRadius: 8,
        marginBottom: 8,
        animation: 'slideDown 0.3s ease-out',
      }}
    />
  );
}
