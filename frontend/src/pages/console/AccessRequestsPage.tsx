import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Input, List, Modal, Tag } from 'antd';
import { useParams } from 'react-router-dom';

import { scopedConsoleApi, type SpaceAccessRequest } from '../../api/scopedConsole';
import { getRateLimitDetails, isAbortError, withRequestSignal } from '../../api/client';
import { EmptyState, PageHeader, Surface } from '../../design/primitives';

export default function AccessRequestsPage() {
  const { t } = useTranslation('common');
  const { spaceId } = useParams<{ spaceId: string }>();
  const [requests, setRequests] = useState<SpaceAccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);
  const requestSequence = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState('');
  const [rejecting, setRejecting] = useState<SpaceAccessRequest | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    if (!spaceId) { setLoading(false); return; }
    setLoading(true); setError(null);
    try {
      setRequests(await withRequestSignal(
        controller.signal,
        () => scopedConsoleApi.accessRequests(spaceId),
      ));
    }
    catch (reason: unknown) {
      if (isAbortError(reason) || controller.signal.aborted || sequence !== requestSequence.current) return;
      const rateLimit = getRateLimitDetails(reason);
      setError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    }
    finally {
      if (sequence === requestSequence.current && !controller.signal.aborted) setLoading(false);
    }
  }, [spaceId]);
  useEffect(() => {
    void load();
    return () => {
      requestSequence.current += 1;
      controllerRef.current?.abort();
    };
  }, [load]);

  const approve = async (accessRequest: SpaceAccessRequest) => {
    if (!spaceId) return;
    setBusy(accessRequest.id);
    try { await scopedConsoleApi.approveAccessRequest(spaceId, accessRequest); await load(); }
    catch (reason: unknown) {
      const rateLimit = getRateLimitDetails(reason);
      setError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    }
    finally { setBusy(''); }
  };

  const reject = async () => {
    if (!spaceId || !rejecting || !rejectionReason.trim()) return;
    setBusy(rejecting.id);
    try {
      await scopedConsoleApi.rejectAccessRequest(spaceId, rejecting, rejectionReason.trim());
      setRejecting(null); setRejectionReason(''); await load();
    } catch (reason: unknown) {
      const rateLimit = getRateLimitDetails(reason);
      setError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    }
    finally { setBusy(''); }
  };

  return (
    <div className="page section-enter">
      <PageHeader title={t('access_requests')} description={t('access_requests_description')} />
      <Surface>
        {loading ? <p role="status">{t('loading')}</p> : error ? (
          <Alert
            type="error"
            showIcon
            message={error.code === 'rate_limited'
              ? `${t('rate_limited') || 'Too many requests'}${error.retryAfterSeconds == null ? '' : ` — retry in ${error.retryAfterSeconds}s`}`
              : t('load_error')}
            action={<Button onClick={() => void load()}>{t('error_retry')}</Button>}
          />
        ) : requests.length === 0 ? <EmptyState icon="K" title={t('access_requests_empty')} /> : (
          <List dataSource={requests} renderItem={(request) => (
            <List.Item
              actions={request.status === 'pending' ? [
                <Button key="approve" type="primary" loading={busy === request.id} onClick={() => approve(request)}>{t('approve')}</Button>,
                <Button key="reject" danger onClick={() => setRejecting(request)}>{t('reject')}</Button>,
              ] : undefined}
            >
              <List.Item.Meta
                title={<>{request.requester_uuid} <Tag bordered={false}>{request.status}</Tag></>}
                description={request.status === 'rejected' && request.decision_reason_code
                  ? `${request.reason || t('access_request_no_reason')} · ${request.decision_reason_code}`
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
