import { useState, useEffect } from 'react';
import { WifiOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

/** Shows a warm offline bar when the browser loses connectivity. */
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
    <div className="net-banner" role="status">
      <WifiOutlined />
      {t('offline_banner')}
    </div>
  );
}
