import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Input, List, Select, Tag } from 'antd';

import { spacesApi, type KnowledgeSpace } from '../api/spaces';
import { getRateLimitDetails, isAbortError } from '../api/client';
import { EmptyState, PageHeader, Surface } from '../design/primitives';

export default function SpaceDiscoveryPage() {
  const { t } = useTranslation('common');
  const [spaces, setSpaces] = useState<KnowledgeSpace[]>([]);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [roles, setRoles] = useState<Record<string, 'member' | 'guest'>>({});
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);
  const requestSequence = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const accessControllers = useRef(new Map<string, AbortController>());

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(null);
    try { setSpaces(await spacesApi.discoverable(controller.signal)); }
    catch (error: unknown) {
      if (isAbortError(error) || controller.signal.aborted || sequence !== requestSequence.current) return;
      const rateLimit = getRateLimitDetails(error);
      setError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    }
    finally {
      if (sequence === requestSequence.current && !controller.signal.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
    return () => {
      requestSequence.current += 1;
      controllerRef.current?.abort();
      for (const controller of accessControllers.current.values()) controller.abort();
      accessControllers.current.clear();
    };
  }, [load]);

  const requestAccess = async (space: KnowledgeSpace) => {
    accessControllers.current.get(space.id)?.abort();
    const controller = new AbortController();
    accessControllers.current.set(space.id, controller);
    setStatuses((current) => ({ ...current, [space.id]: 'submitting' }));
    try {
      const request = await spacesApi.requestAccess(space.id, {
        reason: reasons[space.id] ?? '',
        role: roles[space.id] ?? 'member',
      }, controller.signal);
      if (controller.signal.aborted) return;
      setStatuses((current) => ({ ...current, [space.id]: request.status }));
    } catch (error: unknown) {
      if (isAbortError(error) || controller.signal.aborted) return;
      const rateLimit = getRateLimitDetails(error);
      setStatuses((current) => ({ ...current, [space.id]: rateLimit ? 'rate_limited' : 'failed' }));
    } finally {
      if (accessControllers.current.get(space.id) === controller) accessControllers.current.delete(space.id);
    }
  };

  return (
    <div className="page section-enter">
      <PageHeader title={t('space_discovery')} description={t('space_discovery_description')} />
      <Surface>
        {loading ? <p role="status">{t('loading')}</p> : error ? (
          <Alert
            type="error"
            showIcon
            message={error.code === 'rate_limited'
              ? `${t('rate_limited') || 'Too many requests'}${error.retryAfterSeconds == null ? '' : ` — ${t('retry_after_seconds', { seconds: error.retryAfterSeconds }) || `retry in ${error.retryAfterSeconds}s`}`}`
              : t('load_error')}
            action={<Button onClick={() => void load()}>{t('error_retry')}</Button>}
          />
        ) : spaces.length === 0 ? <EmptyState icon="K" title={t('space_discovery_empty')} /> : (
          <List
            dataSource={spaces}
            renderItem={(space) => (
              <List.Item>
                <div style={{ width: '100%', display: 'grid', gap: 12 }}>
                  <div>
                    <strong>{space.name}</strong> <Tag bordered={false}>{space.visibility}</Tag>
                    <div style={{ color: 'var(--color-text-secondary)', marginTop: 4 }}>{space.description}</div>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    <Input.TextArea
                      value={reasons[space.id] ?? ''}
                      onChange={(event) => setReasons((current) => ({ ...current, [space.id]: event.target.value }))}
                      placeholder={t('space_access_reason')}
                      autoSize={{ minRows: 1, maxRows: 3 }}
                      style={{ flex: '1 1 280px' }}
                    />
                    <Select
                      value={roles[space.id] ?? 'member'}
                      onChange={(role) => setRoles((current) => ({ ...current, [space.id]: role }))}
                      options={[{ value: 'member', label: t('role_member') }, { value: 'guest', label: t('role_guest') }]}
                      style={{ width: 130 }}
                    />
                    <Button
                      type="primary"
                      loading={statuses[space.id] === 'submitting'}
                      disabled={statuses[space.id] === 'pending'}
                      onClick={() => requestAccess(space)}
                    >
                      {statuses[space.id] === 'pending' ? t('space_access_pending') : t('space_access_request')}
                    </Button>
                  </div>
                  {statuses[space.id] === 'failed' && <Alert type="error" message={t('space_access_failed')} showIcon />}
                  {statuses[space.id] === 'rate_limited' && <Alert type="warning" message={t('rate_limited') || 'Too many requests — please retry shortly'} showIcon />}
                </div>
              </List.Item>
            )}
          />
        )}
      </Surface>
    </div>
  );
}
