/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Button,
  Dropdown,
  Input,
  Modal,
  Tag,
  Typography,
  message as antdMessage,
  type MenuProps,
} from 'antd';
import {
  AppstoreOutlined,
  CheckOutlined,
  DownOutlined,
  LoginOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import { getRateLimitDetails, isAbortError } from '../api/client';
import { useAuthorization, useCapabilities } from '../auth/CapabilityProvider';
import { useSpaceStore } from '../store/spaceStore';

const { Text } = Typography;

function getModalTransitionName(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false;
  return reducedMotion || !('TransitionEvent' in window) ? '' : undefined;
}

function openCreationRequestPage() {
  window.history.pushState({}, '', '/spaces/create');
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export default function SpaceSwitcher({ collapsed = false }: { collapsed?: boolean }) {
  const { t } = useTranslation('common');
  const access = useAuthorization();
  const capabilities = useCapabilities();
  const { spaces, activeSpaceId, setActiveSpace, joinByCode } = useSpaceStore();
  const active = spaces.find((space) => space.id === activeSpaceId) ?? null;
  const canRequestWorkspace = access.has('workspace.creation.request');
  const joinV2Enabled = capabilities.snapshot?.feature_availability.workspace_join_v2 ?? false;
  const modalTransitionName = getModalTransitionName();

  const [joinOpen, setJoinOpen] = useState(false);
  const [code, setCode] = useState('');
  const [joinBusy, setJoinBusy] = useState(false);
  const mountedRef = useRef(true);
  const joinGenerationRef = useRef(0);
  const joinPendingRef = useRef(false);
  const joinControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      joinGenerationRef.current += 1;
      joinPendingRef.current = false;
      joinControllerRef.current?.abort();
    };
  }, []);

  const closeJoin = useCallback(() => {
    joinGenerationRef.current += 1;
    joinPendingRef.current = false;
    joinControllerRef.current?.abort();
    joinControllerRef.current = null;
    setJoinOpen(false);
    setCode('');
    setJoinBusy(false);
  }, []);

  useEffect(() => {
    if (!joinOpen) return undefined;
    const handleDocumentKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeJoin();
    };
    document.addEventListener('keydown', handleDocumentKeyDown);
    return () => document.removeEventListener('keydown', handleDocumentKeyDown);
  }, [closeJoin, joinOpen]);

  const handleSwitch = async (id: string) => {
    if (id === activeSpaceId) return;
    try {
      await setActiveSpace(id);
    } catch {
      antdMessage.error(t('space_switch_failed') || 'Failed to switch space');
    }
  };

  const handleJoin = async () => {
    const normalizedCode = code.trim();
    if (!normalizedCode || joinPendingRef.current) return;
    const generation = ++joinGenerationRef.current;
    const controller = new AbortController();
    joinPendingRef.current = true;
    joinControllerRef.current = controller;
    setJoinBusy(true);
    try {
      const accessRequest = await joinByCode(normalizedCode, controller.signal);
      if (!mountedRef.current || controller.signal.aborted || joinGenerationRef.current !== generation) return;
      antdMessage.success(
        accessRequest.status === 'pending'
          ? (t('space_access_requested') || 'Access request submitted for owner review')
          : (t('space_access_request_exists') || 'Your access request already exists'),
      );
      closeJoin();
    } catch (error: unknown) {
      if (!mountedRef.current || controller.signal.aborted || joinGenerationRef.current !== generation) return;
      if (!isAbortError(error)) {
        const rateLimit = getRateLimitDetails(error);
        antdMessage.error(rateLimit
          ? `${t('rate_limited') || 'Too many requests'}${rateLimit.retryAfterSeconds == null ? '' : ` — retry in ${rateLimit.retryAfterSeconds}s`}`
          : (t('space_join_failed') || 'Invalid or expired access code'));
      }
    } finally {
      if (mountedRef.current && joinGenerationRef.current === generation) {
        joinPendingRef.current = false;
        setJoinBusy(false);
        joinControllerRef.current = null;
      }
    }
  };

  const items: MenuProps['items'] = [
    { key: 'header', type: 'group', label: t('switch_space') || 'Switch space' },
    ...spaces.map((space) => ({
      key: space.id,
      icon: space.id === activeSpaceId ? <CheckOutlined /> : <AppstoreOutlined />,
      label: (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          {space.name}
          {space.status === 'archived' && <Tag color="default">{t('space_archived') || 'Archived'}</Tag>}
        </span>
      ),
      onClick: () => void handleSwitch(space.id),
    })),
    { type: 'divider' as const },
    ...(joinV2Enabled ? [{
      key: 'join',
      icon: <LoginOutlined />,
      label: t('join_space') || 'Join with access code',
      onClick: () => setJoinOpen(true),
    }] : []),
    ...(canRequestWorkspace ? [{
      key: 'create',
      icon: <PlusOutlined />,
      label: t('create_space') || 'Request a workspace',
      onClick: openCreationRequestPage,
    }] : []),
  ];

  return (
    <>
      <Dropdown overlayClassName="ambient-glow" menu={{ items }} trigger={['click']} placement="bottomLeft">
        <Button
          className="hover-lift btn-press"
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

      {(joinOpen || joinBusy) && (
        <Modal
          styles={{ mask: { backdropFilter: 'blur(6px)' } }}
          transitionName={modalTransitionName}
          maskTransitionName={modalTransitionName}
          title={t('join_space') || 'Join with access code'}
          open={joinOpen}
          onOk={() => void handleJoin()}
          okButtonProps={{ loading: joinBusy, disabled: joinBusy }}
          onCancel={closeJoin}
          maskProps={{ onClick: closeJoin }}
          maskClosable
          keyboard
          okText={t('join') || 'Join'}
        >
          <Text type="secondary">
            {t('join_space_hint') || 'Enter the access code shared with you to join a space.'}
          </Text>
          <Input
            autoFocus
            value={code}
            onChange={(event) => setCode(event.target.value)}
            onPressEnter={() => void handleJoin()}
            placeholder={t('access_code') || 'Access code'}
            style={{ marginTop: 12 }}
          />
        </Modal>
      )}
    </>
  );
}
