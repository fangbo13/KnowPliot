import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Empty, Popconfirm, Space, Tag, Typography, message } from 'antd';
import { useTranslation } from 'react-i18next';

import { spacesApi, type PendingOwnershipTransfer } from '../api/spaces';

export default function OwnershipTransfersPage() {
  const { t } = useTranslation('common');
  const [transfers, setTransfers] = useState<PendingOwnershipTransfer[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTransfers(await spacesApi.pendingOwnershipTransfers());
    } catch {
      message.error(t('ownership_transfers_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { void load(); }, [load]);

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
    } catch {
      message.error(t('ownership_transfer_response_failed'));
      await load();
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
