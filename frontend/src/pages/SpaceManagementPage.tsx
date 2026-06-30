/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// SpaceManagementPage — V6.0 (SPEC.MD §7.6).
// Owner/admin view for the active space: edit settings, view members, and
// generate / revoke access (invite) codes. All actions are re-checked server-side.

import { useEffect, useState, useCallback } from 'react';
import {
  Card,
  Table,
  Button,
  Input,
  Select,
  Tag,
  Typography,
  Space,
  Modal,
  Popconfirm,
  Empty,
  message as antdMessage,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useSpaceStore } from '../store/spaceStore';
import {
  spacesApi,
  type SpaceMember,
  type InviteCode,
  type SpaceRole,
} from '../api/spaces';

const { Text, Paragraph } = Typography;

const MANAGE_ROLES: (SpaceRole | null)[] = ['owner', 'super_admin', 'org_admin', 'business_admin'];

export default function SpaceManagementPage() {
  const { t } = useTranslation('common');
  const { activeSpaceId, getActiveSpace, loadSpaces } = useSpaceStore();
  const active = getActiveSpace();

  const canManage = MANAGE_ROLES.includes(active?.my_role ?? null);

  const [members, setMembers] = useState<SpaceMember[]>([]);
  const [invites, setInvites] = useState<InviteCode[]>([]);
  const [loading, setLoading] = useState(false);

  // Settings form
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState('private');
  const [savingSettings, setSavingSettings] = useState(false);

  // Invite creation
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteRole, setInviteRole] = useState<SpaceRole>('member');
  const [inviteMaxUses, setInviteMaxUses] = useState<number>(0);
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [generatedCode, setGeneratedCode] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!activeSpaceId) return;
    setLoading(true);
    try {
      const [m, inv] = await Promise.all([
        spacesApi.members(activeSpaceId).catch(() => []),
        canManage ? spacesApi.listInvites(activeSpaceId).catch(() => []) : Promise.resolve([]),
      ]);
      setMembers(m);
      setInvites(inv);
    } finally {
      setLoading(false);
    }
  }, [activeSpaceId, canManage]);

  useEffect(() => {
    if (active) {
      setName(active.name);
      setDescription(active.description);
      setVisibility(active.visibility);
    }
    refresh();
  }, [active?.id, refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveSettings = async () => {
    if (!activeSpaceId) return;
    setSavingSettings(true);
    try {
      await spacesApi.update(activeSpaceId, { name, description, visibility: visibility as any });
      await loadSpaces();
      antdMessage.success(t('space_settings_saved') || 'Settings saved');
    } catch {
      antdMessage.error(t('space_settings_failed') || 'Failed to save settings');
    } finally {
      setSavingSettings(false);
    }
  };

  const createInvite = async () => {
    if (!activeSpaceId) return;
    setCreatingInvite(true);
    try {
      const inv = await spacesApi.createInvite(activeSpaceId, {
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

  const revokeInvite = async (inviteId: string) => {
    if (!activeSpaceId) return;
    try {
      await spacesApi.revokeInvite(activeSpaceId, inviteId);
      await refresh();
      antdMessage.success(t('invite_revoked') || 'Invite code revoked');
    } catch {
      antdMessage.error(t('invite_revoke_failed') || 'Failed to revoke');
    }
  };

  if (!active) {
    return (
      <div style={{ padding: 24 }}>
        <Empty description={t('no_active_space') || 'No active space selected'} />
      </div>
    );
  }

  const memberColumns = [
    { title: t('member_email') || 'Email', dataIndex: 'user_email', key: 'email' },
    {
      title: t('member_role') || 'Role',
      dataIndex: 'role',
      key: 'role',
      render: (r: string) => <Tag>{r}</Tag>,
    },
    {
      title: t('member_status') || 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag>,
    },
  ];

  const inviteColumns = [
    { title: t('access_code') || 'Code', dataIndex: 'code_prefix', key: 'code', render: (p: string) => `${p}…` },
    { title: t('member_role') || 'Role', dataIndex: 'role', key: 'role', render: (r: string) => <Tag>{r}</Tag> },
    {
      title: t('invite_uses') || 'Uses',
      key: 'uses',
      render: (_: any, rec: InviteCode) => `${rec.used_count}${rec.max_uses ? ` / ${rec.max_uses}` : ''}`,
    },
    {
      title: t('member_status') || 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'red'}>{s}</Tag>,
    },
    {
      title: '',
      key: 'actions',
      render: (_: any, rec: InviteCode) =>
        rec.status === 'active' ? (
          <Popconfirm
            title={t('invite_revoke_confirm') || 'Revoke this code?'}
            onConfirm={() => revokeInvite(rec.id)}
          >
            <Button type="link" danger size="small">
              {t('revoke') || 'Revoke'}
            </Button>
          </Popconfirm>
        ) : null,
    },
  ];
  return (
    <div className="page" style={{ background: 'transparent' }}>
      <div className="page-inner">
        <div className="page-head" style={{ marginBottom: 32 }}>
          <h1 className="page-title">
            {t('space_management') || 'Space Management'} — {active.name}
          </h1>
        </div>

        <Card
          title={
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 16 }}>
              {t('space_settings') || 'Space settings'}
            </span>
          }
          styles={{ body: { padding: '28px' } }}
          style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}
        >
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <div>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('space_name') || 'Space name'}</Text>
              <Input size="large" value={name} onChange={(e) => setName(e.target.value)} disabled={!canManage} style={{ marginTop: 6, borderRadius: 10 }} />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>{t('space_description') || 'Description'}</Text>
              <Input.TextArea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={!canManage}
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
                disabled={!canManage}
                style={{ width: 260, display: 'block', marginTop: 6 }}
                popupClassName="menu-pop-dropdown"
                options={[
                  { value: 'private', label: t('visibility_private') || 'Private' },
                  { value: 'business_line', label: t('visibility_business_line') || 'Business line' },
                  { value: 'organization', label: t('visibility_organization') || 'Organization' },
                  { value: 'public_demo', label: t('visibility_public_demo') || 'Public demo' },
                ]}
              />
            </div>
            {canManage && (
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
          style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}
          extra={<Button icon={<ReloadOutlined />} size="middle" onClick={refresh} style={{ borderRadius: 8 }} />}
        >
          <Table
            rowKey="id"
            loading={loading}
            dataSource={members}
            columns={memberColumns}
            pagination={false}
            size="middle"
          />
        </Card>

        {canManage && (
          <Card
            title={
              <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 16 }}>
                {t('invite_codes') || 'Access codes'}
              </span>
            }
            styles={{ body: { padding: '24px' } }}
            style={{ marginBottom: 24, borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}
            extra={
              <Button type="primary" icon={<PlusOutlined />} size="middle" onClick={() => setInviteOpen(true)} style={{ borderRadius: 8 }}>
                {t('generate_code') || 'Generate code'}
              </Button>
            }
          >
            <Table
              rowKey="id"
              loading={loading}
              dataSource={invites}
              columns={inviteColumns}
              pagination={false}
              size="middle"
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
                popupClassName="menu-pop-dropdown"
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
