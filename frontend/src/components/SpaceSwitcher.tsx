// SpaceSwitcher — V6.0 workspace switcher (SPEC.MD §7.2/§7.3).
// Shows the active knowledge space and lets the user switch, join by access
// code, or (for platform admins) create a new space.

import { useState } from 'react';
import {
  Dropdown,
  Button,
  Modal,
  Input,
  Select,
  Typography,
  Tag,
  message as antdMessage,
  type MenuProps,
} from 'antd';
import {
  DownOutlined,
  PlusOutlined,
  LoginOutlined,
  CheckOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useSpaceStore } from '../store/spaceStore';
import { useAuth } from '../auth/AuthProvider';

const { Text } = Typography;

export default function SpaceSwitcher({ collapsed = false }: { collapsed?: boolean }) {
  const { t } = useTranslation('common');
  const { user } = useAuth();
  const { spaces, activeSpaceId, setActiveSpace, joinByCode, createSpace } = useSpaceStore();

  const isAdmin = !!(user?.roles?.includes('admin') || user?.is_superuser);
  const active = spaces.find((s) => s.id === activeSpaceId) || null;

  const [joinOpen, setJoinOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [newName, setNewName] = useState('');
  const [newCode, setNewCode] = useState('');
  const [newVisibility, setNewVisibility] = useState('private');

  const handleSwitch = async (id: string) => {
    if (id === activeSpaceId) return;
    try {
      await setActiveSpace(id);
    } catch {
      antdMessage.error(t('space_switch_failed') || 'Failed to switch space');
    }
  };

  const handleJoin = async () => {
    if (!code.trim()) return;
    setBusy(true);
    try {
      const space = await joinByCode(code.trim());
      antdMessage.success((t('space_join_success') || 'Joined') + `: ${space.name}`);
      setJoinOpen(false);
      setCode('');
    } catch {
      antdMessage.error(t('space_join_failed') || 'Invalid or expired access code');
    } finally {
      setBusy(false);
    }
  };

  const handleCreate = async () => {
    if (!newName.trim() || !newCode.trim()) return;
    setBusy(true);
    try {
      const space = await createSpace({
        name: newName.trim(),
        code: newCode.trim().toLowerCase().replace(/\s+/g, '-'),
        visibility: newVisibility as any,
      });
      antdMessage.success((t('space_create_success') || 'Space created') + `: ${space.name}`);
      setCreateOpen(false);
      setNewName('');
      setNewCode('');
    } catch (e: any) {
      const detail = e?.response?.data?.code?.[0] || e?.response?.data?.detail;
      antdMessage.error(detail || t('space_create_failed') || 'Failed to create space');
    } finally {
      setBusy(false);
    }
  };

  const items: MenuProps['items'] = [
    {
      key: 'header',
      type: 'group',
      label: t('switch_space') || 'Switch space',
    },
    ...spaces.map((s) => ({
      key: s.id,
      icon: s.id === activeSpaceId ? <CheckOutlined /> : <AppstoreOutlined />,
      label: (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          {s.name}
          {s.status === 'archived' && <Tag color="default">{t('space_archived') || 'Archived'}</Tag>}
        </span>
      ),
      onClick: () => handleSwitch(s.id),
    })),
    { type: 'divider' as const },
    {
      key: 'join',
      icon: <LoginOutlined />,
      label: t('join_space') || 'Join with access code',
      onClick: () => setJoinOpen(true),
    },
    ...(isAdmin
      ? [
          {
            key: 'create',
            icon: <PlusOutlined />,
            label: t('create_space') || 'Create space',
            onClick: () => setCreateOpen(true),
          },
        ]
      : []),
  ];

  return (
    <>
      <Dropdown menu={{ items }} trigger={['click']} placement="bottomLeft">
        <Button
          type="text"
          aria-label={t('switch_space') || 'Switch space'}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            width: collapsed ? 40 : '100%',
            justifyContent: collapsed ? 'center' : 'flex-start',
            height: 38,
            padding: '0 12px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--color-fill)',
            color: 'var(--color-text)',
          }}
        >
          <AppstoreOutlined style={{ color: 'var(--accent-text)', flexShrink: 0 }} />
          {!collapsed && (
            <Text ellipsis style={{ flex: 1, textAlign: 'left', color: 'var(--color-text)', fontSize: 13.5 }}>
              {active ? active.name : t('select_space') || 'Select space'}
            </Text>
          )}
          {!collapsed && <DownOutlined style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }} />}
        </Button>
      </Dropdown>

      <Modal
        title={t('join_space') || 'Join with access code'}
        open={joinOpen}
        onOk={handleJoin}
        confirmLoading={busy}
        onCancel={() => setJoinOpen(false)}
        okText={t('join') || 'Join'}
      >
        <Text type="secondary">
          {t('join_space_hint') || 'Enter the access code shared with you to join a space.'}
        </Text>
        <Input
          autoFocus
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onPressEnter={handleJoin}
          placeholder={t('access_code') || 'Access code'}
          style={{ marginTop: 12 }}
        />
      </Modal>

      <Modal
        title={t('create_space') || 'Create space'}
        open={createOpen}
        onOk={handleCreate}
        confirmLoading={busy}
        onCancel={() => setCreateOpen(false)}
        okText={t('create') || 'Create'}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t('space_name') || 'Space name'}
          />
          <Input
            value={newCode}
            onChange={(e) => setNewCode(e.target.value)}
            placeholder={t('space_code') || 'Short code (e.g. audit-ipo-a)'}
          />
          <Select
            value={newVisibility}
            onChange={setNewVisibility}
            options={[
              { value: 'private', label: t('visibility_private') || 'Private' },
              { value: 'business_line', label: t('visibility_business_line') || 'Business line' },
              { value: 'organization', label: t('visibility_organization') || 'Organization' },
              { value: 'public_demo', label: t('visibility_public_demo') || 'Public demo' },
            ]}
          />
        </div>
      </Modal>
    </>
  );
}
