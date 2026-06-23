import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Avatar, Dropdown, Space, Button } from 'antd';
import {
  MessageOutlined,
  HistoryOutlined,
  BookOutlined,
  UserOutlined,
  LogoutOutlined,
  SunOutlined,
  MoonOutlined,
} from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';
import { useTheme } from '../hooks/useTheme';
import { useMemo, useCallback } from 'react';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { effective, setThemeMode } = useTheme();
  const isDark = effective === 'dark';
  const { t } = useTranslation('common');

  // Memoize menu items to prevent unnecessary re-renders
  const menuItems = useMemo(() => [
    { key: '/chat', icon: <MessageOutlined />, label: t('nav_chat') },
    { key: '/history', icon: <HistoryOutlined />, label: t('nav_history') },
    ...(user?.is_hr_admin
      ? [{ key: '/admin/knowledge', icon: <BookOutlined />, label: t('nav_knowledge') }]
      : []),
    { key: '/profile', icon: <UserOutlined />, label: t('nav_profile') },
  ], [user?.is_hr_admin, t]);

  // Memoize user dropdown menu
  const userMenu = useMemo(() => ({
    items: [
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: t('logout'),
        onClick: async () => {
          await logout();
          navigate('/login');
        },
      },
    ],
  }), [logout, navigate, t]);

  // Normalize root path to /chat for menu highlight
  const selectedKey = location.pathname === '/' ? '/chat' : location.pathname;

  // Memoize theme toggle handler
  const handleThemeToggle = useCallback(() => {
    setThemeMode(isDark ? 'light' : 'dark');
  }, [isDark, setThemeMode]);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        breakpoint="md"
        collapsedWidth={64}
        style={{
          borderRight: '1px solid var(--color-border-secondary)',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        <div style={{
          padding: 16,
          borderBottom: '1px solid var(--color-border-secondary)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
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
            whiteSpace: 'nowrap',
            transition: 'opacity 0.2s ease',
          }}>Onboarding</h2>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ border: 'none' }}
        />
      </Sider>
      <Layout>
        <Header style={{
          background: 'var(--color-bg-container)',
          padding: '0 24px',
          borderBottom: '1px solid var(--color-border-secondary)',
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          height: 56,
          lineHeight: '56px',
          transition: 'background 0.3s ease, border-color 0.3s ease',
        }}>
          <Button
            type="text"
            icon={isDark ? <SunOutlined /> : <MoonOutlined />}
            onClick={handleThemeToggle}
            aria-label={isDark ? t('switch_to_light') : t('switch_to_dark')}
            style={{ marginRight: 16, color: 'var(--color-text-secondary)' }}
            title={isDark ? t('switch_to_light') : t('switch_to_dark')}
          />
          <Dropdown menu={userMenu}>
            <Space style={{ cursor: 'pointer' }} aria-label={t('user_menu') || 'User menu'}>
              <Avatar icon={<UserOutlined />} />
              <span style={{
                maxWidth: 200,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>{user?.email}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{
          margin: 16,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <div className="page-enter">
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
