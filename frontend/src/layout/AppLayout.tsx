/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate } from 'react-router-dom';
import {
  MessageOutlined, BookOutlined, UserOutlined, LogoutOutlined,
  SunOutlined, MoonOutlined, GlobalOutlined, SettingOutlined, PlusOutlined,
  DeleteOutlined, SearchOutlined, MoreOutlined, MenuOutlined, AppstoreOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, TeamOutlined, EditOutlined, RocketOutlined,
  CloseOutlined,
  PushpinOutlined, DownloadOutlined, FileTextOutlined, HistoryOutlined,
  CompassOutlined, ArrowLeftOutlined,
} from '@ant-design/icons';
import { lazy, Suspense, useMemo, useCallback, useState, useEffect, useRef } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { useAuthorization } from '../auth/CapabilityProvider';
import { buildManagementEntries } from '../auth/managementEntries';
import { useTheme } from '../hooks/useTheme';
import { useBreakpoint } from '../hooks/useBreakpoint';
import { useDebounce } from '../hooks/useDebounce';
import { useHotkeys } from '../hooks/useHotkeys';
import { useChatStore } from '../store/chatStore';
import { useSpaceStore } from '../store/spaceStore';
import { chatApi } from '../api/chat';
import { getDateGroupKey, getGroupLabel, computeGroupOrder } from '../utils/dateGroup';
import { hasActiveStream } from '../stream/StreamLifecycleManager';
import i18n from '../i18n';
import NetworkStatusBanner from '../components/NetworkStatusBanner';
import ErrorBoundary from '../components/ErrorBoundary';
import { initCrossTabSync, broadcastSessionDelete } from '../sync/crossTabSync';
import { notify } from '../utils/notifications';

const SpaceSwitcher = lazy(() => import('../components/SpaceSwitcher'));
const NotificationBell = lazy(() => import('../components/NotificationBell'));
const SessionRenameModal = lazy(() => import('../components/chat/SessionRenameModal'));
const CommandPalette = lazy(() => import('../components/CommandPalette'));
const PageTransition = lazy(() => import('../components/PageTransition'));

function clampToViewport(x: number, y: number, w = 180, h = 140) {
  return { x: Math.max(8, Math.min(x, window.innerWidth - w - 8)), y: Math.max(8, Math.min(y, window.innerHeight - h - 8)) };
}

function initials(email?: string) {
  return (email?.trim()?.[0] || 'U').toUpperCase();
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const access = useAuthorization();
  const navigate = useNavigate();
  const { t } = useTranslation('common');
  const { sessions, activeSessionId, loadSessions, setActiveSession, resetSession } = useChatStore();
  const activeSpaceId = useSpaceStore((state) => state.activeSpaceId);
  const managementEntries = buildManagementEntries(access, activeSpaceId, t);
  const canAsk = access.has('chat.ask');
  const canUseHistory = access.has('chat.history');
  const canExport = access.has('chat.export');
  const { effective, setThemeMode } = useTheme();
  const isDark = effective === 'dark';
  const [shellEnhancementsReady, setShellEnhancementsReady] = useState(false);

  // The route and composer are interactive after the first commit. Secondary
  // workspace/notification controls start loading on the next task so their
  // Ant Design implementation is not part of the authenticated `/chat` entry.
  useEffect(() => {
    const timer = window.setTimeout(() => setShellEnhancementsReady(true), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const [sidebarSearch, setSidebarSearch] = useState('');
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => new Set(['7days', '30days', 'earlier']));
  const [sessionMenu, setSessionMenu] = useState<{ id: string; title: string; isPinned: boolean; x: number; y: number } | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [renameSessionTarget, setRenameSessionTarget] = useState<{ id: string; title: string } | null>(null);
  const [cmdkOpen, setCmdkOpen] = useState(false);

  const debouncedSidebarSearch = useDebounce(sidebarSearch, 300);
  const bp = useBreakpoint();
  const isMobile = bp.sm;
  const isTablet = bp.md && !bp.sm; // 768–1024px
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => localStorage.getItem('ey-sidebar-collapsed') === 'true');
  useEffect(() => { localStorage.setItem('ey-sidebar-collapsed', String(sidebarCollapsed)); }, [sidebarCollapsed]);
  // Auto-collapse sidebar when entering tablet range to maximise content area.
  // The user can still expand it via the toggle button; this only fires on the
  // desktop→tablet transition (isTablet changes), not on every re-render.
  useEffect(() => {
    if (isTablet) setSidebarCollapsed(true);
  }, [isTablet]);
  const toggleSidebarCollapsed = useCallback(() => setSidebarCollapsed((p) => !p), []);

  const [onboardingVisible, setOnboardingVisible] = useState(() => !localStorage.getItem('ey-onboarding-seen'));
  const [showSkipHint, setShowSkipHint] = useState(false);

  const handleOnboardingClose = useCallback(() => {
    localStorage.setItem('ey-onboarding-seen', 'true');
    setOnboardingVisible(false);
  }, []);

  const handleNewChat = useCallback(() => {
    resetSession();
    navigate('/chat');
    setMobileDrawerOpen(false);
  }, [resetSession, navigate]);

  // Global shortcuts: ⌘K palette · ⌘B collapse sidebar · ⌘⇧O new chat
  useHotkeys([
    { key: 'k', meta: true, allowInInput: true, handler: () => setCmdkOpen((o) => !o) },
    { key: 'b', meta: true, allowInInput: true, handler: () => setSidebarCollapsed((p) => !p) },
    { key: 'o', meta: true, shift: true, allowInInput: true, handler: () => { if (canAsk) handleNewChat(); } },
  ]);

  useEffect(() => {
    if (!onboardingVisible) return;
    const skipTimer = setTimeout(() => setShowSkipHint(true), 5000);
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') handleOnboardingClose(); };
    document.addEventListener('keydown', onEsc);
    return () => { clearTimeout(skipTimer); document.removeEventListener('keydown', onEsc); };
  }, [onboardingVisible, handleOnboardingClose]);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try { await useSpaceStore.getState().loadSpaces(controller.signal); } catch { /* route-owned error state */ }
      if (canUseHistory && !controller.signal.aborted) await loadSessions();
    })();
    initCrossTabSync();
    return () => controller.abort();
  }, [canUseHistory, loadSessions]);

  useEffect(() => {
    if (isMobile && !localStorage.getItem('ey-mobile-drawer-seen')) {
      setMobileDrawerOpen(true);
      localStorage.setItem('ey-mobile-drawer-seen', 'true');
    }
  }, [isMobile]);

  const closeMenu = useCallback(() => { setSessionMenu(null); setConfirmingDelete(false); }, []);
  useEffect(() => {
    if (!sessionMenu) return;
    const handler = (e: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(e.target as Node)) closeMenu(); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [sessionMenu, closeMenu]);

  const userMenu = useMemo(() => {
    const items: any[] = [];
    for (const entry of managementEntries) {
      const icon = entry.id === 'console'
        ? <AppstoreOutlined />
        : entry.id === 'workspace'
          ? <TeamOutlined />
          : <BookOutlined />;
      items.push({
        key: `management-${entry.id}`,
        icon,
        label: entry.label,
        onClick: () => navigate(entry.to),
      });
    }
    if (managementEntries.length) items.push({ type: 'divider' as const });
    if (canUseHistory) {
      items.push({ key: 'history', icon: <HistoryOutlined />, label: t('nav_history'), onClick: () => navigate('/history') });
    }
    items.push({ key: 'ownership-transfers', icon: <TeamOutlined />, label: t('ownership_transfers_title'), onClick: () => navigate('/ownership-transfers') });
    items.push({ key: 'discover-spaces', icon: <CompassOutlined />, label: t('space_discovery'), onClick: () => navigate('/spaces/discover') });
    items.push({ key: 'profile', icon: <SettingOutlined />, label: t('user_settings'), onClick: () => navigate('/profile') });
    items.push({ type: 'divider' as const });
    items.push({
      key: 'logout', icon: <LogoutOutlined />, label: t('logout'),
      onClick: async () => {
        const ok = await logout();
        if (ok) navigate('/login');
        else void notify('error', t('logout_failed') || 'Logout failed — please try again');
      },
    });
    return { items };
  }, [canUseHistory, logout, managementEntries, navigate, t]);

  const currentLang = i18n.language?.startsWith('zh') ? 'zh' : 'en';
  const handleLangChange = useCallback((lang: 'zh' | 'en') => { i18n.changeLanguage(lang); localStorage.setItem('ey-language', lang); }, []);
  const langMenu = useMemo(() => ({
    items: [
      { key: 'zh', label: '中文', icon: currentLang === 'zh' ? <span style={{ color: 'var(--accent)' }}>●</span> : null, onClick: () => handleLangChange('zh') },
      { key: 'en', label: 'English', icon: currentLang === 'en' ? <span style={{ color: 'var(--accent)' }}>●</span> : null, onClick: () => handleLangChange('en') },
    ],
  }), [currentLang, handleLangChange]);

  const onboardingFeatures = useMemo(() => [
    { icon: <MessageOutlined />, title: t('onboarding_chat_title'), desc: t('onboarding_chat_desc') },
    { icon: <BookOutlined />, title: t('onboarding_knowledge_title'), desc: t('onboarding_knowledge_desc') },
    { icon: <UserOutlined />, title: t('onboarding_profile_title'), desc: t('onboarding_profile_desc') },
  ], [t]);

  const sidebarSessions = useMemo(() => {
    const query = debouncedSidebarSearch.toLowerCase();
    const filtered = sessions.filter((s) => !query || (s.title || '').toLowerCase().includes(query));
    const groups: Record<string, typeof filtered> = {};
    for (const s of filtered) {
      const gk = getDateGroupKey(s.updatedAt);
      (groups[gk] ||= []).push(s);
    }
    return groups;
  }, [sessions, debouncedSidebarSearch]);
  const groupOrder = useMemo(() => computeGroupOrder(sidebarSessions), [sidebarSessions]);

  const prevCollapsedRef = useRef<Set<string>>(collapsedGroups);
  useEffect(() => {
    if (debouncedSidebarSearch) {
      prevCollapsedRef.current = new Set(collapsedGroups);
      const matching = new Set(Object.keys(sidebarSessions));
      setCollapsedGroups((prev) => { const next = new Set(prev); for (const k of matching) next.delete(k); return next; });
    } else {
      setCollapsedGroups(prevCollapsedRef.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSidebarSearch, sidebarSessions]);

  const toggleGroup = useCallback((key: string) => {
    setCollapsedGroups((prev) => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next; });
  }, []);

  const handleSidebarSessionClick = useCallback((id: string) => {
    setActiveSession(id);
    navigate('/chat');
    setMobileDrawerOpen(false);
    closeMenu();
  }, [setActiveSession, navigate, closeMenu]);

  const handleDeleteSession = useCallback(async (id: string) => {
    const chatState = useChatStore.getState();
    if (hasActiveStream(id)) chatState.abortSessionStream(id);
    try {
      await chatApi.deleteSession(id);
      chatState.removeSessionState(id);
      broadcastSessionDelete(id);
      loadSessions();
      void notify('success', t('session_deleted_success'));
    } catch (err) {
      console.error('Failed to delete session:', err);
      void notify('error', t('session_delete_failed'));
    }
    closeMenu();
  }, [loadSessions, closeMenu, t]);

  const openRenameSession = useCallback((session: { id: string; title: string }) => { setRenameSessionTarget(session); closeMenu(); }, [closeMenu]);

  const handleRenameSession = useCallback(async (nextTitle: string) => {
    if (!renameSessionTarget) return;
    const trimmed = nextTitle.trim();
    if (!trimmed) { void notify('warning', i18n.language?.startsWith('zh') ? '请输入对话标题' : 'Please enter a conversation title'); return; }
    try {
      await chatApi.renameSession(renameSessionTarget.id, trimmed);
      await loadSessions();
      void notify('success', i18n.language?.startsWith('zh') ? '对话已重命名' : 'Conversation renamed');
      setRenameSessionTarget(null);
    } catch (err) {
      console.error('Failed to rename session:', err);
      void notify('error', i18n.language?.startsWith('zh') ? '重命名失败，请重试' : 'Rename failed. Please try again');
    }
  }, [loadSessions, renameSessionTarget]);

  const handlePinSession = useCallback(async (id: string, isPinned: boolean) => {
    await chatApi.pinSession(id, !isPinned);
    await loadSessions();
    closeMenu();
  }, [closeMenu, loadSessions]);

  const handleExportSession = useCallback(async (id: string, format: 'markdown' | 'html') => {
    const blob = await chatApi.exportSession(id, format);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `conversation-${id}.${format === 'markdown' ? 'md' : 'html'}`;
    anchor.click();
    URL.revokeObjectURL(url);
    closeMenu();
  }, [closeMenu]);

  const openMenuFromButton = (e: React.MouseEvent, session: { id: string; title: string; isPinned: boolean }) => {
    e.stopPropagation();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const { x, y } = clampToViewport(rect.right - 180, rect.bottom + 4);
    setConfirmingDelete(false);
    setSessionMenu({ id: session.id, title: session.title, isPinned: session.isPinned, x, y });
  };

  /* ---- sidebar sub-renderers (shared by desktop + mobile drawer) ---- */
  const renderSearch = () => (
    <div className="sidebar-section">
      <div className="sidebar-search">
        <SearchOutlined />
        <input id="sidebar-search-input" value={sidebarSearch} placeholder={t('sidebar_search')} aria-label={t('sidebar_search')} onChange={(e) => setSidebarSearch(e.target.value)} />
        {sidebarSearch && <button className="sidebar-search-clear" onClick={() => setSidebarSearch('')} aria-label={t('cancel') || 'Clear'}><CloseOutlined style={{ fontSize: 12 }} /></button>}
      </div>
    </div>
  );

  const renderList = () => (
    <div className="sidebar-scroll">
      {sessions.length === 0 ? (
        <div className="sidebar-empty">
          <span style={{ display: 'block', marginBottom: 12 }}>{t('sidebar_empty_state')}</span>
        </div>
      ) : (
        groupOrder.map((groupKey) => {
          const groupSessions = sidebarSessions[groupKey];
          if (!groupSessions || groupSessions.length === 0) return null;
          const isCollapsed = collapsedGroups.has(groupKey);
          return (
            <div className="sidebar-group" key={groupKey}>
              <button className="sidebar-group-header" onClick={() => toggleGroup(groupKey)} aria-expanded={!isCollapsed}>
                <span className={`sidebar-group-caret${isCollapsed ? ' is-collapsed' : ''}`}>▾</span>
                {getGroupLabel(groupKey, currentLang)}
                <span className="sidebar-group-count">{groupSessions.length}</span>
              </button>
              {!isCollapsed && groupSessions.map((session) => {
                const isActive = session.id === activeSessionId;
                const title = session.title || t('new_conversation');
                return (
                  <div
                    key={session.id}
                    className={`sidebar-item${isActive ? ' is-active' : ''}`}
                    onContextMenu={(e) => { e.preventDefault(); const { x, y } = clampToViewport(e.clientX, e.clientY); setConfirmingDelete(false); setSessionMenu({ id: session.id, title, isPinned: session.isPinned, x, y }); }}
                    title={title}
                  >
                    <button className="sidebar-item-main" onClick={() => handleSidebarSessionClick(session.id)}>
                      <span className="sidebar-item-title">{session.isPinned && <PushpinOutlined aria-label={t('sidebar_pinned')} />} {title}</span>
                    </button>
                    <button className="sidebar-item-more" aria-label={t('sidebar_rename')} onClick={(e) => openMenuFromButton(e, { id: session.id, title, isPinned: session.isPinned })}><MoreOutlined /></button>
                  </div>
                );
              })}
            </div>
          );
        })
      )}
    </div>
  );

  const renderFooter = () => (
    <div className="sidebar-footer">
      <span className="sidebar-avatar">{initials(user?.email)}</span>
      <span className="sidebar-user-email">{user?.email}</span>
      <button className="icon-btn" style={{ width: 30, height: 30 }} aria-label={t('logout')} onClick={async () => {
        const ok = await logout();
        if (ok) navigate('/login'); else void notify('error', t('logout_failed') || 'Logout failed — please try again');
        setMobileDrawerOpen(false);
      }}><LogoutOutlined /></button>
    </div>
  );

  const newChatBtn = canAsk ? (
    <div className="sidebar-section">
      <button className="new-chat-btn" onClick={handleNewChat}><PlusOutlined />{t('sidebar_new_chat')}</button>
    </div>
  ) : null;

  const renderMenuItems = (items: any[]) => items.map((item, index) => (
    item.type === 'divider'
      ? <div className="menu-pop-divider" role="separator" key={`divider-${index}`} />
      : <button
          type="button"
          className="menu-pop-item"
          key={item.key ?? `menu-${index}`}
          onClick={(event) => {
            item.onClick?.();
            const details = event.currentTarget.closest('details');
            if (details) details.open = false;
          }}
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
  ));

  return (
    <div className="app-shell">
      {/* Onboarding */}
      {onboardingVisible && (
        <div
          className="onboarding-modal"
          role="presentation"
          onMouseDown={(event) => { if (event.target === event.currentTarget) handleOnboardingClose(); }}
          style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'grid', placeItems: 'center', padding: 24, background: 'var(--color-overlay)', backdropFilter: 'blur(6px)' }}
        >
          <section className="onboarding-card" role="dialog" aria-modal="true" aria-labelledby="onboarding-title" style={{ width: 'min(560px, 100%)', maxHeight: 'min(720px, 90vh)', overflow: 'auto' }}>
            <div className="onboarding-mark">K</div>
            <h2 id="onboarding-title" className="onboarding-title">{t('onboarding_title')}</h2>
            <p className="onboarding-sub">{t('onboarding_subtitle')}</p>
            <div className="onboarding-grid">
              {onboardingFeatures.map((f) => (
                <div className="onboarding-feature" key={f.title}>
                  <div className="onboarding-feature-icon">{f.icon}</div>
                  <div className="onboarding-feature-title">{f.title}</div>
                  <div className="onboarding-feature-desc">{f.desc}</div>
                </div>
              ))}
            </div>
            <button type="button" className="primary-btn hover-lift btn-press" onClick={handleOnboardingClose} style={{ borderRadius: 14, padding: '0 30px', minHeight: 44 }}>
              <RocketOutlined aria-hidden="true" /> {t('onboarding_start')}
            </button>
            <div style={{ marginTop: 12, minHeight: 22 }}>
              {showSkipHint
                ? <button className="msg-action-btn" style={{ margin: '0 auto' }} onClick={handleOnboardingClose}>{t('skip_for_now')}</button>
                : <span className="onboarding-skip-hint">{t('skip_hint_loading') || ''}</span>}
            </div>
          </section>
        </div>
      )}

      <a href="#main-content" className="skip-link">{t('skip_to_content') || 'Skip to main content'}</a>

      {/* Desktop sidebar */}
      {!isMobile && (
        <aside className={`sidebar${sidebarCollapsed ? ' is-collapsed' : ''}`}>
          <div className="sidebar-header">
            <div className="sidebar-brand">
              <span className="sidebar-brand-mark">K</span>
              <span className="sidebar-brand-name">KnowPilot</span>
            </div>
            <button className="icon-btn" title={t('collapse_sidebar') || 'Collapse sidebar'} onClick={toggleSidebarCollapsed} aria-label={t('collapse_sidebar') || 'Collapse sidebar'}><MenuFoldOutlined /></button>
          </div>
          <div className="sidebar-section">
            {shellEnhancementsReady ? <Suspense fallback={<div className="sidebar-switcher-placeholder" aria-hidden="true" />}><SpaceSwitcher collapsed={false} /></Suspense> : <div className="sidebar-switcher-placeholder" aria-hidden="true" />}
          </div>
          {newChatBtn}
          {canUseHistory && renderSearch()}
          {canUseHistory && renderList()}
          {renderFooter()}
        </aside>
      )}

      {/* Mobile drawer */}
      {isMobile && mobileDrawerOpen && (
        <div className="mobile-drawer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setMobileDrawerOpen(false); }} style={{ position: 'fixed', inset: 0, zIndex: 900, background: 'var(--color-overlay)' }}>
          <aside role="dialog" aria-modal="true" aria-label={t('mobile_menu') || 'Menu'} style={{ width: 300, height: '100%', background: 'var(--color-bg-sunken)', display: 'flex', flexDirection: 'column' }}>
          <div className="sidebar-header">
            <div className="sidebar-brand"><span className="sidebar-brand-mark">K</span><span className="sidebar-brand-name">KnowPilot</span></div>
            <button className="icon-btn" onClick={() => setMobileDrawerOpen(false)} aria-label={t('cancel') || 'Close'}><CloseOutlined /></button>
          </div>
          <div className="sidebar-section">
            {shellEnhancementsReady ? <Suspense fallback={<div className="sidebar-switcher-placeholder" aria-hidden="true" />}><SpaceSwitcher collapsed={false} /></Suspense> : <div className="sidebar-switcher-placeholder" aria-hidden="true" />}
          </div>
          {newChatBtn}
          {canUseHistory && renderSearch()}
          {canUseHistory && renderList()}
          {renderFooter()}
          </aside>
        </div>
      )}

      {/* Main */}
      <div className="app-main">
        <header className="app-header">
          {!isMobile && sidebarCollapsed && (
            <button className="icon-btn" title={t('expand_sidebar') || 'Expand sidebar'} onClick={toggleSidebarCollapsed} aria-label={t('expand_sidebar') || 'Expand sidebar'}><MenuUnfoldOutlined /></button>
          )}
          {isMobile && <button className="icon-btn" onClick={() => setMobileDrawerOpen(true)} aria-label={t('mobile_menu') || 'Open menu'}><MenuOutlined /></button>}
          <button className="icon-btn" title={t('go_back') || 'Go back'} onClick={() => navigate(-1)} aria-label={t('go_back') || 'Go back'}><ArrowLeftOutlined /></button>
          <button className="icon-btn" title="⌘K" onClick={() => setCmdkOpen(true)} aria-label={t('cmdk_placeholder', { defaultValue: 'Search' })}><SearchOutlined /></button>

          <span className="spacer" />

          <details className="header-menu">
            <summary className="icon-btn" aria-label={t('language_switch') || 'Switch language'} style={{ color: currentLang === 'zh' ? 'var(--accent)' : undefined }}><GlobalOutlined /></summary>
            <div className="menu-pop header-menu-pop">{renderMenuItems(langMenu.items)}</div>
          </details>
          <button className="icon-btn" onClick={() => setThemeMode(isDark ? 'light' : 'dark')} aria-label={isDark ? t('switch_to_light') : t('switch_to_dark')} title={isDark ? t('switch_to_light') : t('switch_to_dark')}>
            {isDark ? <SunOutlined /> : <MoonOutlined />}
          </button>
          {shellEnhancementsReady ? <Suspense fallback={<button className="icon-btn" aria-label={t('notifications_aria') || 'Notifications'} disabled>•</button>}><NotificationBell /></Suspense> : <button className="icon-btn" aria-label={t('notifications_aria') || 'Notifications'} disabled>•</button>}
          <details className="header-menu">
            <summary className="icon-btn" aria-label={t('user_menu') || 'User menu'} style={{ width: 'auto', gap: 8, padding: '0 8px' }}>
              <span className="sidebar-avatar" style={{ width: 26, height: 26, fontSize: 12 }}>{initials(user?.email)}</span>
              {!isMobile && !isTablet && <span style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13, color: 'var(--color-text-secondary)' }}>{user?.email}</span>}
            </summary>
            <div className="menu-pop header-menu-pop">{renderMenuItems(userMenu.items)}</div>
          </details>
        </header>

        <NetworkStatusBanner />
        <main id="main-content" role="main" style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <ErrorBoundary title={t('error_boundary_title')} description={t('error_boundary_desc')} retryText={t('error_boundary_retry')}>
            <Suspense fallback={<div style={{ flex: 1 }} />}>
              <PageTransition>
                <Outlet />
              </PageTransition>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>

      {/* Unified session menu (right-click + three-dot) */}
      {sessionMenu && (
        <div className="menu-pop" ref={menuRef} style={{ top: sessionMenu.y, left: sessionMenu.x }}>
          {confirmingDelete ? (
            <>
              <div className="menu-pop-label">{t('sidebar_delete_confirm')}</div>
              <div className="menu-pop-item" onClick={closeMenu}>{t('cancel')}</div>
              <div className="menu-pop-item danger" onClick={() => handleDeleteSession(sessionMenu.id)}><DeleteOutlined />{t('sidebar_delete')}</div>
            </>
          ) : (
            <>
              <div className="menu-pop-label">{sessionMenu.title}</div>
              <div className="menu-pop-item" onClick={() => handlePinSession(sessionMenu.id, sessionMenu.isPinned)}><PushpinOutlined />{sessionMenu.isPinned ? t('sidebar_unpin') : t('sidebar_pin')}</div>
              {canExport && <div className="menu-pop-item" onClick={() => handleExportSession(sessionMenu.id, 'markdown')}><FileTextOutlined />{t('sidebar_export_markdown')}</div>}
              {canExport && <div className="menu-pop-item" onClick={() => handleExportSession(sessionMenu.id, 'html')}><DownloadOutlined />{t('sidebar_export_html')}</div>}
              <div className="menu-pop-item" onClick={() => openRenameSession({ id: sessionMenu.id, title: sessionMenu.title })}><EditOutlined />{t('sidebar_rename')}</div>
              <div className="menu-pop-item danger" onClick={() => setConfirmingDelete(true)}><DeleteOutlined />{t('sidebar_delete')}</div>
            </>
          )}
        </div>
      )}

      {renameSessionTarget ? (
        <Suspense fallback={null}>
          <SessionRenameModal
            open
            initialTitle={renameSessionTarget.title}
            title={i18n.language?.startsWith('zh') ? '重命名对话' : 'Rename conversation'}
            okText={i18n.language?.startsWith('zh') ? '保存' : 'Save'}
            cancelText={i18n.language?.startsWith('zh') ? '取消' : 'Cancel'}
            placeholder={i18n.language?.startsWith('zh') ? '输入新的对话标题' : 'Enter a new conversation title'}
            onCancel={() => setRenameSessionTarget(null)}
            onConfirm={handleRenameSession}
          />
        </Suspense>
      ) : null}

      {cmdkOpen ? <Suspense fallback={null}><CommandPalette open onClose={() => setCmdkOpen(false)} /></Suspense> : null}
    </div>
  );
}
