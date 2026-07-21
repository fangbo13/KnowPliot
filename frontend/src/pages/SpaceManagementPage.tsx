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
  message as antdMessage,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useSpaceStore } from '../store/spaceStore';
import {
  spacesApi,
  type KnowledgeSpace,
  type SpaceMember,
  type InviteCode,
  type SpaceRole,
} from '../api/spaces';
import { useAuthorization } from '../auth/CapabilityProvider';
import { getRateLimitDetails, isAbortError, withRequestSignal } from '../api/client';

const { Text, Paragraph } = Typography;

export default function SpaceManagementPage() {
  const { t } = useTranslation('common');
  const access = useAuthorization();
  const { spaceId: routeSpaceId } = useParams<{ spaceId: string }>();
  const { activeSpaceId, getActiveSpace, loadSpaces } = useSpaceStore();
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
  const [savingSettings, setSavingSettings] = useState(false);

  // Invite creation
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteRole, setInviteRole] = useState<SpaceRole>('member');
  const [inviteMaxUses, setInviteMaxUses] = useState<number>(20);
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [generatedCode, setGeneratedCode] = useState<string | null>(null);

  // V7.0: add member by email
  const [memberEmail, setMemberEmail] = useState('');
  const [memberRole, setMemberRole] = useState<SpaceRole>('member');
  const [addingMember, setAddingMember] = useState(false);

  const refresh = useCallback(async () => {
    if (!spaceId) return;
    const sequence = ++requestSequence.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setLoadError(null);
    try {
      const [m, inv] = await Promise.all([
        canReadMembers
          ? withRequestSignal(controller.signal, () => spacesApi.members(spaceId))
          : Promise.resolve([]),
        canManageInvites
          ? withRequestSignal(controller.signal, () => spacesApi.listInvites(spaceId))
          : Promise.resolve([]),
      ]);
      if (controller.signal.aborted || sequence !== requestSequence.current) return;
      setMembers(m);
      setInvites(inv);
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

  useEffect(() => {
    // A direct scoped-console route resolves its workspace independently.
    // Starting member/invite reads before that route resource is durable in
    // component state creates an abort/coalescing race: the resource arrival
    // tears down the first read and the replacement can inherit its aborted
    // promise. Wait for the authoritative route workspace before reading.
    if (!active) return;
    setName(active.name);
    setDescription(active.description);
    setVisibility(active.visibility);
    refresh();
    return () => {
      requestSequence.current += 1;
      controllerRef.current?.abort();
    };
  }, [active?.id, refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveSettings = async () => {
    if (!spaceId) return;
    setSavingSettings(true);
    try {
      await spacesApi.update(spaceId, { name, description, visibility: visibility as any });
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

  // Roles assignable to a space member from this page.
  const MEMBER_ROLE_OPTIONS = ['knowledge_admin', 'reviewer', 'member', 'guest'];

  if (!active) {
    return (
      <div className="page section-enter" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontSize: 48, color: 'var(--color-border-secondary)', fontFamily: "'Fraunces', serif" }}>K</div>
        <div style={{ marginTop: 16, color: 'var(--color-text-secondary)', fontSize: 16 }}>
          {spaceLoading
            ? (t('loading') || 'Loading workspace…')
            : spaceLoadFailed
              ? (t('load_error') || 'Unable to load workspace data')
              : (t('no_active_space') || 'No active space selected')}
        </div>
      </div>
    );
  }


  return (
    <div className="page" style={{ background: 'transparent' }}>
      <div className="page-inner">
        <div className="page-head" style={{ marginBottom: 32 }}>
          <h1 className="page-title">
            {t('space_management') || 'Space Management'} — {active.name}
          </h1>
        </div>
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
            {canManageSettings && (
              <Button type="primary" loading={savingSettings} onClick={saveSettings} size="large" style={{ height: 44, borderRadius: 12, fontWeight: 600, padding: '0 24px', marginTop: 8 }}>
                {t('save') || 'Save'}
              </Button>
            )}
          </Space>
        </Card>

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
            <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
              <Input
                placeholder={t('member_email_placeholder') || 'Add member by email…'}
                value={memberEmail}
                onChange={(e) => setMemberEmail(e.target.value)}
                onPressEnter={addMember}
                style={{ flex: 1, minWidth: 220, borderRadius: 10 }}
                allowClear
              />
              <Select
                value={memberRole}
                onChange={(v) => setMemberRole(v as SpaceRole)}
                style={{ width: 170 }}
                classNames={{ popup: { root: 'menu-pop-dropdown' } }}
                options={MEMBER_ROLE_OPTIONS.map((opt) => ({ value: opt, label: opt }))}
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
                      {canManageMembers && rec.status === 'active' ? (
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

        {canManageInvites && (
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
                onChange={(v) => setInviteRole(v as SpaceRole)}
                style={{ width: '100%', marginTop: 6 }}
                classNames={{ popup: { root: 'menu-pop-dropdown' } }}
                options={[
                  { value: 'member', label: 'member' },
                  { value: 'guest', label: 'guest' },
                  { value: 'reviewer', label: 'reviewer' },
                  { value: 'knowledge_admin', label: 'knowledge_admin' },
                ]}
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
      </div>
    </div>
  );
}
