import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Checkbox, Input, Popconfirm, Space, message } from 'antd';
import { useParams } from 'react-router-dom';

import { spacesApi } from '../../api/spaces';
import { PageHeader, Surface } from '../../design/primitives';
import { useCapabilities } from '../../auth/CapabilityProvider';

export default function WorkspaceLifecyclePage() {
  const { t } = useTranslation('common');
  const { spaceId = '' } = useParams<{ spaceId: string }>();
  const { refresh } = useCapabilities();
  const [cloneName, setCloneName] = useState('');
  const [cloneCode, setCloneCode] = useState('');
  const [copyDocuments, setCopyDocuments] = useState(false);
  const [businessLine, setBusinessLine] = useState('');
  const [ownerUser, setOwnerUser] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState(false);

  const run = async (key: string, operation: () => Promise<unknown>) => {
    setBusy(key); setError(false);
    try { await operation(); await refresh(); message.success(t('lifecycle_success')); }
    catch { setError(true); }
    finally { setBusy(''); }
  };

  return (
    <div className="page section-enter">
      <PageHeader title={t('workspace_lifecycle')} description={t('workspace_lifecycle_description')} />
      <Surface style={{ display: 'grid', gap: 24 }}>
        {error && <Alert showIcon type="error" message={t('lifecycle_failed')} />}
        <Space wrap>
          <Popconfirm title={t('confirm_archive_workspace')} onConfirm={() => run('archive', () => spacesApi.archive(spaceId))}>
            <Button danger loading={busy === 'archive'}>{t('archive')}</Button>
          </Popconfirm>
          <Button loading={busy === 'restore'} onClick={() => run('restore', () => spacesApi.restore(spaceId))}>{t('restore')}</Button>
        </Space>
        <div style={{ display: 'grid', gap: 8 }}>
          <strong>{t('clone_workspace')}</strong>
          <Input value={cloneName} onChange={(event) => setCloneName(event.target.value)} placeholder={t('space_name')} />
          <Input value={cloneCode} onChange={(event) => setCloneCode(event.target.value)} placeholder={t('space_code')} />
          <Checkbox checked={copyDocuments} onChange={(event) => setCopyDocuments(event.target.checked)}>{t('copy_documents')}</Checkbox>
          <Button disabled={!cloneName || !cloneCode} loading={busy === 'clone'} onClick={() => run('clone', () => spacesApi.clone(spaceId, { name: cloneName, code: cloneCode, copy_documents: copyDocuments }))}>{t('clone_workspace')}</Button>
        </div>
        <div style={{ display: 'grid', gap: 8 }}>
          <strong>{t('transfer_business_line')}</strong>
          <Input value={businessLine} onChange={(event) => setBusinessLine(event.target.value)} placeholder={t('business_line_id')} />
          <Popconfirm title={t('confirm_transfer_workspace')} onConfirm={() => run('transfer', () => spacesApi.transfer(spaceId, businessLine))}>
            <Button disabled={!businessLine} loading={busy === 'transfer'}>{t('transfer')}</Button>
          </Popconfirm>
        </div>
        <div style={{ display: 'grid', gap: 8 }}>
          <strong>{t('transfer_owner')}</strong>
          <Input value={ownerUser} onChange={(event) => setOwnerUser(event.target.value)} placeholder={t('user_id')} />
          <Popconfirm title={t('confirm_transfer_owner')} onConfirm={() => run('owner', () => spacesApi.transferOwner(spaceId, ownerUser))}>
            <Button danger disabled={!ownerUser} loading={busy === 'owner'}>{t('transfer_owner')}</Button>
          </Popconfirm>
        </div>
      </Surface>
    </div>
  );
}
