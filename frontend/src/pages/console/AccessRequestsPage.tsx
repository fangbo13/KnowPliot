import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Input, List, Modal, Tag } from 'antd';
import { useParams } from 'react-router-dom';

import { scopedConsoleApi, type SpaceAccessRequest } from '../../api/scopedConsole';
import { EmptyState, PageHeader, Surface } from '../../design/primitives';

export default function AccessRequestsPage() {
  const { t } = useTranslation('common');
  const { spaceId } = useParams<{ spaceId: string }>();
  const [requests, setRequests] = useState<SpaceAccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState('');
  const [rejecting, setRejecting] = useState<SpaceAccessRequest | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');

  const load = useCallback(async () => {
    if (!spaceId) { setLoading(false); return; }
    setLoading(true); setError(false);
    try { setRequests(await scopedConsoleApi.accessRequests(spaceId)); }
    catch { setError(true); }
    finally { setLoading(false); }
  }, [spaceId]);
  useEffect(() => { void load(); }, [load]);

  const approve = async (requestId: string) => {
    if (!spaceId) return;
    setBusy(requestId);
    try { await scopedConsoleApi.approveAccessRequest(spaceId, requestId); await load(); }
    catch { setError(true); }
    finally { setBusy(''); }
  };

  const reject = async () => {
    if (!spaceId || !rejecting || !rejectionReason.trim()) return;
    setBusy(rejecting.id);
    try {
      await scopedConsoleApi.rejectAccessRequest(spaceId, rejecting.id, rejectionReason.trim());
      setRejecting(null); setRejectionReason(''); await load();
    } catch { setError(true); }
    finally { setBusy(''); }
  };

  return (
    <div className="page section-enter">
      <PageHeader title={t('access_requests')} description={t('access_requests_description')} />
      <Surface>
        {loading ? <p role="status">{t('loading')}</p> : error ? (
          <Alert type="error" showIcon message={t('load_error')} action={<Button onClick={load}>{t('error_retry')}</Button>} />
        ) : requests.length === 0 ? <EmptyState icon="K" title={t('access_requests_empty')} /> : (
          <List dataSource={requests} renderItem={(request) => (
            <List.Item
              actions={request.status === 'pending' ? [
                <Button key="approve" type="primary" loading={busy === request.id} onClick={() => approve(request.id)}>{t('approve')}</Button>,
                <Button key="reject" danger onClick={() => setRejecting(request)}>{t('reject')}</Button>,
              ] : undefined}
            >
              <List.Item.Meta
                title={<>{request.user_email ?? request.user} <Tag bordered={false}>{request.status}</Tag></>}
                description={request.status === 'rejected' && request.rejection_reason
                  ? `${request.reason || t('access_request_no_reason')} · ${request.rejection_reason}`
                  : request.reason || t('access_request_no_reason')}
              />
            </List.Item>
          )} />
        )}
      </Surface>
      <Modal
        open={Boolean(rejecting)}
        title={t('reject_access_request')}
        okText={t('reject')}
        okButtonProps={{ danger: true, disabled: !rejectionReason.trim(), loading: busy === rejecting?.id }}
        onOk={reject}
        onCancel={() => { setRejecting(null); setRejectionReason(''); }}
      >
        <Input.TextArea
          value={rejectionReason}
          onChange={(event) => setRejectionReason(event.target.value)}
          placeholder={t('rejection_reason')}
          rows={4}
          maxLength={2000}
        />
      </Modal>
    </div>
  );
}
