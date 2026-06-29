import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate } from 'react-router-dom';
import { Dropdown, Drawer, Modal, Button, Tooltip, message as antMessage } from 'antd';
import {
  MessageOutlined, BookOutlined, UserOutlined, LogoutOutlined,
  SunOutlined, MoonOutlined, GlobalOutlined, SettingOutlined, PlusOutlined,
  DeleteOutlined, SearchOutlined, MoreOutlined, MenuOutlined, AppstoreOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, TeamOutlined, EditOutlined, RocketOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { useMemo, useCallback, useState, useEffect, useRef } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { useTheme } from '../hooks/useTheme';
import { useBreakpoint } from '../hooks/useBreakpoint';
import { useDebounce } from '../hooks/useDebounce';
import { useHotkeys } from '../hooks/useHotkeys';
import { useChatStore } from '../store/chatStore';
import { useSpaceStore } from '../store/spaceStore';
import SpaceSwitcher from '../components/SpaceSwitcher';
import SessionRenameModal from '../components/chat/SessionRenameModal';
import CommandPalette from '../components/CommandPalette';
import { chatApi } from '../api/chat';
import { getDateGroupKey, getGroupLabel, computeGroupOrder } from '../utils/dateGroup';
import { abortActiveStream } from '../stream/StreamLifecycleManager';
import i18n from '../i18n';
import NetworkStatusBanner from '../components/NetworkStatusBanner';
import ErrorBoundary from '../components/ErrorBoundary';
import { initCrossTabSync, broadcastSessionDelete } from '../sync/crossTabSync';

function clampToViewport(x: number, y: number, w = 180, h = 140) {
  return { x: Math.max(8, Math.min(x, window.innerWidth - w - 8)), y: Math.max(8, Math.min(y, window.innerHeight - h - 8)) };
}

function initials(email?: string) {
  return (email?.trim()?.[0] || 'U').toUpperCase();
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { sessions, activeSessionId, streamPhase, loadSessions, setActiveSession, resetSession } = useChatStore();
  const isStreaming = streamPhase !== 'idle';
  const activeSpaceRole = useSpaceStore((s) => s.spaces.find((x) => x.id === s.activeSpaceId)?.my_role ?? null);
  const canManageSpace = ['owner', 'super_admin', 'org_admin', 'business_admin'].includes(activeSpaceRole || '');
  const { effective, setThemeMode } = useTheme();
  const isDark = effective === 'dark';
  const { t } = useTranslation('common');

  const [sidebarSearch, setSidebarSearch] = useState('');
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => new Set(['7days', '30days', 'earlier']));
  const [sessionMenu, setSessionMenu] = useState<{ id: string; title: string; x: number; y: number } | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [renameSessionTarget, setRenameSessionTarget] = useState<{ id: string; title: string } | null>(null);
  const [cmdkOpen, setCmdkOpen] = useState(false);

  const debouncedSidebarSearch = useDebounce(sidebarSearch, 300);
  const bp = useBreakpoint();
  const isMobile = bp.sm;
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => localStorage.getItem('ey-sidebar-collapsed') === 'true');
  useEffect(() => { localStorage.setItem('ey-sidebar-collapsed', String(sidebarCollapsed)); }, [sidebarCollapsed]);
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
    { key: 'o', meta: true, shift: true, allowInInput: true, handler: () => handleNewChat() },
  ]);

  useEffect(() => {
    if (!onboardingVisible) return;
    const skipTimer = setTimeout(() => setShowSkipHint(true), 5000);
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') handleOnboardingClose(); };
    document.addEventListener('keydown', onEsc);
    return () => { clearTimeout(skipTimer); document.removeEventListener('keydown', onEsc); };
  }, [onboardingVisible, handleOnboardingClose]);

  useEffect(() => {
    (async () => {
      try { await useSpaceStore.getState().loadSpaces(); } catch { /* default-space fallback */ }
      loadSessions();
    })();
    initCrossTabSync();
  }, [loadSessions]);

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
    const hasHRAccess = user?.roles?.includes('hr') || user?.roles?.includes('admin') || user?.is_hr_admin;
    if (hasHRAccess) items.push({ key: 'knowledge', icon: <BookOutlined />, label: t('knowledge_base'), onClick: () => navigate('/admin/knowledge') });
    const hasAdminAccess = user?.roles?.includes('admin') || (user?.is_hr_admin && user?.is_superuser);
    if (hasAdminAccess) items.push({ key: 'admin-dashboard', icon: <AppstoreOutlined />, label: t('admin_dashboard') || 'Admin Dashboard', onClick: () => navigate('/admin/dashboard') });
    if (canManageSpace) items.push({ key: 'space-manage', icon: <TeamOutlined />, label: t('space_management') || 'Space Management', onClick: () => navigate('/spaces/manage') });
    if (hasHRAccess || hasAdminAccess || canManageSpace) items.push({ type: 'divider' as const });
    items.push({ key: 'profile', icon: <SettingOutlined />, label: t('user_settings'), onClick: () => navigate('/profile') });
    items.push({ type: 'divider' as const });
    items.push({
      key: 'logout', icon: <LogoutOutlined />, label: t('logout'),
      onClick: async () => {
        const ok = await logout();
        if (ok) navigate('/login');
        else antMessage.error(t('logout_failed') || 'Logout failed — please try again');
      },
    });
    return { items };
  }, [logout, navigate, t, user?.roles, user?.is_hr_admin, user?.is_superuser, canManageSpace]);

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
    if (activeSessionId === id && isStreaming) abortActiveStream();
    const chatState = useChatStore.getState();
    if (chatState.isSendLocked) { chatState.unlockSend(); chatState.setStreamPhase('idle'); }
    try {
      await chatApi.deleteSession(id);
      broadcastSessionDelete(id);
      loadSessions();
      if (activeSessionId === id) resetSession();
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
    closeMenu();
  }, [activeSessionId, isStreaming, loadSessions, resetSession, closeMenu]);

  const openRenameSession = useCallback((session: { id: string; title: string }) => { setRenameSessionTarget(session); closeMenu(); }, [closeMenu]);

  const handleRenameSession = useCallback(async (nextTitle: string) => {
    if (!renameSessionTarget) return;
    const trimmed = nextTitle.trim();
    if (!trimmed) { antMessage.warning(i18n.language?.startsWith('zh') ? '请输入对话标题' : 'Please enter a conversation title'); return; }
    try {
      await chatApi.renameSession(renameSessionTarget.id, trimmed);
      await loadSessions();
      antMessage.success(i18n.language?.startsWith('zh') ? '对话已重命名' : 'Conversation renamed');
      setRenameSessionTarget(null);
    } catch (err) {
      console.error('Failed to rename session:', err);
      antMessage.error(i18n.language?.startsWith('zh') ? '重命名失败，请重试' : 'Rename failed. Please try again');
    }
  }, [loadSessions, renameSessionTarget]);

  const openMenuFromButton = (e: React.MouseEvent, session: { id: string; title: string }) => {
    e.stopPropagation();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const { x, y } = clampToViewport(rect.right - 180, rect.bottom + 4);
    setConfirmingDelete(false);
    setSessionMenu({ id: session.id, title: session.title, x, y });
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
        <div className="sidebar-empty">{t('sidebar_empty_state')}</div>
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
                    onClick={() => handleSidebarSessionClick(session.id)}
                    onContextMenu={(e) => { e.preventDefault(); const { x, y } = clampToViewport(e.clientX, e.clientY); setConfirmingDelete(false); setSessionMenu({ id: session.id, title, x, y }); }}
                    role="button" tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSidebarSessionClick(session.id); }}
                    title={title}
                  >
                    <span className="sidebar-item-title">{title}</span>
                    <button className="sidebar-item-more" aria-label={t('sidebar_rename')} onClick={(e) => openMenuFromButton(e, { id: session.id, title })}><MoreOutlined /></button>
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
        if (ok) navigate('/login'); else antMessage.error(t('logout_failed') || 'Logout failed — please try again');
        setMobileDrawerOpen(false);
      }}><LogoutOutlined /></button>
    </div>
  );

  const newChatBtn = (
    <div className="sidebar-section">
      <button className="new-chat-btn" onClick={handleNewChat}><PlusOutlined />{t('sidebar_new_chat')}</button>
    </div>
  );

  return (
    <div className="app-shell">
      {/* Onboarding */}
      <Modal open={onboardingVisible} onCancel={handleOnboardingClose} footer={null} centered width={560} className="onboarding-modal">
        <div className="onboarding-card">
          <div className="onboarding-mark">K</div>
          <h2 className="onboarding-title">{t('onboarding_title')}</h2>
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
          <Button type="primary" size="large" icon={<RocketOutlined />} onClick={handleOnboardingClose} style={{ borderRadius: 14, padding: '0 30px' }}>
            {t('onboarding_start')}
          </Button>
          <div style={{ marginTop: 12, minHeight: 22 }}>
            {showSkipHint
              ? <button className="msg-action-btn" style={{ margin: '0 auto' }} onClick={handleOnboardingClose}>{t('skip_for_now')}</button>
              : <span style={{ fontSize: 12, color: 'var(--color-text-tertiary)' }}>{t('skip_hint_loading') || ''}</span>}
          </div>
        </div>
      </Modal>

      <a href="#main-content" className="skip-link">{t('skip_to_content') || 'Skip to main content'}</a>

      {/* Desktop sidebar */}
      {!isMobile && (
        <aside className={`sidebar${sidebarCollapsed ? ' is-collapsed' : ''}`}>
          <div className="sidebar-header">
            <div className="sidebar-brand">
              <span className="sidebar-brand-mark">K</span>
              <span className="sidebar-brand-name">KnowPilot</span>
            </div>
            <Tooltip title={`${t('collapse_sidebar') || 'Collapse'}  ⌘B`} placement="bottom">
              <button className="icon-btn" onClick={toggleSidebarCollapsed} aria-label={t('collapse_sidebar') || 'Collapse sidebar'}><MenuFoldOutlined /></button>
            </Tooltip>
          </div>
          <div className="sidebar-section"><SpaceSwitcher collapsed={false} /></div>
          {newChatBtn}
          {renderSearch()}
          {renderList()}
          {renderFooter()}
        </aside>
      )}

      {/* Mobile drawer */}
      {isMobile && (
        <Drawer placement="left" onClose={() => setMobileDrawerOpen(false)} open={mobileDrawerOpen} width={300}
          styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', background: 'var(--color-bg-sunken)' }, header: { display: 'none' } }}>
          <div className="sidebar-header">
            <div className="sidebar-brand"><span className="sidebar-brand-mark">K</span><span className="sidebar-brand-name">KnowPilot</span></div>
            <button className="icon-btn" onClick={() => setMobileDrawerOpen(false)} aria-label={t('cancel') || 'Close'}><CloseOutlined /></button>
          </div>
          <div className="sidebar-section"><SpaceSwitcher collapsed={false} /></div>
          {newChatBtn}
          {renderSearch()}
          {renderList()}
          {renderFooter()}
        </Drawer>
      )}

      {/* Main */}
      <div className="app-main">
        <header className="app-header">
          {!isMobile && sidebarCollapsed && (
            <Tooltip title={`${t('expand_sidebar') || 'Expand'}  ⌘B`} placement="bottomLeft">
              <button className="icon-btn" onClick={toggleSidebarCollapsed} aria-label={t('expand_sidebar') || 'Expand sidebar'}><MenuUnfoldOutlined /></button>
            </Tooltip>
          )}
          {isMobile && <button className="icon-btn" onClick={() => setMobileDrawerOpen(true)} aria-label={t('mobile_menu') || 'Open menu'}><MenuOutlined /></button>}
          <Tooltip title="⌘K" placement="bottom">
            <button className="icon-btn" onClick={() => setCmdkOpen(true)} aria-label={t('cmdk_placeholder', { defaultValue: 'Search' })}><SearchOutlined /></button>
          </Tooltip>

          <span className="spacer" />

          <Dropdown menu={langMenu} placement="bottomRight">
            <button className="icon-btn" aria-label={t('language_switch') || 'Switch language'} style={{ color: currentLang === 'zh' ? 'var(--accent)' : undefined }}><GlobalOutlined /></button>
          </Dropdown>
          <button className="icon-btn" onClick={() => setThemeMode(isDark ? 'light' : 'dark')} aria-label={isDark ? t('switch_to_light') : t('switch_to_dark')} title={isDark ? t('switch_to_light') : t('switch_to_dark')}>
            {isDark ? <SunOutlined /> : <MoonOutlined />}
          </button>
          <Dropdown menu={userMenu} placement="bottomRight">
            <button className="icon-btn" aria-label={t('user_menu') || 'User menu'} style={{ width: 'auto', gap: 8, padding: '0 8px' }}>
              <span className="sidebar-avatar" style={{ width: 26, height: 26, fontSize: 12 }}>{initials(user?.email)}</span>
              {!isMobile && <span style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13, color: 'var(--color-text-secondary)' }}>{user?.email}</span>}
            </button>
          </Dropdown>
        </header>

        <NetworkStatusBanner />
        <main id="main-content" role="main" style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <ErrorBoundary title={t('error_boundary_title')} description={t('error_boundary_desc')} retryText={t('error_boundary_retry')}>
            <div className="page-enter" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <Outlet />
            </div>
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
              <div className="menu-pop-item" onClick={() => openRenameSession({ id: sessionMenu.id, title: sessionMenu.title })}><EditOutlined />{t('sidebar_rename')}</div>
              <div className="menu-pop-item danger" onClick={() => setConfirmingDelete(true)}><DeleteOutlined />{t('sidebar_delete')}</div>
            </>
          )}
        </div>
      )}

      <SessionRenameModal
        open={!!renameSessionTarget}
        initialTitle={renameSessionTarget?.title || ''}
        title={i18n.language?.startsWith('zh') ? '重命名对话' : 'Rename conversation'}
        okText={i18n.language?.startsWith('zh') ? '保存' : 'Save'}
        cancelText={i18n.language?.startsWith('zh') ? '取消' : 'Cancel'}
        placeholder={i18n.language?.startsWith('zh') ? '输入新的对话标题' : 'Enter a new conversation title'}
        onCancel={() => setRenameSessionTarget(null)}
        onConfirm={handleRenameSession}
      />

      <CommandPalette open={cmdkOpen} onClose={() => setCmdkOpen(false)} />
    </div>
  );
}
