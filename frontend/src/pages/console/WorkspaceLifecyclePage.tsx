import { useEffect, useState, type UIEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Checkbox, Input, Popconfirm, Select, Space, Typography, message } from 'antd';
import { useParams } from 'react-router-dom';

import { spacesApi, type OwnershipCandidate } from '../../api/spaces';
import { PageHeader, Surface } from '../../design/primitives';
import { useAuthorization, useCapabilities } from '../../auth/CapabilityProvider';

export default function WorkspaceLifecyclePage() {
  const { t } = useTranslation('common');
  const { spaceId = '' } = useParams<{ spaceId: string }>();
  const { refresh } = useCapabilities();
  const access = useAuthorization();
  const [cloneName, setCloneName] = useState('');
  const [cloneCode, setCloneCode] = useState('');
  const [copyDocuments, setCopyDocuments] = useState(false);
  const [businessLine, setBusinessLine] = useState('');
  const [ownership, setOwnership] = useState<Awaited<ReturnType<typeof spacesApi.ownership>> | null>(null);
  const [ownerCandidates, setOwnerCandidates] = useState<OwnershipCandidate[]>([]);
  const [forceCandidates, setForceCandidates] = useState<OwnershipCandidate[]>([]);
  const [candidateNext, setCandidateNext] = useState<Record<'voluntary' | 'forced', number | null>>({ voluntary: null, forced: null });
  const [candidateQuery, setCandidateQuery] = useState<Record<'voluntary' | 'forced', string>>({ voluntary: '', forced: '' });
  const [candidateLoading, setCandidateLoading] = useState<Record<'voluntary' | 'forced', boolean>>({ voluntary: false, forced: false });
  const [ownerUser, setOwnerUser] = useState<string>();
  const [forcedOwnerUser, setForcedOwnerUser] = useState<string>();
  const [forceReason, setForceReason] = useState('administrative_continuity');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState(false);

  const run = async (key: string, operation: () => Promise<unknown>) => {
    setBusy(key); setError(false);
    try { await operation(); await refresh(); message.success(t('lifecycle_success')); }
    catch { setError(true); }
    finally { setBusy(''); }
  };

  const loadOwnership = async () => {
    if (!spaceId) return;
    try {
      const [detail, candidates, forced] = await Promise.all([
        spacesApi.ownership(spaceId),
        spacesApi.ownershipCandidatePage(spaceId),
        access.has('workspace.ownership.transfer.force')
          ? spacesApi.ownershipCandidatePage(spaceId, '', 'forced')
          : Promise.resolve({ results: [], next: null }),
      ]);
      setOwnership(detail);
      setOwnerCandidates(candidates.results);
      setForceCandidates(forced.results);
      setCandidateNext({ voluntary: candidates.next, forced: forced.next });
      setCandidateQuery({ voluntary: '', forced: '' });
    } catch {
      setError(true);
    }
  };

  const loadCandidatePage = async (
    purpose: 'voluntary' | 'forced',
    query: string,
    offset = 0,
    append = false,
  ) => {
    if (!spaceId) return;
    setCandidateLoading((current) => ({ ...current, [purpose]: true }));
    try {
      const page = await spacesApi.ownershipCandidatePage(spaceId, query, purpose, offset);
      if (purpose === 'voluntary') {
        setOwnerCandidates((current) => append ? [...current, ...page.results] : page.results);
      } else {
        setForceCandidates((current) => append ? [...current, ...page.results] : page.results);
      }
      setCandidateNext((current) => ({ ...current, [purpose]: page.next }));
      setCandidateQuery((current) => ({ ...current, [purpose]: query }));
    } catch {
      setError(true);
    } finally {
      setCandidateLoading((current) => ({ ...current, [purpose]: false }));
    }
  };

  const loadNextCandidates = (purpose: 'voluntary' | 'forced') => {
    const next = candidateNext[purpose];
    if (next !== null && !candidateLoading[purpose]) {
      void loadCandidatePage(purpose, candidateQuery[purpose], next, true);
    }
  };

  const handleCandidatePopupScroll = (purpose: 'voluntary' | 'forced', event: UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    if (target.scrollTop + target.clientHeight >= target.scrollHeight - 12) loadNextCandidates(purpose);
  };

  useEffect(() => { void loadOwnership(); }, [spaceId, access]);

  const requestOwnershipTransfer = async () => {
    if (!ownerUser || !ownership) return;
    await spacesApi.requestOwnershipTransfer(spaceId, {
      to_user_id: ownerUser,
      expected_ownership_version: ownership.ownership_version,
      reason_code: 'voluntary',
    });
    await loadOwnership();
  };

  const forceOwnershipTransfer = async () => {
    if (!forcedOwnerUser || !ownership) return;
    await spacesApi.forceOwnershipTransfer(spaceId, {
      to_user_id: forcedOwnerUser,
      expected_ownership_version: ownership.ownership_version,
      reason_code: forceReason,
    });
    await loadOwnership();
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
          <Typography.Text type="secondary">
            {ownership?.owner ? `Current owner: ${ownership.owner.display_name}` : 'Loading current owner…'}
          </Typography.Text>
          {ownership?.pending_transfer ? (
            <Alert
              type="info"
              showIcon
              message="Ownership transfer awaiting acceptance"
              description={`The selected successor must accept before ownership changes.`}
            />
          ) : (
            <>
              <Select
                showSearch
                filterOption={false}
                loading={candidateLoading.voluntary}
                value={ownerUser}
                onChange={setOwnerUser}
                onSearch={(query) => void loadCandidatePage('voluntary', query)}
                onPopupScroll={(event) => handleCandidatePopupScroll('voluntary', event)}
                placeholder="Select an eligible member"
                options={ownerCandidates.map((candidate) => ({ value: candidate.id, label: candidate.display_name }))}
              />
              <Popconfirm title="Request this ownership transfer? The successor must accept it." onConfirm={() => run('owner', requestOwnershipTransfer)}>
                <Button danger disabled={!ownerUser || !ownership} loading={busy === 'owner'}>{t('transfer_owner')}</Button>
              </Popconfirm>
            </>
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Ownership changes only after the selected successor accepts the request.
          </Typography.Text>
        </div>
        {access.has('workspace.ownership.transfer.force') && (
          <div style={{ display: 'grid', gap: 8 }}>
            <strong>{t('force_ownership_transfer')}</strong>
            <Alert
              type="warning"
              showIcon
              message={t('force_ownership_transfer_notice')}
            />
            <Select
              showSearch
              filterOption={false}
              loading={candidateLoading.forced}
              value={forcedOwnerUser}
              onChange={setForcedOwnerUser}
              onSearch={(query) => void loadCandidatePage('forced', query)}
              onPopupScroll={(event) => handleCandidatePopupScroll('forced', event)}
              placeholder={t('offboarding_select_successor')}
              options={forceCandidates.map((candidate) => ({ value: candidate.id, label: candidate.display_name }))}
            />
            <Select
              value={forceReason}
              onChange={setForceReason}
              options={[
                { value: 'administrative_continuity', label: t('force_reason_continuity') },
                { value: 'emergency', label: t('force_reason_emergency') },
              ]}
            />
            <Popconfirm
              title={t('force_ownership_transfer_confirm')}
              onConfirm={() => run('force-owner', forceOwnershipTransfer)}
            >
              <Button danger disabled={!forcedOwnerUser || !ownership} loading={busy === 'force-owner'}>
                {t('force_ownership_transfer')}
              </Button>
            </Popconfirm>
          </div>
        )}
      </Surface>
    </div>
  );
}
