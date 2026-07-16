/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AppstoreOutlined,
  BookOutlined,
  BulbOutlined,
  HistoryOutlined,
  MessageOutlined,
  PlusOutlined,
  SearchOutlined,
  SwapOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';

import { useAuthorization } from '../auth/CapabilityProvider';
import { buildManagementEntries } from '../auth/managementEntries';
import { useTheme } from '../hooks/useTheme';
import { useChatStore } from '../store/chatStore';
import { useSpaceStore } from '../store/spaceStore';

interface Command {
  id: string;
  group: 'actions' | 'recent' | 'spaces' | 'navigate';
  label: string;
  icon: React.ReactNode;
  hint?: string;
  keywords?: string;
  run: () => void;
}

const GROUP_ORDER: Command['group'][] = ['actions', 'recent', 'spaces', 'navigate'];

export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const access = useAuthorization();
  const { effective, setThemeMode } = useTheme();
  const sessions = useChatStore((state) => state.sessions);
  const setActiveSession = useChatStore((state) => state.setActiveSession);
  const resetSession = useChatStore((state) => state.resetSession);
  const spaces = useSpaceStore((state) => state.spaces);
  const activeSpaceId = useSpaceStore((state) => state.activeSpaceId);
  const setActiveSpace = useSpaceStore((state) => state.setActiveSpace);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const commands = useMemo<Command[]>(() => {
    const list: Command[] = [];
    const close = () => onClose();

    if (access.has('chat.ask')) {
      list.push({
        id: 'new-chat',
        group: 'actions',
        icon: <PlusOutlined />,
        label: t('sidebar_new_chat') || 'New chat',
        hint: '⇧⌘O',
        keywords: 'new conversation',
        run: () => { resetSession(); navigate('/chat'); close(); },
      });
    }
    list.push({
      id: 'toggle-theme',
      group: 'actions',
      icon: <BulbOutlined />,
      label: effective === 'dark'
        ? (t('switch_to_light') || 'Light theme')
        : (t('switch_to_dark') || 'Dark theme'),
      keywords: 'theme dark light',
      run: () => { setThemeMode(effective === 'dark' ? 'light' : 'dark'); close(); },
    });

    if (access.has('chat.history')) {
      for (const session of sessions) {
        list.push({
          id: `session-${session.id}`,
          group: 'recent',
          icon: <MessageOutlined />,
          label: session.title || (t('new_conversation') || 'New conversation'),
          keywords: session.title || '',
          run: () => { setActiveSession(session.id); navigate('/chat'); close(); },
        });
      }
    }

    for (const space of spaces) {
      list.push({
        id: `space-${space.id}`,
        group: 'spaces',
        icon: <SwapOutlined />,
        label: space.name,
        hint: space.id === activeSpaceId ? t('active', { defaultValue: 'Active' }) : undefined,
        keywords: `space ${space.name}`,
        run: () => { void setActiveSpace(space.id); navigate('/chat'); close(); },
      });
    }

    for (const entry of buildManagementEntries(access, activeSpaceId)) {
      const icon = entry.id === 'knowledge'
        ? <BookOutlined />
        : entry.id === 'workspace'
          ? <TeamOutlined />
          : <AppstoreOutlined />;
      list.push({
        id: `nav-${entry.id}`,
        group: 'navigate',
        icon,
        label: entry.label,
        keywords: `${entry.id} management admin`,
        run: () => { navigate(entry.to); close(); },
      });
    }
    if (access.has('chat.history')) {
      list.push({
        id: 'nav-history',
        group: 'navigate',
        icon: <HistoryOutlined />,
        label: t('nav_history') || 'History',
        keywords: 'history conversations',
        run: () => { navigate('/history'); close(); },
      });
    }
    list.push({
      id: 'nav-profile',
      group: 'navigate',
      icon: <UserOutlined />,
      label: t('user_settings') || 'Settings',
      keywords: 'profile settings',
      run: () => { navigate('/profile'); close(); },
    });
    return list;
  }, [
    access,
    activeSpaceId,
    effective,
    navigate,
    onClose,
    resetSession,
    sessions,
    setActiveSession,
    setActiveSpace,
    setThemeMode,
    spaces,
    t,
  ]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    let recentCount = 0;
    return commands
      .filter((command) => {
        if (normalized) {
          return `${command.label} ${command.keywords ?? ''}`.toLowerCase().includes(normalized);
        }
        if (command.group === 'recent') {
          recentCount += 1;
          return recentCount <= 6;
        }
        return true;
      })
      .sort((left, right) => GROUP_ORDER.indexOf(left.group) - GROUP_ORDER.indexOf(right.group));
  }, [commands, query]);

  useEffect(() => setActiveIndex(0), [query]);
  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActiveIndex(0);
    const timer = window.setTimeout(() => inputRef.current?.focus(), 30);
    return () => window.clearTimeout(timer);
  }, [open]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('.cmdk-item.is-active')?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (!open) return null;

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, filtered.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      filtered[activeIndex]?.run();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
    }
  };

  let previousGroup: Command['group'] | null = null;
  return (
    <div className="cmdk-overlay" onMouseDown={onClose} role="dialog" aria-modal="true" aria-label="Search and commands">
      <div className="cmdk-panel section-enter" onMouseDown={(event) => event.stopPropagation()}>
        <div className="cmdk-input-wrap">
          <SearchOutlined />
          <input
            ref={inputRef}
            className="cmdk-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t('cmdk_placeholder', { defaultValue: 'Search conversations or run a command…' })}
            aria-label="Search and commands"
          />
        </div>
        <div className="cmdk-list" ref={listRef}>
          {filtered.length === 0 && <div className="cmdk-empty">{t('cmdk_empty', { defaultValue: 'No results' })}</div>}
          {filtered.map((command, index) => {
            const header = command.group !== previousGroup
              ? <div className="cmdk-group-label">{command.group}</div>
              : null;
            previousGroup = command.group;
            return (
              <div key={command.id}>
                {header}
                <button
                  type="button"
                  className={`cmdk-item${index === activeIndex ? ' is-active' : ''}`}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={command.run}
                >
                  <span className="cmdk-item-icon">{command.icon}</span>
                  <span className="cmdk-item-label">{command.label}</span>
                  {command.hint && <span className="cmdk-item-hint">{command.hint}</span>}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
