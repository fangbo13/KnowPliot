import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Input, List, Select, Tag } from 'antd';

import { spacesApi, type KnowledgeSpace } from '../api/spaces';
import { EmptyState, PageHeader, Surface } from '../design/primitives';

export default function SpaceDiscoveryPage() {
  const { t } = useTranslation('common');
  const [spaces, setSpaces] = useState<KnowledgeSpace[]>([]);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [roles, setRoles] = useState<Record<string, 'member' | 'guest'>>({});
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(false);
    try { setSpaces(await spacesApi.discoverable()); }
    catch { setError(true); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const requestAccess = async (space: KnowledgeSpace) => {
    setStatuses((current) => ({ ...current, [space.id]: 'submitting' }));
    try {
      const request = await spacesApi.requestAccess(space.id, {
        reason: reasons[space.id] ?? '',
        role: roles[space.id] ?? 'member',
      });
      setStatuses((current) => ({ ...current, [space.id]: request.status }));
    } catch {
      setStatuses((current) => ({ ...current, [space.id]: 'failed' }));
    }
  };

  return (
    <div className="page section-enter">
      <PageHeader title={t('space_discovery')} description={t('space_discovery_description')} />
      <Surface>
        {loading ? <p role="status">{t('loading')}</p> : error ? (
          <Alert type="error" showIcon message={t('load_error')} action={<Button onClick={load}>{t('error_retry')}</Button>} />
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
                </div>
              </List.Item>
            )}
          />
        )}
      </Surface>
    </div>
  );
}
