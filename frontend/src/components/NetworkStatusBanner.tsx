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
        // V4.2 UI-V4.2-012: Removed inline 'slideDown' animation reference.
        // @keyframes slideDown is defined in globals.css, but inline style
        // animation references may fail under strict CSP (no unsafe-inline).
        // antd Alert has its own built-in entrance animation, so this was
        // redundant dead code. Now relies on antd's internal animation.
        // [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-012]
      }}
    />
  );
}
