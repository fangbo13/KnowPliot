import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Empty, Popconfirm, Space, Tag, Typography, message } from 'antd';
import { useTranslation } from 'react-i18next';

import { spacesApi, type PendingOwnershipTransfer } from '../api/spaces';
import { getRateLimitDetails, isAbortError } from '../api/client';

export default function OwnershipTransfersPage() {
  const { t } = useTranslation('common');
  const [transfers, setTransfers] = useState<PendingOwnershipTransfer[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);
  const requestSequence = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setLoadError(null);
    try {
      setTransfers(await spacesApi.pendingOwnershipTransfers(controller.signal));
    } catch (error: unknown) {
      if (isAbortError(error) || controller.signal.aborted || sequence !== requestSequence.current) return;
      const rateLimit = getRateLimitDetails(error);
      setLoadError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    } finally {
      if (sequence === requestSequence.current && !controller.signal.aborted) setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
    return () => {
      requestSequence.current += 1;
      controllerRef.current?.abort();
    };
  }, [load]);

  const respond = async (transfer: PendingOwnershipTransfer, response: 'accept' | 'decline') => {
    setBusyId(transfer.id);
    try {
      if (response === 'accept') {
        await spacesApi.acceptOwnershipTransfer(transfer.space_id, transfer.id);
      } else {
        await spacesApi.declineOwnershipTransfer(transfer.space_id, transfer.id);
      }
      message.success(response === 'accept' ? t('ownership_transfer_accepted') : t('ownership_transfer_declined'));
      await load();
    } catch (error: unknown) {
      if (!isAbortError(error)) {
        const rateLimit = getRateLimitDetails(error);
        message.error(rateLimit
          ? `${t('rate_limited') || 'Too many requests'}${rateLimit.retryAfterSeconds == null ? '' : ` — retry in ${rateLimit.retryAfterSeconds}s`}`
          : t('ownership_transfer_response_failed'));
      }
      if (!isAbortError(error)) await load();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="page section-enter">
      <div className="page-inner">
        <div className="page-head">
          <h1 className="page-title">{t('ownership_transfers_title')}</h1>
          <p style={{ color: 'var(--color-text-secondary)' }}>{t('ownership_transfers_description')}</p>
        </div>
        {loadError && (
          <Alert
            style={{ marginBottom: 16 }}
            type="error"
            showIcon
            message={loadError.code === 'rate_limited'
              ? `${t('rate_limited') || 'Too many requests'}${loadError.retryAfterSeconds == null ? '' : ` — retry in ${loadError.retryAfterSeconds}s`}`
              : t('ownership_transfers_load_failed')}
            action={<Button onClick={() => void load()}>{t('error_retry') || 'Retry'}</Button>}
          />
        )}
        <Card className="glass-panel" loading={loading} styles={{ body: { padding: 20 } }}>
          {transfers.length === 0 ? <Empty description={t('ownership_transfers_empty')} /> : (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              {transfers.map((transfer) => (
                <Card key={transfer.id} size="small" style={{ borderRadius: 12 }}>
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Typography.Text strong>{transfer.space.display_name}</Typography.Text>
                      <Tag>{transfer.space.status}</Tag>
                    </Space>
                    <Typography.Text type="secondary">{t('ownership_transfer_acceptance_notice')}</Typography.Text>
                    <Space>
                      <Popconfirm
                        title={t('ownership_transfer_accept_confirm')}
                        onConfirm={() => void respond(transfer, 'accept')}
                      >
                        <Button type="primary" loading={busyId === transfer.id}>{t('accept')}</Button>
                      </Popconfirm>
                      <Popconfirm
                        title={t('ownership_transfer_decline_confirm')}
                        onConfirm={() => void respond(transfer, 'decline')}
                      >
                        <Button danger loading={busyId === transfer.id}>{t('decline')}</Button>
                      </Popconfirm>
                    </Space>
                  </Space>
                </Card>
              ))}
            </Space>
          )}
          <Alert
            style={{ marginTop: 16 }}
            type="info"
            showIcon
            message={t('ownership_transfer_acceptance_hint')}
          />
        </Card>
      </div>
    </div>
  );
}
