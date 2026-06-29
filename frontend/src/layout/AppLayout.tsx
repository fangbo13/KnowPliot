import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate } from 'react-router-dom';
import {
  Avatar, Dropdown, Button, Drawer, Modal, Card, Typography,
  Popconfirm, Input, Tooltip, message as antMessage,
} from 'antd';
import {
  MessageOutlined,
  BookOutlined,
  UserOutlined,
  LogoutOutlined,
  SunOutlined,
  MoonOutlined,
  GlobalOutlined,
  RocketOutlined,
  SettingOutlined,
  PlusOutlined,
  DeleteOutlined,
  SearchOutlined,
  MoreOutlined,
  MenuOutlined,
  AppstoreOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  TeamOutlined,
  EditOutlined,
} from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';
import { useTheme } from '../hooks/useTheme';
import { useBreakpoint } from '../hooks/useBreakpoint';
import { useMemo, useCallback, useState, useEffect, useRef } from 'react';
import { useDebounce } from '../hooks/useDebounce';
import { useChatStore } from '../store/chatStore';
import { useSpaceStore } from '../store/spaceStore';
import SpaceSwitcher from '../components/SpaceSwitcher';
import SessionRenameModal from '../components/chat/SessionRenameModal';
import { chatApi } from '../api/chat';
import { getDateGroupKey, getGroupLabel, computeGroupOrder } from '../utils/dateGroup';
import { abortActiveStream } from '../stream/StreamLifecycleManager';
import i18n from '../i18n';
import NetworkStatusBanner from '../components/NetworkStatusBanner';
import ErrorBoundary from '../components/ErrorBoundary';
// V4.0 DEFECT-008: BroadcastChannel cross-tab sync
import { initCrossTabSync, broadcastSessionDelete } from '../sync/crossTabSync';

const { Text } = Typography;

// V4.1 BUG-007: Clamp context/action menu position to viewport bounds.
// Prevents menus from overflowing the screen edge when the user right-clicks near
// the bottom or right side of the viewport. Menu width is ~160px, estimated height ~120px.
// [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-007]
function clampToViewport(x: number, y: number, menuWidth: number = 160, menuHeight: number = 120) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  return {
    x: Math.max(0, Math.min(x, vw - menuWidth)),
    y: Math.max(0, Math.min(y, vh - menuHeight)),
  };
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { sessions, activeSessionId, streamPhase, loadSessions, setActiveSession, resetSession } = useChatStore();
  const isStreaming = streamPhase !== 'idle'; // V3.5: Derived from streamPhase
  // V6.0: active space role drives the "Space Management" menu visibility.
  const activeSpaceRole = useSpaceStore((s) => {
    const sp = s.spaces.find((x) => x.id === s.activeSpaceId);
    return sp?.my_role ?? null;
  });
  const canManageSpace = ['owner', 'super_admin', 'org_admin', 'business_admin'].includes(
    activeSpaceRole || ''
  );
  const { effective, setThemeMode } = useTheme();
  const isDark = effective === 'dark';
  const { t } = useTranslation('common');

  // Sidebar conversation list state
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => {
    return new Set(['7days', '30days', 'earlier']);
  });
  const [contextMenuSession, setContextMenuSession] = useState<{ id: string; title: string; x: number; y: number } | null>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const [sidebarActionMenu, setSidebarActionMenu] = useState<{ sessionId: string; x: number; y: number } | null>(null);
  const sidebarActionMenuRef = useRef<HTMLDivElement>(null);
  const [renameSessionTarget, setRenameSessionTarget] = useState<{ id: string; title: string } | null>(null);

  // Debounced sidebar search
  const debouncedSidebarSearch = useDebounce(sidebarSearch, 300);

  // P1-7: Unified breakpoints
  const bp = useBreakpoint();
  const isMobile = bp.sm;
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

  // V5.0: Sidebar collapse (desktop). Persists across reloads via localStorage.
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(
    () => localStorage.getItem('ey-sidebar-collapsed') === 'true'
  );
  useEffect(() => {
    localStorage.setItem('ey-sidebar-collapsed', String(sidebarCollapsed));
  }, [sidebarCollapsed]);
  const toggleSidebarCollapsed = useCallback(() => setSidebarCollapsed(p => !p), []);

  // Onboarding modal state (no more interactive tour — nav structure changed)
  const [onboardingVisible, setOnboardingVisible] = useState(() => {
    return !localStorage.getItem('ey-onboarding-seen');
  });
  // P0-1: Show skip hint after 5 seconds — prevents modal from feeling like a blocker
  const [showSkipHint, setShowSkipHint] = useState(false);

  // P0-1: ESC key closes onboarding modal + 5-second skip hint timer
  useEffect(() => {
    if (!onboardingVisible) return;
    // Show "跳过" hint after 5 seconds
    const skipTimer = setTimeout(() => setShowSkipHint(true), 5000);
    // ESC key handler
    const handleEscKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleOnboardingClose();
      }
    };
    document.addEventListener('keydown', handleEscKey);
    return () => {
      clearTimeout(skipTimer);
      document.removeEventListener('keydown', handleEscKey);
    };
  }, [onboardingVisible]);

  // Load spaces, then sessions, on mount. V6.0: spaces load first so the active
  // space is resolved before sessions are fetched (the session list is scoped to
  // the active space via the X-Space-Id header).
  useEffect(() => {
    (async () => {
      try {
        await useSpaceStore.getState().loadSpaces();
      } catch {
        // ignore — session load still works via the default-space fallback
      }
      loadSessions();
    })();
    initCrossTabSync(); // V4.0 DEFECT-008: start cross-tab listener
  }, [loadSessions]);

  // V4.1 BUG-011: Removed auto-close after 2 seconds. The drawer now stays open
  // until the user explicitly taps a conversation or presses the close button.
  // Previously, setTimeout auto-close made the onboarding gesture useless.
  // localStorage 'ey-mobile-drawer-seen' flag still prevents re-opening on future visits.
  // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-011]
  useEffect(() => {
    if (isMobile && !localStorage.getItem('ey-mobile-drawer-seen')) {
      setMobileDrawerOpen(true);
      localStorage.setItem('ey-mobile-drawer-seen', 'true');
      // No auto-close timer — user must interact to dismiss
    }
  }, [isMobile]);

  // V4.1 BUG-009: CSS :has() Safari compatibility fallback.
  // Safari <15.4 does not support :has() selector. Detect via CSS.supports()
  // and apply fallback class to the sidebar search affix-wrapper element.
  // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-009]
  useEffect(() => {
    const hasSupport = CSS.supports('selector(:has(*))');
    if (!hasSupport) {
      // Find the affix-wrapper that contains #sidebar-search-input
      const input = document.getElementById('sidebar-search-input');
      if (input) {
        const affixWrapper = input.closest('.ant-input-affix-wrapper');
        if (affixWrapper) {
          affixWrapper.classList.add('sidebar-search-affix-fix');
        }
      }
    }
  }, []);

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenuSession) return;
    const handler = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenuSession(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [contextMenuSession]);

  // Close sidebar action menu on outside click
  useEffect(() => {
    if (!sidebarActionMenu) return;
    const handler = (e: MouseEvent) => {
      if (sidebarActionMenuRef.current && !sidebarActionMenuRef.current.contains(e.target as Node)) {
        setSidebarActionMenu(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [sidebarActionMenu]);

  // Memoize user dropdown menu (header — V4.0 dual-track navigation)
  const userMenu = useMemo(() => {
    const items: any[] = [];

    // V4.0: Knowledge base — HR and Admin both can access
    const hasHRAccess = user?.roles?.includes('hr') || user?.roles?.includes('admin') || user?.is_hr_admin;
    if (hasHRAccess) {
      items.push({
        key: 'knowledge',
        icon: <BookOutlined />,
        label: t('knowledge_base'),
        onClick: () => navigate('/admin/knowledge'),
      });
    }

    // V4.0: Admin Dashboard — Admin only (system domain)
    const hasAdminAccess = user?.roles?.includes('admin') || (user?.is_hr_admin && user?.is_superuser);
    if (hasAdminAccess) {
      items.push({
        key: 'admin-dashboard',
        icon: <AppstoreOutlined />,
        label: t('admin_dashboard') || 'Admin Dashboard',
        onClick: () => navigate('/admin/dashboard'),
      });
      // V6.0: Web Crawler menu item removed (feature retired).
    }

    // V6.0: Space Management — visible to owners / org / business / super admins
    // of the active space (server re-checks every action).
    if (canManageSpace) {
      items.push({
        key: 'space-manage',
        icon: <TeamOutlined />,
        label: t('space_management') || 'Space Management',
        onClick: () => navigate('/spaces/manage'),
      });
    }

    if (hasHRAccess || hasAdminAccess || canManageSpace) {
      items.push({ type: 'divider' as const });
    }

    items.push({
      key: 'profile',
      icon: <SettingOutlined />,
      label: t('user_settings'),
      onClick: () => navigate('/profile'),
    });
    items.push({ type: 'divider' as const });
    items.push({
      key: 'logout',
      icon: <LogoutOutlined />,
      label: t('logout'),
      // V4.1 BUG-014: Only navigate on successful logout. If API fails, stay on
      // current page and show error toast. This prevents stuck-on-broken-login scenario.
      onClick: async () => {
        const success = await logout();
        if (success) {
          navigate('/login');
        } else {
          antMessage.error(t('logout_failed') || 'Logout failed — please try again');
        }
      },
    });

    return { items };
  }, [logout, navigate, t, user?.roles, user?.is_hr_admin, user?.is_superuser, canManageSpace]);

  // V4.1 BUG-015: Theme toggle animation — 0.3s spin transition on icon change.
  // When user clicks the toggle, themeAnimating is set true for 300ms, applying
  // the .theme-toggle-spin CSS class which rotates the icon 180deg.
  // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-015]
  const [themeAnimating, setThemeAnimating] = useState(false);
  const handleThemeToggle = useCallback(() => {
    setThemeAnimating(true);
    setThemeMode(isDark ? 'light' : 'dark');
    setTimeout(() => setThemeAnimating(false), 300);
  }, [isDark, setThemeMode]);

  // Language switch
  const currentLang = i18n.language?.startsWith('zh') ? 'zh' : 'en';
  const handleLangChange = useCallback((lang: 'zh' | 'en') => {
    i18n.changeLanguage(lang);
    localStorage.setItem('ey-language', lang);
  }, []);

  const langMenu = useMemo(() => ({
    items: [
      {
        key: 'zh',
        label: '中文',
        icon: currentLang === 'zh' ? <span style={{ color: 'var(--accent)' }}>●</span> : null,
        onClick: () => handleLangChange('zh'),
      },
      {
        key: 'en',
        label: 'English',
        icon: currentLang === 'en' ? <span style={{ color: 'var(--accent)' }}>●</span> : null,
        onClick: () => handleLangChange('en'),
      },
    ],
  }), [currentLang, handleLangChange]);

  // Onboarding handler
  const handleOnboardingClose = useCallback(() => {
    localStorage.setItem('ey-onboarding-seen', 'true');
    setOnboardingVisible(false);
  }, []);

  // Onboarding feature cards data (simplified — no history/nav references)
  const onboardingFeatures = useMemo(() => [
    { icon: <MessageOutlined style={{ fontSize: 24 }} />, title: t('onboarding_chat_title'), desc: t('onboarding_chat_desc') },
    { icon: <BookOutlined style={{ fontSize: 24 }} />, title: t('onboarding_knowledge_title'), desc: t('onboarding_knowledge_desc') },
    { icon: <UserOutlined style={{ fontSize: 24 }} />, title: t('onboarding_profile_title'), desc: t('onboarding_profile_desc') },
  ], [t]);

  // Filtered and grouped sidebar sessions — V3.5: dynamic month-level grouping
  const sidebarSessions = useMemo(() => {
    const query = debouncedSidebarSearch.toLowerCase();
    const filtered = sessions.filter((s) => {
      if (query && !(s.title || '').toLowerCase().includes(query)) return false;
      return true;
    });

    const groups: Record<string, typeof filtered> = {};
    for (const s of filtered) {
      const gk = getDateGroupKey(s.updatedAt);
      if (!groups[gk]) groups[gk] = [];
      groups[gk].push(s);
    }
    return groups;
  }, [sessions, debouncedSidebarSearch]);

  // V3.5: Dynamic group ordering — recent groups first, then month groups in reverse chronological order
  const groupOrder = useMemo(() => computeGroupOrder(sidebarSessions), [sidebarSessions]);

  // V4.1 BUG-012: Auto-expand collapsed groups that contain search matches.
  // When sidebar search is active, compute which groups have matching sessions
  // and expand them so results are visible. When search is cleared, restore
  // previous collapsed state.
  // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-012]
  const prevCollapsedRef = useRef<Set<string>>(collapsedGroups);
  useEffect(() => {
    if (debouncedSidebarSearch) {
      // Search active: save current state, then expand groups with matches
      prevCollapsedRef.current = new Set(collapsedGroups);
      const matchingGroupKeys = new Set(Object.keys(sidebarSessions));
      setCollapsedGroups(prev => {
        const next = new Set(prev);
        // Remove groups from collapsed set that have search matches
        for (const key of matchingGroupKeys) {
          next.delete(key);
        }
        return next;
      });
    } else {
      // Search cleared: restore previous collapsed state
      setCollapsedGroups(prevCollapsedRef.current);
    }
  }, [debouncedSidebarSearch, sidebarSessions]);

  // Toggle collapsed group
  const toggleGroup = useCallback((key: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  // Handle sidebar session click
  const handleSidebarSessionClick = useCallback((id: string) => {
    setActiveSession(id);
    navigate('/chat');
    setMobileDrawerOpen(false);
    setContextMenuSession(null);
    setSidebarActionMenu(null);
  }, [setActiveSession, navigate]);

  // Handle new chat from sidebar
  const handleNewChat = useCallback(() => {
    resetSession();
    navigate('/chat');
    setMobileDrawerOpen(false);
  }, [resetSession, navigate]);

  // Handle delete session — V3.5 HIGH-002: abort stream if deleting active streaming session
  // V3.6: Edge case guard — force-unlock if send is locked (session creation phase)
  const handleDeleteSession = useCallback(async (id: string) => {
    // V3.5: If deleting the currently active session while streaming, abort the stream first
    if (activeSessionId === id && isStreaming) {
      abortActiveStream();
    }
    // V3.6: Force unlock if send is locked — covers session creation phase where
    // AbortController doesn't manage the createSession fetch
    const chatState = useChatStore.getState();
    if (chatState.isSendLocked) {
      chatState.unlockSend();
      chatState.setStreamPhase('idle');
    }
    try {
      await chatApi.deleteSession(id);
      broadcastSessionDelete(id); // V4.0 DEFECT-008: notify other tabs of session deletion
      loadSessions();
      if (activeSessionId === id) {
        resetSession();
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
    setContextMenuSession(null);
    setSidebarActionMenu(null);
  }, [activeSessionId, isStreaming, loadSessions, resetSession]);

  const openRenameSession = useCallback((session: { id: string; title: string }) => {
    setRenameSessionTarget(session);
    setContextMenuSession(null);
    setSidebarActionMenu(null);
  }, []);

  const handleRenameSession = useCallback(async (nextTitle: string) => {
    if (!renameSessionTarget) return;
    const trimmed = nextTitle.trim();
    if (!trimmed) {
      antMessage.warning(i18n.language?.startsWith('zh') ? '请输入对话标题' : 'Please enter a conversation title');
      return;
    }
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

  // V3.5: Dynamic group labels with month-level i18n support

  // Sidebar header content (reused in Drawer)
  const siderHeader = (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
    <div style={{
      padding: '16px 16px 8px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          background: 'var(--gradient-accent)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          boxShadow: 'var(--shadow-accent)',
        }}>
          {/* FIX-007: Use CSS variable instead of hardcoded #FFFFFF for dark mode consistency */}
          <span style={{ fontSize: 14, fontWeight: 800, color: 'var(--color-text-on-accent)', lineHeight: 1 }}>EY</span>
        </div>
        <h2 style={{
          margin: 0,
          fontSize: 16,
          fontWeight: 600,
          color: 'var(--color-text)',
        }}>KnowPilot</h2>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        {/* V5.0: collapse sidebar button */}
        <Tooltip title={t('collapse_sidebar') || '收起侧栏'} placement="bottom">
          <Button
            type="text"
            size="small"
            icon={<MenuFoldOutlined style={{ fontSize: 14 }} />}
            onClick={toggleSidebarCollapsed}
            aria-label={t('collapse_sidebar') || 'Collapse sidebar'}
            className="sidebar-header-icon"
            style={{ color: 'var(--color-text-secondary)' }}
          />
        </Tooltip>
      </div>
    </div>
      {/* V6.0: workspace switcher — switch space / join by code / create space */}
      <div style={{ padding: '0 12px 8px' }}>
        <SpaceSwitcher collapsed={false} />
      </div>
    </div>
  );

  // Sidebar user area — P0-1 fix: removed duplicate Profile entry, only Logout remains
  // (Profile entry is kept only in the top-right user dropdown per audit recommendation)
  const sidebarUserArea = useMemo(() => {
    return (
      <div
        className="sidebar-user-area"
        style={{
          padding: '8px 12px',
          borderTop: '1px solid var(--color-border-secondary)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          borderRadius: '8px 8px 0 0',
          transition: 'background 0.15s ease',
        }}
      >
        <Avatar icon={<UserOutlined />} size="small" />
        <span style={{
          flex: 1,
          fontSize: 13,
          color: 'var(--color-text)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>{user?.email}</span>
        <Button
          type="text"
          icon={<LogoutOutlined />}
          size="small"
          aria-label={t('logout')}
          style={{ color: 'var(--color-text-secondary)', padding: '0 4px' }}
          onClick={async () => {
            // V4.1 BUG-014: Guard navigation behind successful logout
            const success = await logout();
            if (success) {
              navigate('/login');
            } else {
              antMessage.error(t('logout_failed') || 'Logout failed — please try again');
            }
            setMobileDrawerOpen(false);
          }}
        />
      </div>
    );
  }, [user?.email, logout, navigate, t]);

  // Shared conversation list renderer
  const renderConversationList = () => (
    <>
      {/* Search capsule */}
      <div style={{ padding: '0 12px 8px' }}>
        <Input
          id="sidebar-search-input"
          size="middle"
          placeholder={t('sidebar_search')}
          prefix={<SearchOutlined style={{ fontSize: 14 }} />}
          value={sidebarSearch}
          onChange={(e) => setSidebarSearch(e.target.value)}
          allowClear
          style={{
            borderRadius: 18,
            background: 'var(--color-fill-secondary)',
            border: 'none',
            transition: 'all 0.2s ease',
          }}
          aria-label={t('sidebar_search')}
        />
      </div>

      {/* Grouped conversation list */}
      {sessions.length === 0 ? (
        <div style={{
          padding: '24px 16px',
          textAlign: 'center',
          color: 'var(--color-text-tertiary)',
          fontSize: 12,
        }}>
          {t('sidebar_empty_state')}
        </div>
      ) : (
        // V3.5: Dynamic group ordering with month-level grouping
        groupOrder.map((groupKey) => {
          const groupSessions = sidebarSessions[groupKey];
          if (!groupSessions || groupSessions.length === 0) return null;

          const isCollapsed = collapsedGroups.has(groupKey);
          // V3.5: Dynamic group labels — supports month keys like '2026-05'
          const label = getGroupLabel(groupKey, currentLang);

          return (
            <div key={groupKey} style={{ marginBottom: 4 }}>
              {/* Group header */}
              <div
                onClick={() => toggleGroup(groupKey)}
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: 'var(--color-text-tertiary)',
                  padding: '6px 16px 4px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  userSelect: 'none',
                }}
                role="button"
                aria-expanded={!isCollapsed}
              >
                <span style={{
                  transition: 'transform 0.2s ease',
                  display: 'inline-block',
                  transform: isCollapsed ? 'rotate(-90deg)' : 'rotate(0)',
                  fontSize: 10,
                }}>
                  ▾
                </span>
                {label}
                <span style={{ marginLeft: 'auto', fontWeight: 400, opacity: 0.6 }}>
                  {groupSessions.length}
                </span>
              </div>

              {/* Group items */}
              {!isCollapsed && groupSessions.map((session) => {
                const isActive = session.id === activeSessionId;
                const sessionTitle = session.title || t('new_conversation');
                // P0-2 / #5 enhancement: tooltip with full title + date info
                const tooltipContent = `${sessionTitle} · ${new Date(session.updatedAt).toLocaleDateString()}`;
                return (
                  <Tooltip title={tooltipContent} placement="right" mouseEnterDelay={0.5}>
                  <div
                    key={session.id}
                    className="sidebar-chat-item"
                    onClick={() => handleSidebarSessionClick(session.id)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      // V4.1 BUG-007: Clamp menu position to viewport bounds
                      const clamped = clampToViewport(e.clientX, e.clientY);
                      setContextMenuSession({
                        id: session.id,
                        title: session.title || t('new_conversation'),
                        x: clamped.x,
                        y: clamped.y,
                      });
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '6px 12px',
                      margin: '0 8px',
                      cursor: 'pointer',
                      fontSize: 13,
                      lineHeight: '20px',
                      color: isActive ? 'var(--color-text)' : 'var(--color-text-secondary)',
                      background: isActive ? 'var(--color-fill-secondary)' : 'transparent',
                      fontWeight: isActive ? 600 : 400,
                      borderRadius: 6,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      position: 'relative',
                      transition: 'background 0.15s ease, opacity 0.15s ease',
                      // P0-2: non-active items reduced opacity per DeepSeek audit
                      opacity: isActive ? 1 : 0.6,
                    }}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSidebarSessionClick(session.id);
                    }}
                  >
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {session.title || t('new_conversation')}
                    </span>
                    <div style={{ position: 'relative', flexShrink: 0 }}>
                      <Button
                        type="text"
                        size="small"
                        icon={<MoreOutlined style={{ fontSize: 12 }} />}
                        className="sidebar-more-btn"
                        data-active={isActive}
                        style={{
                          padding: '0 4px',
                          height: 24,
                          minWidth: 24,
                          color: 'var(--color-text-tertiary)',
                          opacity: isActive ? 1 : 0,
                          transition: 'opacity 0.15s ease, background 0.15s ease',
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          const rect = e.currentTarget.getBoundingClientRect();
                          // V4.1 BUG-007: Clamp action menu position to viewport bounds
                          const clamped = clampToViewport(rect.right, rect.bottom, 140);
                          setSidebarActionMenu({
                            sessionId: session.id,
                            x: clamped.x,
                            y: clamped.y,
                          });
                        }}
                      />
                    </div>
                  </div>
                </Tooltip>
                );
              })}
            </div>
          );
        })
      )}
    </>
  );

  return (
    <div style={{ height: '100vh', display: 'flex' }}>
      {/* Onboarding modal for first-time users */}
      <Modal
        open={onboardingVisible}
        onCancel={handleOnboardingClose}
        footer={null}
        centered
        closable
        maskClosable
        width={520}
        className="onboarding-modal"
      >
        <div style={{ textAlign: 'center', padding: '8px 0 16px' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 56,
            height: 56,
            borderRadius: 14,
            background: 'var(--gradient-accent)',
            marginBottom: 16,
            boxShadow: 'var(--shadow-accent-lg)',
          }}>
            {/* FIX-007: Use CSS variable instead of hardcoded #FFFFFF for dark mode consistency */}
            <span style={{ fontSize: 24, fontWeight: 800, color: 'var(--color-text-on-accent)' }}>EY</span>
          </div>
          <Typography.Title level={4} style={{ margin: '0 0 4px', fontWeight: 600 }}>
            {t('onboarding_title')}
          </Typography.Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            {t('onboarding_subtitle')}
          </Text>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 20 }}>
          {onboardingFeatures.map((feature) => (
            <Card
              key={feature.title}
              size="small"
              hoverable
              style={{
                borderRadius: 12,
                borderColor: 'var(--color-border-secondary)',
                textAlign: 'center',
              }}
              styles={{ body: { padding: '16px 12px' } }}
            >
              <div style={{
                width: 44,
                height: 44,
                borderRadius: 10,
                background: 'var(--color-fill-secondary)',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 8,
                color: 'var(--accent)',
              }}>
                {feature.icon}
              </div>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{feature.title}</div>
              <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.4, display: 'block' }}>
                {feature.desc}
              </Text>
            </Card>
          ))}
        </div>

        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <Button
            type="primary"
            size="large"
            icon={<RocketOutlined />}
            onClick={handleOnboardingClose}
            style={{ borderRadius: 12, fontWeight: 500, padding: '0 32px' }}
          >
            {t('onboarding_start')}
          </Button>
          {/* P0-1: Skip hint — shows after 5 seconds so the modal doesn't feel stuck */}
          <div style={{ marginTop: 12 }}>
            {showSkipHint ? (
              <Button
                type="link"
                onClick={handleOnboardingClose}
                style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}
              >
                {t('skip_for_now')}
              </Button>
            ) : (
              <Text type="secondary" style={{ fontSize: 12, opacity: 0.5 }}>
                {t('skip_hint_loading') || '提示将在几秒后出现…'}
              </Text>
            )}
          </div>
        </div>
      </Modal>

      {/* Skip to content link */}
      <a href="#main-content" className="skip-link">
        {t('skip_to_content') || 'Skip to main content'}
      </a>

      {/* Desktop Sidebar — DeepSeek pattern: fixed width flex child */}
      {!isMobile && (
        <div style={{
          // V5.0: animate width to 0 when collapsed; overflow:hidden clips content
          // during the transition so nothing spills into the main area.
          width: sidebarCollapsed ? 0 : 260,
          flexShrink: 0,
          borderRight: sidebarCollapsed ? 'none' : '1px solid var(--color-border-secondary)',
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          background: 'var(--color-bg-container)',
          overflow: 'hidden',
          transition: 'width 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        }}>
          {/* Sidebar header: Logo + icons */}
          {siderHeader}

          {/* New Chat button */}
          <div style={{ padding: '4px 12px 8px' }}>
            <Button
              type="default"
              icon={<PlusOutlined />}
              onClick={handleNewChat}
              block
              size="middle"
              className="new-chat-btn"
            >
              {t('sidebar_new_chat')}
            </Button>
          </div>

          {/* Conversation list area */}
          <div
            className="sidebar-scroll-area"
            style={{
              borderTop: '1px solid var(--color-border-secondary)',
              flex: 1,
              minHeight: 0,
              overflowY: 'auto',
              overflowX: 'hidden',
              padding: '8px 0',
            }}
          >
            {renderConversationList()}
          </div>

          {/* Bottom user area */}
          {sidebarUserArea}
        </div>
      )}

      {/* Mobile Drawer */}
      {isMobile && (
        <Drawer
          placement="left"
          onClose={() => setMobileDrawerOpen(false)}
          open={mobileDrawerOpen}
          width={280}
          styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column' } }}
          title={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: 'var(--gradient-accent)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {/* FIX-007: Use CSS variable instead of hardcoded #FFFFFF for dark mode consistency */}
                  <span style={{ fontSize: 14, fontWeight: 800, color: 'var(--color-text-on-accent)' }}>EY</span>
                </div>
                <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text)' }}>KnowPilot</span>
              </div>
              <div />
            </div>
          }
        >
          {/* New Chat button */}
          <div style={{ padding: '0 16px 8px' }}>
            <Button
              type="default"
              icon={<PlusOutlined />}
              onClick={handleNewChat}
              block
              className="new-chat-btn"
              style={{ margin: 0, width: '100%' }}
            >
              {t('sidebar_new_chat')}
            </Button>
          </div>

          {/* Mobile conversation list */}
          <div
            className="sidebar-scroll-area"
            style={{
              borderTop: '1px solid var(--color-border-secondary)',
              flex: 1,
              minHeight: 0,
              overflowY: 'auto',
              overflowX: 'hidden',
              padding: '8px 0',
          }}>
            {renderConversationList()}
          </div>

          {/* Mobile bottom user area */}
          {sidebarUserArea}
        </Drawer>
      )}

      {/* Main content area — DeepSeek pattern: flex-1 fills remaining space */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        overflow: 'hidden',
      }}>
        {/* Header bar */}
        <div style={{
          background: 'var(--color-bg-container)',
          padding: '0 24px',
          borderBottom: '1px solid var(--color-border-secondary)',
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          height: 56,
          flexShrink: 0,
          transition: 'background 0.3s ease, border-color 0.3s ease',
        }}>
          {/* V5.0: expand sidebar button — desktop only, shown when collapsed.
              marginRight:auto keeps it left while the rest stays right-aligned. */}
          {!isMobile && sidebarCollapsed && (
            <Tooltip title={t('expand_sidebar') || '展开侧栏'} placement="bottomLeft">
              <Button
                type="text"
                icon={<MenuUnfoldOutlined />}
                onClick={toggleSidebarCollapsed}
                aria-label={t('expand_sidebar') || 'Expand sidebar'}
                style={{ marginRight: 'auto', color: 'var(--color-text-secondary)' }}
              />
            </Tooltip>
          )}
          {/* Mobile hamburger button — P1-3: improved icon + larger touch target */}
          {isMobile && (
            <Button
              type="text"
              icon={<MenuOutlined />}
              onClick={() => setMobileDrawerOpen(true)}
              aria-label={t('mobile_menu') || 'Open mobile menu'}
              style={{
                marginRight: 12,
                color: 'var(--color-text)',
                minWidth: 44,
                minHeight: 44,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            />
          )}

          <Dropdown menu={langMenu} placement="bottomRight">
            <Button
              type="text"
              icon={<GlobalOutlined />}
              aria-label={t('language_switch') || 'Switch language'}
              style={{
                color: currentLang === 'zh' ? 'var(--accent)' : 'var(--color-text-secondary)',
                marginRight: 8,
              }}
              title={currentLang === 'zh' ? '切换至 English' : 'Switch to 中文'}
            />
          </Dropdown>
          <Button
            type="text"
            icon={isDark ? <SunOutlined /> : <MoonOutlined />}
            onClick={handleThemeToggle}
            aria-label={isDark ? t('switch_to_light') : t('switch_to_dark')}
            className={themeAnimating ? 'theme-toggle-spin' : ''}
            style={{ marginRight: 16, color: 'var(--color-text-secondary)' }}
            title={isDark ? t('switch_to_light') : t('switch_to_dark')}
          />
          <Dropdown menu={userMenu}>
            <Button
              type="text"
              aria-label={t('user_menu') || 'User menu'}
              style={{
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                padding: '0 8px',
                color: 'var(--color-text)',
              }}
            >
              <Avatar icon={<UserOutlined />} size="small" style={{ marginRight: 8 }} />
              <span style={{
                maxWidth: 200,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>{user?.email}</span>
            </Button>
          </Dropdown>
        </div>

        {/* Content area — fills remaining space */}
        <div style={{
          flex: 1,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <NetworkStatusBanner />
          <main id="main-content" role="main" style={{ flex: 1, minHeight: 0, overflow: 'hidden', padding: 0, display: 'flex', flexDirection: 'column' }}>
            <ErrorBoundary
              title={t('error_boundary_title')}
              description={t('error_boundary_desc')}
              retryText={t('error_boundary_retry')}
            >
              <div className="page-enter" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                <Outlet />
              </div>
            </ErrorBoundary>
          </main>
        </div>
      </div>

      {/* Right-click context menu for sidebar session actions */}
      {contextMenuSession && (
        <div
          ref={contextMenuRef}
          style={{
            position: 'fixed',
            top: contextMenuSession.y,
            left: contextMenuSession.x,
            zIndex: 10000,
            background: 'var(--color-bg-container)',
            borderRadius: 8,
            boxShadow: 'var(--shadow-context-menu)',
            border: '1px solid var(--color-border)',
            padding: '4px 0',
            minWidth: 160,
          }}
        >
          <div
            style={{
              padding: '8px 16px',
              cursor: 'pointer',
              fontSize: 13,
              color: 'var(--color-text-secondary)',
              borderBottom: '1px solid var(--color-border-secondary)',
              marginBottom: 4,
            }}
          >
            {contextMenuSession.title}
          </div>
          <div
            onClick={() => {
              openRenameSession({
                id: contextMenuSession.id,
                title: contextMenuSession.title,
              });
            }}
            style={{
              padding: '8px 16px',
              cursor: 'pointer',
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              color: 'var(--color-text)',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-fill-secondary)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
          >
            <EditOutlined /> {t('sidebar_rename')}
          </div>
          <Popconfirm
            title={t('sidebar_delete')}
            description={t('sidebar_delete_confirm')}
            okText={t('confirm')}
            cancelText={t('cancel')}
            onConfirm={() => handleDeleteSession(contextMenuSession.id)}
          >
            <div
              style={{
                padding: '8px 16px',
                cursor: 'pointer',
                fontSize: 13,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                color: 'var(--color-error)',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-fill-secondary)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              <DeleteOutlined /> {t('sidebar_delete')}
            </div>
          </Popconfirm>
        </div>
      )}

      {/* Three-dot action menu for sidebar session items */}
      {sidebarActionMenu && (
        <div
          ref={sidebarActionMenuRef}
          style={{
            position: 'fixed',
            top: sidebarActionMenu.y,
            left: sidebarActionMenu.x,
            zIndex: 10000,
            background: 'var(--color-bg-container)',
            borderRadius: 8,
            boxShadow: 'var(--shadow-context-menu)',
            border: '1px solid var(--color-border)',
            padding: '4px 0',
            minWidth: 140,
          }}
        >
          <div
            onClick={() => {
              const session = sessions.find((item) => item.id === sidebarActionMenu.sessionId);
              if (!session) {
                setSidebarActionMenu(null);
                return;
              }
              openRenameSession({
                id: session.id,
                title: session.title || t('new_conversation'),
              });
            }}
            style={{
              padding: '8px 16px',
              cursor: 'pointer',
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              color: 'var(--color-text)',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-fill-secondary)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
          >
            <EditOutlined /> {t('sidebar_rename')}
          </div>
          <Popconfirm
            title={t('sidebar_delete')}
            description={t('sidebar_delete_confirm')}
            okText={t('confirm')}
            cancelText={t('cancel')}
            onConfirm={() => handleDeleteSession(sidebarActionMenu.sessionId)}
          >
            <div
              style={{
                padding: '8px 16px',
                cursor: 'pointer',
                fontSize: 13,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                color: 'var(--color-error)',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-fill-secondary)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              <DeleteOutlined /> {t('sidebar_delete')}
            </div>
          </Popconfirm>
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
    </div>
  );
}
