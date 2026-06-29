import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  SearchOutlined, PlusOutlined, BulbOutlined, MessageOutlined,
  BookOutlined, AppstoreOutlined, UserOutlined, TeamOutlined, SwapOutlined,
} from '@ant-design/icons';
import { useChatStore } from '../store/chatStore';
import { useSpaceStore } from '../store/spaceStore';
import { useAuth } from '../auth/AuthProvider';
import { useTheme } from '../hooks/useTheme';

interface Cmd {
  id: string;
  group: 'actions' | 'recent' | 'spaces' | 'navigate';
  label: string;
  icon: React.ReactNode;
  hint?: string;
  keywords?: string;
  run: () => void;
}

const GROUP_ORDER: Cmd['group'][] = ['actions', 'recent', 'spaces', 'navigate'];

export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const { user } = useAuth();
  const { effective, setThemeMode } = useTheme();
  const sessions = useChatStore((s) => s.sessions);
  const setActiveSession = useChatStore((s) => s.setActiveSession);
  const resetSession = useChatStore((s) => s.resetSession);
  const spaces = useSpaceStore((s) => s.spaces);
  const activeSpaceId = useSpaceStore((s) => s.activeSpaceId);
  const setActiveSpace = useSpaceStore((s) => s.setActiveSpace);

  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const groupLabels: Record<Cmd['group'], string> = {
    actions: t('cmdk_actions', { defaultValue: 'Actions' }),
    recent: t('cmdk_recent', { defaultValue: 'Recent conversations' }),
    spaces: t('cmdk_spaces', { defaultValue: 'Spaces' }),
    navigate: t('cmdk_navigate', { defaultValue: 'Go to' }),
  };

  const hasHRAccess = user?.roles?.includes('hr') || user?.roles?.includes('admin') || user?.is_hr_admin;
  const hasAdminAccess = user?.roles?.includes('admin') || (user?.is_hr_admin && user?.is_superuser);

  const close = () => { onClose(); };

  const commands = useMemo<Cmd[]>(() => {
    const list: Cmd[] = [];
    list.push({
      id: 'new-chat', group: 'actions', icon: <PlusOutlined />,
      label: t('sidebar_new_chat') || 'New chat', hint: '⌘⇧O', keywords: 'new conversation 新建',
      run: () => { resetSession(); navigate('/chat'); close(); },
    });
    list.push({
      id: 'toggle-theme', group: 'actions', icon: <BulbOutlined />,
      label: effective === 'dark' ? (t('switch_to_light') || 'Light theme') : (t('switch_to_dark') || 'Dark theme'),
      keywords: 'theme dark light 主题 暗色',
      run: () => { setThemeMode(effective === 'dark' ? 'light' : 'dark'); close(); },
    });

    for (const s of sessions) {
      list.push({
        id: `session-${s.id}`, group: 'recent', icon: <MessageOutlined />,
        label: s.title || (t('new_conversation') || 'New conversation'), keywords: s.title || '',
        run: () => { setActiveSession(s.id); navigate('/chat'); close(); },
      });
    }

    for (const sp of spaces) {
      list.push({
        id: `space-${sp.id}`, group: 'spaces', icon: <SwapOutlined />,
        label: sp.name, hint: sp.id === activeSpaceId ? t('active', { defaultValue: 'Active' }) : undefined,
        keywords: `space ${sp.name}`,
        run: () => { setActiveSpace(sp.id); navigate('/chat'); close(); },
      });
    }

    if (hasHRAccess) list.push({ id: 'nav-kb', group: 'navigate', icon: <BookOutlined />, label: t('knowledge_base') || 'Knowledge base', keywords: 'kb documents', run: () => { navigate('/admin/knowledge'); close(); } });
    if (hasAdminAccess) list.push({ id: 'nav-admin', group: 'navigate', icon: <AppstoreOutlined />, label: t('admin_dashboard') || 'Admin dashboard', keywords: 'admin users', run: () => { navigate('/admin/dashboard'); close(); } });
    list.push({ id: 'nav-spaces', group: 'navigate', icon: <TeamOutlined />, label: t('space_management') || 'Space management', keywords: 'space members', run: () => { navigate('/spaces/manage'); close(); } });
    list.push({ id: 'nav-profile', group: 'navigate', icon: <UserOutlined />, label: t('user_settings') || 'Settings', keywords: 'profile settings 设置', run: () => { navigate('/profile'); close(); } });

    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions, spaces, activeSpaceId, effective, user, t]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let items = commands;
    if (q) {
      items = commands.filter((c) => (c.label + ' ' + (c.keywords || '')).toLowerCase().includes(q));
    } else {
      // no query: cap recent conversations to keep the list focused
      let recentCount = 0;
      items = commands.filter((c) => {
        if (c.group === 'recent') { recentCount += 1; return recentCount <= 6; }
        return true;
      });
    }
    return [...items].sort((a, b) => GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group));
  }, [commands, query]);

  useEffect(() => { setActiveIndex(0); }, [query]);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIndex(0);
      const id = window.setTimeout(() => inputRef.current?.focus(), 30);
      return () => window.clearTimeout(id);
    }
  }, [open]);

  useEffect(() => {
    const el = listRef.current?.querySelector('.cmdk-item.is-active') as HTMLElement | null;
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, filtered]);

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex((i) => Math.min(i + 1, filtered.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex((i) => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); filtered[activeIndex]?.run(); }
    else if (e.key === 'Escape') { e.preventDefault(); close(); }
  };

  let lastGroup: Cmd['group'] | null = null;

  return (
    <div className="cmdk-overlay" onMouseDown={close} role="dialog" aria-modal="true" aria-label={t('cmdk_placeholder', { defaultValue: 'Search and commands' })}>
      <div className="cmdk-panel" onMouseDown={(e) => e.stopPropagation()}>
        <div className="cmdk-input-wrap">
          <SearchOutlined />
          <input
            ref={inputRef}
            className="cmdk-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t('cmdk_placeholder', { defaultValue: 'Search conversations or run a command…' })}
            aria-label={t('cmdk_placeholder', { defaultValue: 'Search and commands' })}
          />
        </div>

        <div className="cmdk-list" ref={listRef}>
          {filtered.length === 0 && (
            <div className="cmdk-empty">{t('cmdk_empty', { defaultValue: 'No results' })}</div>
          )}
          {filtered.map((cmd, i) => {
            const header = cmd.group !== lastGroup ? <div className="cmdk-group-label" key={`h-${cmd.group}`}>{groupLabels[cmd.group]}</div> : null;
            lastGroup = cmd.group;
            return (
              <div key={`g-${cmd.id}`}>
                {header}
                <div
                  className={`cmdk-item${i === activeIndex ? ' is-active' : ''}`}
                  onMouseEnter={() => setActiveIndex(i)}
                  onClick={cmd.run}
                  role="button"
                >
                  <span className="cmdk-item-icon">{cmd.icon}</span>
                  <span className="cmdk-item-label">{cmd.label}</span>
                  {cmd.hint && <span className="cmdk-item-hint">{cmd.hint}</span>}
                </div>
              </div>
            );
          })}
        </div>

        <div className="cmdk-footer">
          <span><span className="kbd">↑</span><span className="kbd">↓</span> {t('cmdk_nav_hint', { defaultValue: 'navigate' })}</span>
          <span><span className="kbd">↵</span> {t('cmdk_select_hint', { defaultValue: 'select' })}</span>
          <span><span className="kbd">esc</span> {t('cmdk_close_hint', { defaultValue: 'close' })}</span>
        </div>
      </div>
    </div>
  );
}
