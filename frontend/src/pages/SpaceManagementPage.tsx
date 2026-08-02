/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// SpaceManagementPage — V6.0 (SPEC.MD §7.6).
// Owner/admin view for the active space: edit settings, view members, and
// generate / revoke access (invite) codes. All actions are re-checked server-side.

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Card,
  List,
  Button,
  Input,
  Select,
  Tag,
  Typography,
  Space,
  Modal,
  Popconfirm,
  Alert,
  Radio,
  Switch,
  Table,
  message as antdMessage,
} from 'antd';
import { PlusOutlined, ReloadOutlined, CopyOutlined, SyncOutlined, SwapOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useParams, useLocation } from 'react-router-dom';
import { useSpaceStore } from '../store/spaceStore';
import {
  spacesApi,
  type KnowledgeSpace,
  type SpaceMember,
  type InviteCode,
  type SpaceRole,
  type JoinCodeInfo,
  type JoinPolicy,
  type OwnershipDetail,
  type OwnershipCandidate,
} from '../api/spaces';
import { useAuthorization } from '../auth/CapabilityProvider';
import { getRateLimitDetails, isAbortError, withRequestSignal } from '../api/client';
import { AppShell, EmptyState, PageHeader } from '../design/primitives';

const { Text, Paragraph } = Typography;

export default function SpaceManagementPage() {
  const { t } = useTranslation('common');
  const access = useAuthorization();
  const { spaceId: routeSpaceId } = useParams<{ spaceId: string }>();
  const { activeSpaceId, getActiveSpace, loadSpaces, spaces: allSpaces } = useSpaceStore();
  const storeActive = getActiveSpace();
  const spaceId = routeSpaceId || activeSpaceId;
  const [routeSpace, setRouteSpace] = useState<KnowledgeSpace | null>(null);
  const [spaceLoading, setSpaceLoading] = useState(false);
  const [spaceLoadFailed, setSpaceLoadFailed] = useState(false);
  const active = storeActive?.id === spaceId
    ? storeActive
    : routeSpace?.id === spaceId
      ? routeSpace
      : null;

  const canManageSettings = access.has('workspace.settings.manage');
  const canManageMembers = access.has('workspace.members.manage');
  const canManageInvites = access.has('workspace.invites.manage');
  const canReadMembers = !access.enabled || canManageMembers;
  const canManageJoinPolicy = canManageSettings;

  // Detect current management section from the URL path so each sub-route
  // only renders the card(s) it owns (settings / members / invites).
  const location = useLocation();
  const pathSegments = location.pathname.split('/').filter(Boolean);
  const rawSection = pathSegments[pathSegments.length - 1] || '';
  const section: 'settings' | 'members' | 'invites' =
    rawSection === 'members' ? 'members' : rawSection === 'invites' ? 'invites' : 'settings';
  const showSettings = section === 'settings';
  const showJoinPolicy = section === 'settings';
  const showMembers = section === 'members';
  const showInvites = section === 'invites';
  const useGrid = showSettings && showJoinPolicy;

  const [members, setMembers] = useState<SpaceMember[]>([]);
  const [invites, setInvites] = useState<InviteCode[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);
  const requestSequence = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!spaceId || storeActive?.id === spaceId) {
      setRouteSpace(null);
      setSpaceLoading(false);
      setSpaceLoadFailed(false);
      return;
    }
    const controller = new AbortController();
    setRouteSpace(null);
    setSpaceLoading(true);
    setSpaceLoadFailed(false);
    spacesApi.get(spaceId, controller.signal).then((resolved) => {
      if (!controller.signal.aborted) setRouteSpace(resolved);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted && !isAbortError(error)) setSpaceLoadFailed(true);
    }).finally(() => {
      if (!controller.signal.aborted) setSpaceLoading(false);
    });
    return () => controller.abort();
  }, [spaceId, storeActive?.id]);

  // Settings form
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState('private');
  // Spec §3: space-level review gate (direct_publish | require_review)
  const [reviewPolicy, setReviewPolicy] = useState('direct_publish');
  const [savingSettings, setSavingSettings] = useState(false);

  // Invite creation
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteRole] = useState<SpaceRole>('guest');
  const [inviteMaxUses, setInviteMaxUses] = useState<number>(20);
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [generatedCode, setGeneratedCode] = useState<string | null>(null);

  // V7.0: add member by email
  const [memberEmail, setMemberEmail] = useState('');
  const [memberRole] = useState<SpaceRole>('guest');
  const [addingMember, setAddingMember] = useState(false);

  // Join policy management
  const [joinCodeInfo, setJoinCodeInfo] = useState<JoinCodeInfo | null>(null);
  const [switchingPolicy, setSwitchingPolicy] = useState(false);
  const [regeneratingCode, setRegeneratingCode] = useState(false);
  const [togglingInvite, setTogglingInvite] = useState(false);
  const [customCodeModalOpen, setCustomCodeModalOpen] = useState(false);
  const [customCode, setCustomCode] = useState('');

  // Bug#9: Ownership transfer state (single + batch)
  const [ownership, setOwnership] = useState<OwnershipDetail | null>(null);
  const [ownerCandidates, setOwnerCandidates] = useState<OwnershipCandidate[]>([]);
  const [ownerUser, setOwnerUser] = useState<string>();
  const [transferring, setTransferring] = useState(false);
  const [batchSelectedSpaceIds, setBatchSelectedSpaceIds] = useState<string[]>([]);
  const [batchTargetUser, setBatchTargetUser] = useState<string>();
  const [batchTransferring, setBatchTransferring] = useState(false);

  const refresh = useCallback(async () => {
    if (!spaceId) return;
    const sequence = ++requestSequence.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setLoadError(null);
    try {
      const [m, inv, jci] = await Promise.all([
        canReadMembers
          ? withRequestSignal(controller.signal, () => spacesApi.members(spaceId))
          : Promise.resolve([]),
        canManageInvites
          ? withRequestSignal(controller.signal, () => spacesApi.listInvites(spaceId))
          : Promise.resolve([]),
        withRequestSignal(controller.signal, () => spacesApi.getJoinCode(spaceId)).catch(() => null),
      ]);
      if (controller.signal.aborted || sequence !== requestSequence.current) return;
      setMembers(m);
      setInvites(inv);
      if (jci) setJoinCodeInfo(jci);
    } catch (error: unknown) {
      if (isAbortError(error) || controller.signal.aborted || sequence !== requestSequence.current) return;
      const rateLimit = getRateLimitDetails(error);
      setLoadError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    } finally {
      if (sequence === requestSequence.current && !controller.signal.aborted) setLoading(false);
    }
  }, [spaceId, canManageInvites, canReadMembers]);

  // Bug#14: auto-retry once on initial mount if the first load fails.
  const [autoRetried, setAutoRetried] = useState(false);
  useEffect(() => {
    if (!active) return;
    setName(active.name);
    setDescription(active.description);
    setVisibility(active.visibility);
        setReviewPolicy(active.review_policy || 'direct_publish');
    setJoinCodeInfo({
      space_id: active.id,
      join_policy: active.join_policy,
      join_code: active.join_code,
      allow_member_invite: active.allow_member_invite,
      join_code_updated_at: active.join_code_updated_at,
    });
    refresh().then(() => {}).catch(() => {
      // Bug#14: auto-retry after 2s if the first load fails
      if (!autoRetried) {
        setAutoRetried(true);
        setTimeout(() => void refresh(), 2000);
      }
    });
    return () => {
      requestSequence.current += 1;
      controllerRef.current?.abort();
    };
  }, [active?.id, refresh, autoRetried]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveSettings = async () => {
    if (!spaceId) return;
    setSavingSettings(true);
    try {
      await spacesApi.update(spaceId, { name, description, visibility: visibility as any, review_policy: reviewPolicy as any });
      await loadSpaces();
      antdMessage.success(t('space_settings_saved') || 'Settings saved');
    } catch {
      antdMessage.error(t('space_settings_failed') || 'Failed to save settings');
    } finally {
      setSavingSettings(false);
    }
  };

  const createInvite = async () => {
    if (!spaceId) return;
    setCreatingInvite(true);
    try {
      const inv = await spacesApi.createInvite(spaceId, {
        role: inviteRole,
        max_uses: inviteMaxUses,
      });
      setGeneratedCode(inv.code ?? null);
      setInviteOpen(false);
      await refresh();
    } catch {
      antdMessage.error(t('invite_create_failed') || 'Failed to create invite code');
    } finally {
      setCreatingInvite(false);
    }
  };

  const revokeInvite = async (invite: InviteCode) => {
    if (!spaceId) return;
    try {
      await spacesApi.revokeInvite(spaceId, invite);
      await refresh();
      antdMessage.success(t('invite_revoked') || 'Invite code revoked');
    } catch {
      antdMessage.error(t('invite_revoke_failed') || 'Failed to revoke');
    }
  };

  // V7.0: add a member by email (existing account -> active member + notified;
  // unknown email -> pending invite redeemed on signup).
  const addMember = async () => {
    if (!spaceId || !memberEmail.trim()) return;
    setAddingMember(true);
    try {
      await spacesApi.addMember(spaceId, { email: memberEmail.trim(), role: memberRole });
      setMemberEmail('');
      await refresh();
      antdMessage.success(t('member_invited_pending') || 'Targeted invitation created');
    } catch {
      antdMessage.error(t('member_add_failed') || 'Failed to add member');
    } finally {
      setAddingMember(false);
    }
  };

  const changeMemberRole = async (member: SpaceMember, role: SpaceRole) => {
    if (!spaceId) return;
    try {
      await spacesApi.updateMember(spaceId, member, role);
      await refresh();
      antdMessage.success(t('member_role_updated') || 'Member role updated');
    } catch {
      antdMessage.error(t('member_update_failed') || 'Failed to update member');
    }
  };

  const removeMember = async (member: SpaceMember) => {
    if (!spaceId) return;
    try {
      await spacesApi.removeMember(spaceId, member);
      await refresh();
      antdMessage.success(t('member_removed') || 'Member removed');
    } catch {
      antdMessage.error(t('member_remove_failed') || 'Failed to remove member');
    }
  };

  const handleSwitchPolicy = async (newPolicy: JoinPolicy) => {
    if (!spaceId || newPolicy === joinCodeInfo?.join_policy) return;
    setSwitchingPolicy(true);
    try {
      await spacesApi.switchJoinPolicy(spaceId, newPolicy);
      await refresh();
      await loadSpaces();
      antdMessage.success(t('join_policy_switched') || 'Join policy updated');
    } catch {
      antdMessage.error(t('join_policy_switch_failed') || 'Failed to switch join policy');
    } finally {
      setSwitchingPolicy(false);
    }
  };

  const handleRegenerateCode = async () => {
    if (!spaceId) return;
    setRegeneratingCode(true);
    try {
      const result = await spacesApi.regenerateJoinCode(spaceId, customCode.trim() || undefined);
      setJoinCodeInfo(prev => prev ? {
        ...prev,
        join_code: result.join_code,
        join_code_updated_at: result.join_code_updated_at,
      } : {
        space_id: result.space_id,
        join_policy: result.join_policy,
        join_code: result.join_code,
        allow_member_invite: true,
        join_code_updated_at: result.join_code_updated_at,
      });
      setCustomCodeModalOpen(false);
      setCustomCode('');
      antdMessage.success(t('join_code_regenerated') || 'Join code regenerated');
    } catch {
      antdMessage.error(t('join_code_regenerate_failed') || 'Failed to regenerate join code');
    } finally {
      setRegeneratingCode(false);
    }
  };

  const handleToggleMemberInvite = async (checked: boolean) => {
    if (!spaceId) return;
    setTogglingInvite(true);
    try {
      await spacesApi.toggleAllowMemberInvite(spaceId, checked);
      setJoinCodeInfo(prev => prev ? { ...prev, allow_member_invite: checked } : prev);
      antdMessage.success(t('invite_permission_updated') || 'Invite permission updated');
    } catch {
      antdMessage.error(t('invite_permission_update_failed') || 'Failed to update invite permission');
    } finally {
      setTogglingInvite(false);
    }
  };

  const copyJoinCode = () => {
    if (joinCodeInfo?.join_code) {
      navigator.clipboard.writeText(joinCodeInfo.join_code);
      antdMessage.success(t('copied') || 'Copied to clipboard');
    }
  };

  // Bug#9: Owner check — must be declared before useEffect that uses it
  const isOwner = access.has('workspace.ownership.transfer.request') || access.has('workspace.ownership.transfer.force');

  // Bug#9: Load ownership details for single transfer
  useEffect(() => {
    if (!spaceId || !isOwner) return;
    const controller = new AbortController();
    (async () => {
      try {
        const [detail, candidates] = await Promise.all([
          spacesApi.ownership(spaceId, controller.signal),
          spacesApi.ownershipCandidatePage(spaceId, '', 'voluntary', 0, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setOwnership(detail);
        setOwnerCandidates(candidates.results);
      } catch {
        // ignore — ownership section degrades gracefully
      }
    })();
    return () => controller.abort();
  }, [spaceId, isOwner]); // eslint-disable-line react-hooks/exhaustive-deps

  // Bug#9: Single ownership transfer
  const handleSingleTransfer = async () => {
    if (!spaceId || !ownerUser || !ownership) return;
    setTransferring(true);
    try {
      await spacesApi.requestOwnershipTransfer(spaceId, {
        to_user_id: ownerUser,
        expected_ownership_version: ownership.ownership_version,
        reason_code: 'voluntary',
      });
      antdMessage.success(t('batch_transfer_success') || 'Ownership transfer initiated');
      setOwnerUser(undefined);
      const [detail, candidates] = await Promise.all([
        spacesApi.ownership(spaceId),
        spacesApi.ownershipCandidatePage(spaceId, '', 'voluntary', 0),
      ]);
      setOwnership(detail);
      setOwnerCandidates(candidates.results);
    } catch {
      antdMessage.error(t('batch_transfer_failed') || 'Transfer failed');
    } finally {
      setTransferring(false);
    }
  };

  // Bug#9: Batch ownership transfer
  const handleBatchTransfer = async () => {
    if (!batchTargetUser || batchSelectedSpaceIds.length === 0) return;
    setBatchTransferring(true);
    let success = 0;
    let failed = 0;
    for (const sid of batchSelectedSpaceIds) {
      try {
        const detail = await spacesApi.ownership(sid);
        await spacesApi.requestOwnershipTransfer(sid, {
          to_user_id: batchTargetUser,
          expected_ownership_version: detail.ownership_version,
          reason_code: 'voluntary',
        });
        success++;
      } catch {
        failed++;
      }
    }
    if (success > 0) antdMessage.success(`${t('batch_transfer_success') || 'Transfer successful'} (${success}/${batchSelectedSpaceIds.length})`);
    if (failed > 0) antdMessage.error(`${t('batch_transfer_failed') || 'Transfer failed'} (${failed}/${batchSelectedSpaceIds.length})`);
    setBatchSelectedSpaceIds([]);
    setBatchTargetUser(undefined);
    setBatchTransferring(false);
    if (spaceId && isOwner) {
      try {
        const [detail, candidates] = await Promise.all([
          spacesApi.ownership(spaceId),
          spacesApi.ownershipCandidatePage(spaceId, '', 'voluntary', 0),
        ]);
        setOwnership(detail);
        setOwnerCandidates(candidates.results);
      } catch { /* ignore */ }
    }
  };

  const MEMBER_ROLE_OPTIONS: SpaceRole[] = isOwner
    ? ['space_admin', 'member', 'guest']
    : ['member', 'guest'];

  if (!active) {
    return (
      <AppShell as="section" width="management" className="kp-space-workbench kp-space-workbench--empty section-enter">
        <EmptyState
          title={spaceLoading
            ? (t('loading') || 'Loading workspace…')
            : spaceLoadFailed
              ? (t('load_error') || 'Unable to load workspace data')
              : (t('no_active_space') || 'No active space selected')}
        />
      </AppShell>
    );
  }


  return (
    <AppShell as="section" width="management" className="kp-space-workbench">
        <PageHeader
          eyebrow={t('workspace_management')}
          title={`${t('space_management') || 'Space Management'} — ${active.name}`}
          description={active.description || t('space_management')}
        />
        {loadError && (
          <Alert
            type="error"
            showIcon
            closable={false}
            style={{ marginBottom: 16 }}
            message={loadError.code === 'rate_limited'
              ? `${t('rate_limited') || 'Too many requests'}${loadError.retryAfterSeconds == null ? '' : ` — retry in ${loadError.retryAfterSeconds}s`}`
              : (t('load_error') || 'Unable to load workspace data')}
            action={<Button onClick={() => void refresh()}>{t('error_retry') || 'Retry'}</Button>}
          />
        )}

        <div className={useGrid ? 'kp-mgmt-grid kp-space-task-grid' : 'kp-space-task-grid'}>
        {showSettings && (
        <Card
          title={
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 16 }}>
              {t('space_settings') || 'Space settings'}
            </span>
          }
          styles={{ body: { padding: '28px' } }}
          className="glass-panel hover-lift"
          style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)' }}
        >
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <div>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('space_name') || 'Space name'}</Text>
              <Input size="large" value={name} onChange={(e) => setName(e.target.value)} disabled={!canManageSettings} style={{ marginTop: 6, borderRadius: 10 }} />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('space_description') || 'Description'}</Text>
              <Input.TextArea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={!canManageSettings}
                rows={3}
                style={{ marginTop: 6, borderRadius: 10 }}
              />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('space_visibility') || 'Visibility'}</Text>
              <Select
                size="large"
                value={visibility}
                onChange={setVisibility}
                disabled={!canManageSettings}
                style={{ width: 260, display: 'block', marginTop: 6 }}
                classNames={{ popup: { root: 'menu-pop-dropdown' } }}
                options={[
                  { value: 'private', label: t('visibility_private') || 'Private' },
                  { value: 'business_line', label: t('visibility_business_line') || 'Business line' },
                  { value: 'organization', label: t('visibility_organization') || 'Organization' },
                  { value: 'public_demo', label: t('visibility_public_demo') || 'Public demo' },
                ]}
              />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('space_review_policy') || 'Review policy'}</Text>
              <Select
                size="large"
                value={reviewPolicy}
                onChange={setReviewPolicy}
                disabled={!canManageSettings}
                style={{ width: 260, display: 'block', marginTop: 6 }}
                classNames={{ popup: { root: 'menu-pop-dropdown' } }}
                options={[
                  { value: 'require_review', label: t('review_policy_require') || 'Require review' },
                  { value: 'direct_publish', label: t('review_policy_direct') || 'Direct publish' },
                ]}
              />
              <Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 4 }}>
                {t('space_review_policy_hint')}
              </Text>
            </div>
            {canManageSettings && (
              <Button type="primary" loading={savingSettings} onClick={saveSettings} size="large" style={{ height: 44, borderRadius: 12, fontWeight: 600, padding: '0 24px', marginTop: 8 }}>
                {t('save') || 'Save'}
              </Button>
            )}
          </Space>
        </Card>
        )}

        {showJoinPolicy && (
        <Card
          title={
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 16 }}>
              {t('join_policy_title') || '加入策略'}
            </span>
          }
          styles={{ body: { padding: '28px' } }}
          className="glass-panel hover-lift"
          style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)' }}
        >
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            {/* Current policy display */}
            <div>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('current_join_policy') || '当前策略'}</Text>
              <div style={{ marginTop: 8 }}>
                <Tag color={joinCodeInfo?.join_policy === 'global' ? 'blue' : 'gold'} style={{ fontSize: 14, padding: '4px 12px' }}>
                  {joinCodeInfo?.join_policy === 'global'
                    ? (t('join_policy_global') || '全局可见')
                    : (t('join_policy_access_code') || '邀请码加入')}
                </Tag>
              </div>
            </div>

            {/* Access code mode: show join code */}
            {joinCodeInfo?.join_policy === 'access_code' && joinCodeInfo.join_code && (
              <div>
                <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('join_code') || '加入码'}</Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                  <Input
                    readOnly
                    value={joinCodeInfo.join_code}
                    style={{ flex: 1, borderRadius: 10, fontFamily: 'var(--font-family-mono)' }}
                  />
                  <Button
                    icon={<CopyOutlined />}
                    onClick={copyJoinCode}
                    style={{ borderRadius: 10 }}
                  >
                    {t('copy') || '复制'}
                  </Button>
                  {canManageJoinPolicy && (
                    <Button
                      icon={<SyncOutlined />}
                      onClick={() => setCustomCodeModalOpen(true)}
                      loading={regeneratingCode}
                      style={{ borderRadius: 10 }}
                    >
                      {t('regenerate') || '重新生成'}
                    </Button>
                  )}
                </div>
                {joinCodeInfo.join_code_updated_at && (
                  <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
                    {t('updated_at') || '更新于'}: {new Date(joinCodeInfo.join_code_updated_at).toLocaleString()}
                  </Text>
                )}
              </div>
            )}

            {/* Global mode: show info */}
            {joinCodeInfo?.join_policy === 'global' && (
              <Alert
                type="info"
                showIcon
                message={t('global_join_hint') || '该空间在发现页可见，用户可直接加入'}
                style={{ borderRadius: 10 }}
              />
            )}

            {/* Policy switch (owner/admin only) */}
            {canManageJoinPolicy && (
              <div>
                <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('switch_join_policy') || '切换策略'}</Text>
                <div style={{ marginTop: 8 }}>
                  <Radio.Group
                    value={joinCodeInfo?.join_policy ?? 'access_code'}
                    onChange={(e) => void handleSwitchPolicy(e.target.value as JoinPolicy)}
                    disabled={switchingPolicy}
                  >
                    <Space direction="vertical">
                      <Radio value="access_code">{t('join_policy_access_code') || '邀请码加入 — 空间隐藏，凭加入码加入'}</Radio>
                      <Radio value="global">{t('join_policy_global') || '全局可见 — 在发现页展示，用户可直接加入'}</Radio>
                    </Space>
                  </Radio.Group>
                </div>
              </div>
            )}

            {/* Allow member invite toggle (owner/admin only) */}
            {canManageJoinPolicy && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0', borderTop: '1px solid var(--color-border-secondary)' }}>
                <div>
                  <Text strong style={{ fontSize: 14 }}>{t('allow_member_invite') || '允许成员邀请'}</Text>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 2 }}>
                    {t('allow_member_invite_hint') || '开启后，所有成员均可发起邀请；关闭后仅所有者可邀请'}
                  </Text>
                </div>
                <Switch
                  checked={joinCodeInfo?.allow_member_invite ?? true}
                  loading={togglingInvite}
                  onChange={(checked) => void handleToggleMemberInvite(checked)}
                />
              </div>
            )}
          </Space>
        </Card>
        )}

        {showMembers && (
        <Card
          title={
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 16 }}>
              {t('space_members') || 'Members'}
            </span>
          }
          styles={{ body: { padding: '24px' } }}
          className="glass-panel hover-lift"
          style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)' }}
          extra={<Button icon={<ReloadOutlined />} size="middle" onClick={refresh} style={{ borderRadius: 8 }} />}
        >
          {canManageMembers && (
            <div className="kp-space-member-actions">
              <Input
                placeholder={t('member_email_placeholder') || 'Add member by email…'}
                value={memberEmail}
                onChange={(e) => setMemberEmail(e.target.value)}
                onPressEnter={addMember}
                style={{ flex: 1, minWidth: 220, borderRadius: 10 }}
                allowClear
                disabled={!(joinCodeInfo?.allow_member_invite ?? true)}
              />
              <Select
                value={memberRole}
                disabled
                style={{ width: 170 }}
                classNames={{ popup: { root: 'menu-pop-dropdown' } }}
                options={[{ value: 'guest', label: 'guest' }]}
              />
              <Button
                type="primary"
                icon={<PlusOutlined />}
                loading={addingMember}
                onClick={addMember}
                disabled={!memberEmail.trim()}
                style={{ borderRadius: 10 }}
              >
                {t('add_member') || 'Add'}
              </Button>
            </div>
          )}
          <List
            grid={{ gutter: 16, xs: 1, sm: 1, md: 2, lg: 2, xl: 3, xxl: 3 }}
            dataSource={members}
            loading={loading}
            renderItem={(rec) => (
              <List.Item>
                <Card size="small" className="glass-panel hover-lift" style={{ borderRadius: 12, border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <Text strong style={{ fontSize: 14 }}>{rec.user.display_name || rec.user.email}</Text>
                      <Tag color={rec.status === 'active' ? 'green' : 'default'}>{rec.status}</Tag>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      {canManageMembers && rec.status === 'active' && rec.role !== 'owner'
                        && (isOwner || rec.role !== 'space_admin') ? (
                        <Select
                          size="small"
                          value={rec.role}
                          style={{ width: 140 }}
                          classNames={{ popup: { root: 'menu-pop-dropdown' } }}
                          onChange={(v) => changeMemberRole(rec, v as SpaceRole)}
                          options={MEMBER_ROLE_OPTIONS.map((opt) => ({ value: opt, label: opt }))}
                        />
                      ) : (
                        <Tag>{rec.role}</Tag>
                      )}
                      {canManageMembers && rec.status === 'active' && (
                        <Popconfirm
                          title={t('member_remove_confirm') || 'Remove this member?'}
                            onConfirm={() => removeMember(rec)}
                        >
                          <Button type="text" danger size="small">{t('remove') || 'Remove'}</Button>
                        </Popconfirm>
                      )}
                    </div>
                  </div>
                </Card>
              </List.Item>
            )}
            locale={{ emptyText: <div style={{ padding: 40 }}><div style={{ fontSize: 40, color: 'var(--color-border-secondary)', fontFamily: "'Fraunces', serif" }}>K</div><div style={{ marginTop: 12, color: 'var(--color-text-tertiary)' }}>{t('no_members') || '暂无成员'}</div></div> }}
          />
        </Card>
        )}

        {showInvites && canManageInvites && (
          <Card
            title={
              <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 16 }}>
                {t('invite_codes') || 'Access codes'}
              </span>
            }
            styles={{ body: { padding: '24px' } }}
            className="glass-panel hover-lift"
            style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)' }}
            extra={
              <Button type="primary" icon={<PlusOutlined />} size="middle" onClick={() => setInviteOpen(true)} style={{ borderRadius: 8 }}>
                {t('generate_code') || 'Generate code'}
              </Button>
            }
          >
            <List
              grid={{ gutter: 16, xs: 1, sm: 1, md: 2, lg: 2, xl: 3, xxl: 3 }}
              dataSource={invites}
              loading={loading}
              renderItem={(rec) => (
                <List.Item>
                  <Card size="small" className="glass-panel hover-lift" style={{ borderRadius: 12, border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text strong code style={{ fontSize: 15 }}>{rec.display_prefix}…</Text>
                        <Tag color={rec.status === 'active' ? 'green' : 'red'}>{rec.status}</Tag>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Space>
                          <Tag>{rec.role_ceiling}</Tag>
                          <Text type="secondary" style={{ fontSize: 12 }}>{t('invite_uses') || 'Uses'}: {rec.used_count}{rec.max_uses ? ` / ${rec.max_uses}` : ''}</Text>
                        </Space>
                        {rec.status === 'active' && (
                          <Popconfirm
                            title={t('invite_revoke_confirm') || 'Revoke this code?'}
                            onConfirm={() => revokeInvite(rec)}
                          >
                            <Button type="text" danger size="small">
                              {t('revoke') || 'Revoke'}
                            </Button>
                          </Popconfirm>
                        )}
                      </div>
                    </div>
                  </Card>
                </List.Item>
              )}
              locale={{ emptyText: <div style={{ padding: 40 }}><div style={{ fontSize: 40, color: 'var(--color-border-secondary)', fontFamily: "'Fraunces', serif" }}>K</div><div style={{ marginTop: 12, color: 'var(--color-text-tertiary)' }}>{t('no_invites') || '暂无邀请码'}</div></div> }}
            />
          </Card>
        )}
        </div>

        {isOwner && showMembers && (
          <Card
            title={
              <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 16, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <SwapOutlined /> {t('ownership_continuity') || 'Ownership Transfer'}
              </span>
            }
            styles={{ body: { padding: '28px' } }}
            className="glass-panel hover-lift"
            style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)' }}
          >
            <Space direction="vertical" style={{ width: '100%' }} size="large">
              {/* Single Transfer */}
              <div>
                <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('transfer_owner') || 'Transfer Ownership'}</Text>
                <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 13 }}>
                  {ownership?.owner
                    ? (t('current_owner_name', { name: ownership.owner.display_name }) || `Current owner: ${ownership.owner.display_name}`)
                    : (t('current_owner_loading') || 'Loading owner…')}
                </Text>
                {ownership?.pending_transfer ? (
                  <Alert type="info" showIcon message={t('ownership_transfer_pending') || 'Transfer pending'} description={t('ownership_transfer_pending_description') || 'A transfer is already in progress.'} style={{ borderRadius: 10 }} />
                ) : (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <Select
                      showSearch
                      filterOption={false}
                      value={ownerUser}
                      onChange={setOwnerUser}
                      placeholder={t('select_eligible_member') || 'Select eligible member'}
                      style={{ flex: 1, minWidth: 220 }}
                      classNames={{ popup: { root: 'menu-pop-dropdown' } }}
                      options={ownerCandidates.map((c) => ({ value: c.id, label: c.display_name }))}
                    />
                    <Popconfirm title={t('ownership_transfer_confirm') || 'Confirm ownership transfer?'} onConfirm={handleSingleTransfer}>
                      <Button danger loading={transferring} disabled={!ownerUser || !ownership} style={{ borderRadius: 10 }}>
                        {t('transfer_owner') || 'Transfer'}
                      </Button>
                    </Popconfirm>
                  </div>
                )}
              </div>

              {/* Batch Transfer */}
              <div style={{ borderTop: '1px solid var(--color-border-secondary)', paddingTop: 16 }}>
                <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('batch_transfer') || 'Batch Transfer'}</Text>
                <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
                  {t('batch_transfer_select') || 'Select multiple spaces to transfer ownership'}
                </Text>
                <Table
                  size="small"
                  rowSelection={{
                    selectedRowKeys: batchSelectedSpaceIds,
                    onChange: (keys) => setBatchSelectedSpaceIds(keys as string[]),
                  }}
                  columns={[
                    { title: t('space_name') || 'Space', dataIndex: 'name', key: 'name', ellipsis: true },
                    { title: t('kb_status') || 'Status', dataIndex: 'status', key: 'status', width: 100 },
                  ]}
                  dataSource={allSpaces.filter((s) => s.my_role === 'owner' && s.status === 'active')}
                  rowKey="id"
                  pagination={false}
                  style={{ marginBottom: 12 }}
                  locale={{ emptyText: t('no_spaces_selected') || 'No owned spaces available' }}
                />
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Select
                    showSearch
                    filterOption={false}
                    value={batchTargetUser}
                    onChange={setBatchTargetUser}
                    placeholder={t('select_eligible_member') || 'Select new owner'}
                    style={{ flex: 1, minWidth: 220 }}
                    classNames={{ popup: { root: 'menu-pop-dropdown' } }}
                    options={ownerCandidates.map((c) => ({ value: c.id, label: c.display_name }))}
                  />
                  <Popconfirm
                    title={t('batch_transfer_confirm') || 'Confirm batch ownership transfer?'}
                    onConfirm={handleBatchTransfer}
                    disabled={batchSelectedSpaceIds.length === 0 || !batchTargetUser}
                  >
                    <Button
                      type="primary"
                      danger
                      loading={batchTransferring}
                      disabled={batchSelectedSpaceIds.length === 0 || !batchTargetUser}
                      style={{ borderRadius: 10 }}
                    >
                      {t('batch_transfer') || 'Batch Transfer'} ({batchSelectedSpaceIds.length})
                    </Button>
                  </Popconfirm>
                </div>
              </div>
            </Space>
          </Card>
        )}

        <Modal
          title={t('generate_code') || 'Generate access code'}
          open={inviteOpen}
          onOk={createInvite}
          confirmLoading={creatingInvite}
          onCancel={() => setInviteOpen(false)}
          okText={t('create') || 'Create'}
          styles={{ mask: { backdropFilter: 'blur(6px)' } }}
          transitionName="fade"
          style={{ top: 120 }}
        >
          <Space direction="vertical" style={{ width: '100%', padding: '16px 0' }} size="large">
            <div>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('member_role') || 'Role granted on join'}</Text>
              <Select
                size="large"
                value={inviteRole}
                disabled
                style={{ width: '100%', marginTop: 6 }}
                classNames={{ popup: { root: 'menu-pop-dropdown' } }}
                options={[{ value: 'guest', label: 'guest' }]}
              />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('invite_max_uses') || 'Max uses (0 = unlimited)'}</Text>
              <Input
                size="large"
                type="number"
                min={0}
                value={inviteMaxUses}
                onChange={(e) => setInviteMaxUses(Number(e.target.value) || 0)}
                style={{ width: '100%', marginTop: 6, borderRadius: 10 }}
              />
            </div>
          </Space>
        </Modal>

        <Modal
          title={t('code_generated') || 'Access code generated'}
          open={!!generatedCode}
          onCancel={() => setGeneratedCode(null)}
          footer={[
            <Button key="ok" type="primary" onClick={() => setGeneratedCode(null)} size="large" style={{ borderRadius: 10 }}>
              {t('done') || 'Done'}
            </Button>,
          ]}
          styles={{ mask: { backdropFilter: 'blur(6px)' } }}
          transitionName="fade"
          style={{ top: 120 }}
        >
          <div style={{ padding: '16px 0' }}>
            <Paragraph type="warning" style={{ fontSize: 13.5, fontWeight: 500, marginBottom: 12 }}>
              {t('code_generated_hint') || 'Copy this code now — it is shown only once.'}
            </Paragraph>
            <Input.TextArea readOnly value={generatedCode ?? ''} autoSize style={{ borderRadius: 10, fontFamily: 'var(--font-family-mono)', padding: 12 }} />
          </div>
        </Modal>

        <Modal
          title={t('regenerate_join_code') || '重新生成加入码'}
          open={customCodeModalOpen}
          onOk={handleRegenerateCode}
          confirmLoading={regeneratingCode}
          onCancel={() => { setCustomCodeModalOpen(false); setCustomCode(''); }}
          okText={t('regenerate') || '重新生成'}
          styles={{ mask: { backdropFilter: 'blur(6px)' } }}
          transitionName="fade"
          style={{ top: 120 }}
        >
          <div style={{ padding: '16px 0' }}>
            <Alert
              type="warning"
              showIcon
              message={t('regenerate_warning') || '重新生成后，旧加入码将立即失效'}
              style={{ marginBottom: 16, borderRadius: 10 }}
            />
            <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>
              {t('custom_code_hint') || '自定义加入码（留空则系统自动生成）'}
            </Text>
            <Input
              size="large"
              value={customCode}
              onChange={(e) => setCustomCode(e.target.value)}
              placeholder="留空自动生成，如 KP-MYTEAM"
              style={{ marginTop: 8, borderRadius: 10, fontFamily: 'var(--font-family-mono)' }}
              autoComplete="off"
            />
          </div>
        </Modal>
    </AppShell>
  );
}
