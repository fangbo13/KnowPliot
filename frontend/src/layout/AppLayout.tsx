import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate } from 'react-router-dom';
import {
  Avatar, Dropdown, Button, Drawer, Modal, Card, Typography,
  Popconfirm, Input,
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
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';
import { useTheme } from '../hooks/useTheme';
import { useBreakpoint } from '../hooks/useBreakpoint';
import { useMemo, useCallback, useState, useEffect, useRef } from 'react';
import { useDebounce } from '../hooks/useDebounce';
import { useChatStore } from '../store/chatStore';
import { chatApi } from '../api/chat';
import { getDateGroupKey, DATE_GROUP_ORDER } from '../utils/dateGroup';
import i18n from '../i18n';
import NetworkStatusBanner from '../components/NetworkStatusBanner';
import ErrorBoundary from '../components/ErrorBoundary';

const { Text } = Typography;

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { sessions, activeSessionId, loadSessions, setActiveSession, resetSession } = useChatStore();
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

  // Debounced sidebar search
  const debouncedSidebarSearch = useDebounce(sidebarSearch, 300);

  // P1-7: Unified breakpoints
  const bp = useBreakpoint();
  const isMobile = bp.sm;
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

  // Onboarding modal state (no more interactive tour — nav structure changed)
  const [onboardingVisible, setOnboardingVisible] = useState(() => {
    return !localStorage.getItem('ey-onboarding-seen');
  });

  // Load sessions on mount and periodically
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

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

  // Memoize user dropdown menu (header — includes knowledge base for admins)
  const userMenu = useMemo(() => {
    const items: any[] = [];

    // Knowledge base — admin only
    if (user?.is_hr_admin) {
      items.push({
        key: 'knowledge',
        icon: <BookOutlined />,
        label: t('knowledge_base'),
        onClick: () => navigate('/admin/knowledge'),
      });
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
      onClick: async () => {
        await logout();
        navigate('/login');
      },
    });

    return { items };
  }, [logout, navigate, t, user?.is_hr_admin]);

  // Memoize theme toggle handler
  const handleThemeToggle = useCallback(() => {
    setThemeMode(isDark ? 'light' : 'dark');
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
        icon: currentLang === 'zh' ? <span style={{ color: '#0052FF' }}>●</span> : null,
        onClick: () => handleLangChange('zh'),
      },
      {
        key: 'en',
        label: 'English',
        icon: currentLang === 'en' ? <span style={{ color: '#0052FF' }}>●</span> : null,
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

  // Filtered and grouped sidebar sessions
  const sidebarSessions = useMemo(() => {
    const query = debouncedSidebarSearch.toLowerCase();
    const filtered = sessions.filter((s) => {
      if (query && !(s.title || '').toLowerCase().includes(query)) return false;
      return true;
    });

    const groups: Record<string, typeof filtered> = {};
    for (const key of DATE_GROUP_ORDER) {
      groups[key] = [];
    }
    for (const s of filtered) {
      const gk = getDateGroupKey(s.updatedAt);
      groups[gk].push(s);
    }
    return groups;
  }, [sessions, debouncedSidebarSearch]);

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

  // Handle delete session
  const handleDeleteSession = useCallback(async (id: string) => {
    try {
      await chatApi.deleteSession(id);
      loadSessions();
      if (activeSessionId === id) {
        resetSession();
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
    setContextMenuSession(null);
    setSidebarActionMenu(null);
  }, [activeSessionId, loadSessions, resetSession]);

  // Group label i18n key
  const groupLabelKey: Record<string, string> = {
    today: 'sidebar_today',
    yesterday: 'sidebar_yesterday',
    '7days': 'sidebar_7days',
    '30days': 'sidebar_30days',
    earlier: 'sidebar_earlier',
  };

  // Sidebar header content (reused in Drawer)
  const siderHeader = (
    <div style={{
      padding: '16px 16px 8px',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
    }}>
      <div style={{
        width: 32,
        height: 32,
        borderRadius: 8,
        background: 'linear-gradient(135deg, #0052FF, #4D7CFF)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        boxShadow: '0 2px 8px rgba(0, 82, 255, 0.25)',
      }}>
        <span style={{ fontSize: 14, fontWeight: 800, color: '#FFFFFF', lineHeight: 1 }}>EY</span>
      </div>
      <h2 style={{
        margin: 0,
        fontSize: 16,
        fontWeight: 600,
        color: 'var(--color-text)',
      }}>Onboarding</h2>
    </div>
  );

  // Sidebar user area (reused in Drawer)
  const sidebarUserArea = useMemo(() => {
    const userMenuItems: any[] = [
      {
        key: 'profile',
        icon: <SettingOutlined />,
        label: t('user_settings'),
        onClick: () => {
          navigate('/profile');
          setMobileDrawerOpen(false);
        },
      },
      { type: 'divider' as const },
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: t('logout'),
        onClick: async () => {
          await logout();
          navigate('/login');
          setMobileDrawerOpen(false);
        },
      },
    ];

    return (
      <div style={{
        padding: '8px 12px',
        borderTop: '1px solid var(--color-border-secondary)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        cursor: 'pointer',
        borderRadius: '8px 8px 0 0',
        transition: 'background 0.15s ease',
      }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-fill)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
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
        <Dropdown menu={{ items: userMenuItems }} placement="topRight" trigger={['click']}>
          <Button
            type="text"
            icon={<MoreOutlined />}
            size="small"
            aria-label={t('user_settings')}
            style={{ color: 'var(--color-text-secondary)', padding: '0 4px' }}
            onClick={(e) => e.stopPropagation()}
          />
        </Dropdown>
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
          size="small"
          placeholder={t('sidebar_search')}
          prefix={<SearchOutlined style={{ fontSize: 12 }} />}
          value={sidebarSearch}
          onChange={(e) => setSidebarSearch(e.target.value)}
          allowClear
          style={{
            borderRadius: 20,
            background: 'var(--color-fill-secondary)',
            border: 'none',
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
        DATE_GROUP_ORDER.map((groupKey) => {
          const groupSessions = sidebarSessions[groupKey];
          if (!groupSessions || groupSessions.length === 0) return null;

          const isCollapsed = collapsedGroups.has(groupKey);
          const label = t(groupLabelKey[groupKey] || groupKey);

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
                return (
                  <div
                    key={session.id}
                    className="sidebar-chat-item"
                    onClick={() => handleSidebarSessionClick(session.id)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setContextMenuSession({
                        id: session.id,
                        title: session.title || t('new_conversation'),
                        x: e.clientX,
                        y: e.clientY,
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
                      background: isActive ? 'rgba(0, 82, 255, 0.08)' : 'transparent',
                      fontWeight: isActive ? 600 : 400,
                      borderRadius: 6,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      position: 'relative',
                      transition: 'background 0.15s ease',
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) e.currentTarget.style.background = 'var(--color-fill)';
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) e.currentTarget.style.background = 'transparent';
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
                        style={{
                          padding: '0 4px',
                          height: 24,
                          minWidth: 24,
                          color: 'var(--color-text-tertiary)',
                          opacity: isActive ? 1 : 0,
                          transition: 'opacity 0.15s ease',
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          const rect = e.currentTarget.getBoundingClientRect();
                          setSidebarActionMenu({
                            sessionId: session.id,
                            x: rect.right,
                            y: rect.bottom,
                          });
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.opacity = '1';
                          e.currentTarget.style.background = 'var(--color-fill)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.opacity = isActive ? '1' : '0';
                          e.currentTarget.style.background = 'transparent';
                        }}
                      />
                    </div>
                  </div>
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
            background: 'linear-gradient(135deg, #0052FF, #4D7CFF)',
            marginBottom: 16,
            boxShadow: '0 6px 20px rgba(0, 82, 255, 0.25)',
          }}>
            <span style={{ fontSize: 24, fontWeight: 800, color: '#FFFFFF' }}>EY</span>
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
                background: 'rgba(0, 82, 255, 0.08)',
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
        </div>
      </Modal>

      {/* Skip to content link */}
      <a href="#main-content" className="skip-link">
        {t('skip_to_content') || 'Skip to main content'}
      </a>

      {/* Desktop Sidebar — DeepSeek pattern: fixed width flex child */}
      {!isMobile && (
        <div style={{
          width: 260,
          flexShrink: 0,
          borderRight: '1px solid var(--color-border-secondary)',
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          background: 'var(--color-bg-container)',
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
          <div style={{
            borderTop: '1px solid var(--color-border-secondary)',
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            overflowX: 'hidden',
            padding: '8px 0',
          }}>
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: 'linear-gradient(135deg, #0052FF, #4D7CFF)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: '#FFFFFF' }}>EY</span>
              </div>
              <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text)' }}>Onboarding</span>
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
          <div style={{
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
          {/* Mobile hamburger button */}
          {isMobile && (
            <Button
              type="text"
              icon={<MenuUnfoldOutlined />}
              onClick={() => setMobileDrawerOpen(true)}
              aria-label={t('mobile_menu') || 'Open mobile menu'}
              style={{ marginRight: 12, color: 'var(--color-text-secondary)' }}
            />
          )}

          <Dropdown menu={langMenu} placement="bottomRight">
            <Button
              type="text"
              icon={<GlobalOutlined />}
              aria-label={t('language_switch') || 'Switch language'}
              style={{
                color: currentLang === 'zh' ? '#0052FF' : 'var(--color-text-secondary)',
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
          <main id="main-content" role="main" style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column' }}>
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
            boxShadow: '0 6px 16px rgba(0,0,0,0.12)',
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
              setContextMenuSession(null);
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
            <MoreOutlined /> {t('sidebar_rename')}
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
                color: '#ff4d4f',
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
            boxShadow: '0 6px 16px rgba(0,0,0,0.12)',
            border: '1px solid var(--color-border)',
            padding: '4px 0',
            minWidth: 140,
          }}
        >
          <div
            onClick={() => {
              setSidebarActionMenu(null);
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
            <MoreOutlined /> {t('sidebar_rename')}
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
                color: '#ff4d4f',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-fill-secondary)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              <DeleteOutlined /> {t('sidebar_delete')}
            </div>
          </Popconfirm>
        </div>
      )}
    </div>
  );
}
