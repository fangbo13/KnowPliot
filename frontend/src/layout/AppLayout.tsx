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

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { effective, setThemeMode } = useTheme();
  const isDark = effective === 'dark';

  const menuItems = [
    { key: '/chat', icon: <MessageOutlined />, label: 'Chat' },
    { key: '/history', icon: <HistoryOutlined />, label: 'History' },
    ...(user?.is_hr_admin
      ? [{ key: '/admin/knowledge', icon: <BookOutlined />, label: 'Knowledge Base' }]
      : []),
    { key: '/profile', icon: <UserOutlined />, label: 'Profile' },
  ];

  const userMenu = {
    items: [
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: 'Logout',
        onClick: async () => {
          await logout();
          navigate('/login');
        },
      },
    ],
  };

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
            background: 'linear-gradient(135deg, #FFE500 0%, #FDD800 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 2px 8px rgba(255, 229, 0, 0.25)',
          }}>
            <span style={{ fontSize: 14, fontWeight: 800, color: '#262626', lineHeight: 1 }}>EY</span>
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
          selectedKeys={[location.pathname]}
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
          {/* Dark mode toggle */}
          <Button
            type="text"
            icon={isDark ? <SunOutlined /> : <MoonOutlined />}
            onClick={() => setThemeMode(isDark ? 'light' : 'dark')}
            style={{ marginRight: 16, color: 'var(--color-text-secondary)' }}
            title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          />
          <Dropdown menu={userMenu}>
            <Space style={{ cursor: 'pointer' }}>
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
