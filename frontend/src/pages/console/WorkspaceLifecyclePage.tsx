import { useCallback, useEffect, useRef, useState, type UIEvent } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  Checkbox,
  Input,
  Popconfirm,
  Select,
  Space,
  Typography,
  message,
} from 'antd';
import { useParams } from 'react-router-dom';

import {
  spacesApi,
  type KnowledgeSpace,
  type OwnershipCandidate,
  type OwnershipDetail,
  type WorkspaceDeletionImpact,
  type WorkspaceDeletionRequest,
} from '../../api/spaces';
import { useAuthorization, useCapabilities } from '../../auth/CapabilityProvider';
import { PageHeader, Status, Surface } from '../../design/primitives';

type CandidatePurpose = 'voluntary' | 'forced';

function domainErrorCode(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (data && typeof data === 'object') {
    const code = (data as { code?: unknown }).code;
    if (typeof code === 'string' && code) return code;
  }
  return 'lifecycle_failed';
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString();
}

function requestTone(status: WorkspaceDeletionRequest['status']) {
  if (status === 'completed') return 'success' as const;
  if (status === 'failed' || status === 'invalidated') return 'error' as const;
  if (status === 'scheduled' || status === 'executing') return 'warning' as const;
  return 'info' as const;
}

export default function WorkspaceLifecyclePage() {
  const { t } = useTranslation('common');
  const { spaceId = '' } = useParams<{ spaceId: string }>();
  const { refresh, snapshot } = useCapabilities();
  const access = useAuthorization();
  const canForceTransfer = access.has('workspace.ownership.transfer.force');
  const canDeletePermanently = access.has('workspace.delete.permanent')
    && Boolean(snapshot?.feature_availability.workspace_permanent_delete);
  const requestSequence = useRef(0);

  const [space, setSpace] = useState<KnowledgeSpace | null>(null);
  const [ownership, setOwnership] = useState<OwnershipDetail | null>(null);
  const [ownerCandidates, setOwnerCandidates] = useState<OwnershipCandidate[]>([]);
  const [forceCandidates, setForceCandidates] = useState<OwnershipCandidate[]>([]);
  const [candidateNext, setCandidateNext] = useState<Record<CandidatePurpose, number | null>>({
    voluntary: null,
    forced: null,
  });
  const [candidateQuery, setCandidateQuery] = useState<Record<CandidatePurpose, string>>({
    voluntary: '',
    forced: '',
  });
  const [candidateLoading, setCandidateLoading] = useState<Record<CandidatePurpose, boolean>>({
    voluntary: false,
    forced: false,
  });

  const [cloneName, setCloneName] = useState('');
  const [cloneCode, setCloneCode] = useState('');
  const [businessLine, setBusinessLine] = useState('');
  const [ownerUser, setOwnerUser] = useState<string>();
  const [forcedOwnerUser, setForcedOwnerUser] = useState<string>();
  const [forceReason, setForceReason] = useState('administrative_continuity');
  const [busy, setBusy] = useState('');
  const [loadError, setLoadError] = useState(false);

  const [deletionImpact, setDeletionImpact] = useState<WorkspaceDeletionImpact | null>(null);
  const [deletionRequest, setDeletionRequest] = useState<WorkspaceDeletionRequest | null>(null);
  const [confirmationPhrase, setConfirmationPhrase] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [deletionError, setDeletionError] = useState<string | null>(null);

  const loadLifecycle = useCallback(
    async (signal?: AbortSignal) => {
      if (!spaceId) return;
      const sequence = ++requestSequence.current;
      setLoadError(false);
      try {
        const [nextSpace, detail, candidates, forced, impact] = await Promise.all([
          spacesApi.get(spaceId, signal),
          spacesApi.ownership(spaceId, signal),
          spacesApi.ownershipCandidatePage(spaceId, '', 'voluntary', 0, signal),
          canForceTransfer
            ? spacesApi.ownershipCandidatePage(spaceId, '', 'forced', 0, signal)
            : Promise.resolve({ results: [], next: null }),
          canDeletePermanently
            ? spacesApi.deletionImpact(spaceId, signal)
            : Promise.resolve(null),
        ]);
        if (signal?.aborted || sequence !== requestSequence.current) return;
        setSpace(nextSpace);
        setOwnership(detail);
        setOwnerCandidates(candidates.results);
        setForceCandidates(forced.results);
        setCandidateNext({ voluntary: candidates.next, forced: forced.next });
        setCandidateQuery({ voluntary: '', forced: '' });
        setDeletionImpact(impact);
        setDeletionRequest(impact?.active_request ?? null);
      } catch {
        if (signal?.aborted || sequence !== requestSequence.current) return;
        setLoadError(true);
      }
    },
    [canDeletePermanently, canForceTransfer, spaceId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadLifecycle(controller.signal);
    return () => controller.abort();
  }, [loadLifecycle]);

  useEffect(() => {
    const requestId = deletionRequest?.request_id;
    const live = deletionRequest
      ? ['pending', 'scheduled', 'executing', 'failed'].includes(deletionRequest.status)
      : false;
    if (!requestId || !live) return undefined;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await spacesApi.deletionStatus(requestId, controller.signal);
        if (controller.signal.aborted) return;
        setDeletionRequest(next);
      } catch {
        if (!controller.signal.aborted) setDeletionError('deletion_status_unavailable');
      }
      if (!controller.signal.aborted) timeout = setTimeout(poll, 8_000);
    };
    timeout = setTimeout(poll, 8_000);
    return () => {
      controller.abort();
      if (timeout) clearTimeout(timeout);
    };
  }, [deletionRequest?.request_id, deletionRequest?.status]);

  const run = async (key: string, operation: () => Promise<unknown>) => {
    setBusy(key);
    setLoadError(false);
    try {
      await operation();
      refresh();
      await loadLifecycle();
      message.success(t('lifecycle_success'));
    } catch {
      setLoadError(true);
    } finally {
      setBusy('');
    }
  };

  const loadCandidatePage = async (
    purpose: CandidatePurpose,
    query: string,
    offset = 0,
    append = false,
  ) => {
    if (!spaceId) return;
    setCandidateLoading((current) => ({ ...current, [purpose]: true }));
    try {
      const page = await spacesApi.ownershipCandidatePage(spaceId, query, purpose, offset);
      if (purpose === 'voluntary') {
        setOwnerCandidates((current) => (append ? [...current, ...page.results] : page.results));
      } else {
        setForceCandidates((current) => (append ? [...current, ...page.results] : page.results));
      }
      setCandidateNext((current) => ({ ...current, [purpose]: page.next }));
      setCandidateQuery((current) => ({ ...current, [purpose]: query }));
    } catch {
      setLoadError(true);
    } finally {
      setCandidateLoading((current) => ({ ...current, [purpose]: false }));
    }
  };

  const loadNextCandidates = (purpose: CandidatePurpose) => {
    const next = candidateNext[purpose];
    if (next !== null && !candidateLoading[purpose]) {
      void loadCandidatePage(purpose, candidateQuery[purpose], next, true);
    }
  };

  const handleCandidatePopupScroll = (
    purpose: CandidatePurpose,
    event: UIEvent<HTMLDivElement>,
  ) => {
    const target = event.currentTarget;
    if (target.scrollTop + target.clientHeight >= target.scrollHeight - 12) {
      loadNextCandidates(purpose);
    }
  };

  const requestOwnershipTransfer = async () => {
    if (!ownerUser || !ownership) return;
    await spacesApi.requestOwnershipTransfer(spaceId, {
      to_user_id: ownerUser,
      expected_ownership_version: ownership.ownership_version,
      reason_code: 'voluntary',
    });
  };

  const forceOwnershipTransfer = async () => {
    if (!forcedOwnerUser || !ownership) return;
    await spacesApi.forceOwnershipTransfer(spaceId, {
      to_user_id: forcedOwnerUser,
      expected_ownership_version: ownership.ownership_version,
      reason_code: forceReason,
    });
  };

  const runDeletion = async (key: string, operation: () => Promise<WorkspaceDeletionRequest>) => {
    setBusy(key);
    setDeletionError(null);
    try {
      const result = await operation();
      setDeletionRequest(result);
      setConfirmationPhrase('');
      setAcknowledged(false);
      const refreshedImpact = await spacesApi.deletionImpact(spaceId);
      setDeletionImpact(refreshedImpact);
      if (result.status === 'cancelled') setDeletionRequest(null);
    } catch (error: unknown) {
      const code = domainErrorCode(error);
      setDeletionError(code);
      if (code === 'impact_changed' || code === 'ownership_changed') {
        setConfirmationPhrase('');
        setAcknowledged(false);
        try {
          const refreshedImpact = await spacesApi.deletionImpact(spaceId);
          setDeletionImpact(refreshedImpact);
          setDeletionRequest(refreshedImpact.active_request);
        } catch {
          setLoadError(true);
        }
      }
    } finally {
      setBusy('');
    }
  };

  const blockers = deletionImpact?.blockers ?? [];
  const deletionPending = deletionRequest?.status === 'pending';
  const deletionCancellable =
    deletionRequest?.status === 'pending' || deletionRequest?.status === 'scheduled';
  const phraseMatches = confirmationPhrase === deletionImpact?.confirmation_phrase;

  return (
    <div className="page section-enter kp-lifecycle-page">
      <PageHeader
        eyebrow={t('workspace_governance')}
        title={t('workspace_lifecycle')}
        description={t('workspace_lifecycle_description')}
      />
      {loadError ? <Alert showIcon type="error" message={t('lifecycle_failed')} /> : null}

      <div className="kp-lifecycle-grid">
        <Surface as="section" className="kp-lifecycle-section">
          <div className="kp-lifecycle-section__head">
            <div>
              <div className="kp-lifecycle-kicker">{t('workspace_state')}</div>
              <h2>{space?.name ?? t('workspace')}</h2>
            </div>
            <Status tone={space?.status === 'archived' ? 'warning' : 'success'}>
              {space?.status === 'archived' ? t('status_archived') : t('status_active')}
            </Status>
          </div>
          <Typography.Paragraph type="secondary">
            {space?.status === 'archived'
              ? t('workspace_archived_read_only')
              : t('workspace_archive_explainer')}
          </Typography.Paragraph>
          <Space wrap>
            {space?.status !== 'archived' ? (
              <Popconfirm
                title={t('confirm_archive_workspace')}
                onConfirm={() => run('archive', () => spacesApi.archive(spaceId))}
              >
                <Button danger loading={busy === 'archive'}>{t('archive')}</Button>
              </Popconfirm>
            ) : (
              <Button
                loading={busy === 'restore'}
                disabled={Boolean(deletionRequest)}
                onClick={() => run('restore', () => spacesApi.restore(spaceId))}
              >
                {t('restore')}
              </Button>
            )}
          </Space>
        </Surface>

        <Surface as="section" className="kp-lifecycle-section">
          <div className="kp-lifecycle-kicker">{t('workspace_structure')}</div>
          <h2>{t('clone_workspace')}</h2>
          <Typography.Paragraph type="secondary">
            {t('clone_workspace_configuration_only')}
          </Typography.Paragraph>
          <Input
            value={cloneName}
            onChange={(event) => setCloneName(event.target.value)}
            placeholder={t('space_name')}
          />
          <Input
            value={cloneCode}
            onChange={(event) => setCloneCode(event.target.value)}
            placeholder={t('space_code')}
          />
          <Button
            disabled={!cloneName || !cloneCode || space?.status === 'archived'}
            loading={busy === 'clone'}
            onClick={() =>
              run('clone', () =>
                spacesApi.clone(spaceId, {
                  name: cloneName,
                  code: cloneCode,
                  copy_documents: false,
                }),
              )
            }
          >
            {t('clone_workspace')}
          </Button>

          <div className="kp-lifecycle-subsection">
            <strong>{t('transfer_business_line')}</strong>
            <Input
              value={businessLine}
              onChange={(event) => setBusinessLine(event.target.value)}
              placeholder={t('business_line_id')}
            />
            <Popconfirm
              title={t('confirm_transfer_workspace')}
              onConfirm={() => run('transfer', () => spacesApi.transfer(spaceId, businessLine))}
            >
              <Button
                disabled={!businessLine || space?.status === 'archived'}
                loading={busy === 'transfer'}
              >
                {t('transfer')}
              </Button>
            </Popconfirm>
          </div>
        </Surface>

        <Surface as="section" className="kp-lifecycle-section">
          <div className="kp-lifecycle-kicker">{t('ownership_continuity')}</div>
          <h2>{t('transfer_owner')}</h2>
          <Typography.Text type="secondary">
            {ownership?.owner
              ? t('current_owner_name', { name: ownership.owner.display_name })
              : t('current_owner_loading')}
          </Typography.Text>
          {ownership?.pending_transfer ? (
            <Alert
              type="info"
              showIcon
              message={t('ownership_transfer_pending')}
              description={t('ownership_transfer_pending_description')}
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
                placeholder={t('select_eligible_member')}
                options={ownerCandidates.map((candidate) => ({
                  value: candidate.id,
                  label: candidate.display_name,
                }))}
              />
              <Popconfirm
                title={t('ownership_transfer_confirm')}
                onConfirm={() => run('owner', requestOwnershipTransfer)}
              >
                <Button
                  danger
                  disabled={!ownerUser || !ownership || space?.status === 'archived'}
                  loading={busy === 'owner'}
                >
                  {t('transfer_owner')}
                </Button>
              </Popconfirm>
            </>
          )}
          <Typography.Text type="secondary" className="kp-lifecycle-fine-print">
            {t('ownership_transfer_acceptance_note')}
          </Typography.Text>
        </Surface>

        {canForceTransfer ? (
          <Surface as="section" className="kp-lifecycle-section">
            <div className="kp-lifecycle-kicker">{t('governed_override')}</div>
            <h2>{t('force_ownership_transfer')}</h2>
            <Alert type="warning" showIcon message={t('force_ownership_transfer_notice')} />
            <Select
              showSearch
              filterOption={false}
              loading={candidateLoading.forced}
              value={forcedOwnerUser}
              onChange={setForcedOwnerUser}
              onSearch={(query) => void loadCandidatePage('forced', query)}
              onPopupScroll={(event) => handleCandidatePopupScroll('forced', event)}
              placeholder={t('offboarding_select_successor')}
              options={forceCandidates.map((candidate) => ({
                value: candidate.id,
                label: candidate.display_name,
              }))}
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
              <Button
                danger
                disabled={!forcedOwnerUser || !ownership}
                loading={busy === 'force-owner'}
              >
                {t('force_ownership_transfer')}
              </Button>
            </Popconfirm>
          </Surface>
        ) : null}
      </div>

      {canDeletePermanently ? (
        <Surface as="section" className="kp-lifecycle-section kp-danger-zone">
          <div className="kp-lifecycle-section__head">
            <div>
              <div className="kp-lifecycle-kicker">{t('danger_zone')}</div>
              <h2>{t('delete_workspace_permanently')}</h2>
            </div>
            {deletionRequest ? (
              <Status tone={requestTone(deletionRequest.status)}>
                {t(`deletion_status_${deletionRequest.status}`)}
              </Status>
            ) : null}
          </div>
          <Typography.Paragraph type="secondary">
            {t('delete_workspace_permanently_description')}
          </Typography.Paragraph>
          {deletionError ? (
            <Alert
              showIcon
              type="error"
              message={t(`deletion_error_${deletionError}`, {
                defaultValue: t('deletion_error_generic'),
              })}
            />
          ) : null}

          {blockers.length ? (
            <Alert
              showIcon
              type="warning"
              message={t('deletion_blockers_title')}
              description={(
                <ul className="kp-danger-zone__blockers">
                  {blockers.map((blocker) => (
                    <li key={`${blocker.kind}:${blocker.id}`}>
                      <strong>{t(`deletion_blocker_${blocker.kind}`)}</strong>
                      <span>{blocker.status}</span>
                    </li>
                  ))}
                </ul>
              )}
            />
          ) : null}

          {deletionImpact ? (
            <div className="kp-danger-zone__facts" aria-label={t('deletion_impact_summary')}>
              <div><span>{t('eligible_content_count')}</span><strong>{deletionImpact.counts.eligible_content}</strong></div>
              <div><span>{t('retained_evidence_count')}</span><strong>{deletionImpact.counts.retained_evidence}</strong></div>
              <div><span>{t('earliest_purge_time')}</span><strong>{formatDate(deletionRequest?.purge_not_before ?? deletionImpact.earliest_purge_at)}</strong></div>
            </div>
          ) : null}

          {!deletionRequest ? (
            <div className="kp-danger-zone__step">
              <div>
                <strong>{t('deletion_step_request')}</strong>
                <p>{t('deletion_step_request_description')}</p>
              </div>
              <Button
                danger
                disabled={space?.status !== 'archived' || blockers.length > 0 || !deletionImpact}
                loading={busy === 'delete-request'}
                onClick={() => {
                  if (deletionImpact) {
                    void runDeletion('delete-request', () =>
                      spacesApi.submitDeletion(spaceId, deletionImpact),
                    );
                  }
                }}
              >
                {space?.status === 'archived'
                  ? t('request_permanent_deletion')
                  : t('archive_before_deletion')}
              </Button>
            </div>
          ) : null}

          {deletionPending && deletionImpact ? (
            <div className="kp-danger-zone__confirmation">
              <div className="kp-danger-zone__step-number">02</div>
              <div>
                <h3>{t('confirm_permanent_deletion')}</h3>
                <p>{t('confirm_permanent_deletion_description')}</p>
              </div>
              <code>{deletionImpact.confirmation_phrase}</code>
              <Input
                value={confirmationPhrase}
                onChange={(event) => setConfirmationPhrase(event.target.value)}
                placeholder={deletionImpact.confirmation_phrase}
                aria-label={t('deletion_confirmation_phrase')}
                autoComplete="off"
                spellCheck={false}
              />
              <Checkbox
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
              >
                {t('deletion_permanence_acknowledgement')}
              </Checkbox>
              <Button
                danger
                type="primary"
                disabled={!phraseMatches || !acknowledged}
                loading={busy === 'delete-confirm'}
                onClick={() =>
                  void runDeletion('delete-confirm', () =>
                    spacesApi.confirmDeletion(
                      spaceId,
                      deletionRequest,
                      deletionImpact,
                      confirmationPhrase,
                    ),
                  )
                }
              >
                {t('schedule_permanent_deletion')}
              </Button>
            </div>
          ) : null}

          {deletionRequest?.purge ? (
            <div className="kp-danger-zone__stores">
              {deletionRequest.purge.stores.map((store) => (
                <div key={store.store}>
                  <span>{store.store}</span>
                  <Status tone={store.status === 'acked' ? 'success' : store.status === 'failed' ? 'error' : 'info'}>
                    {store.status}
                  </Status>
                </div>
              ))}
            </div>
          ) : null}

          {deletionCancellable && deletionRequest ? (
            <Button
              loading={busy === 'delete-cancel'}
              onClick={() =>
                void runDeletion('delete-cancel', () =>
                  spacesApi.cancelDeletion(spaceId, deletionRequest),
                )
              }
            >
              {t('cancel_permanent_deletion')}
            </Button>
          ) : null}
        </Surface>
      ) : null}
    </div>
  );
}
