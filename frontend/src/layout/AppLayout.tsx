import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Avatar, Dropdown, Space } from 'antd';
import {
  MessageOutlined,
  HistoryOutlined,
  BookOutlined,
  UserOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { useAuth } from '../auth/AuthProvider';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

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
        onClick: () => {
          logout();
          navigate('/login');
        },
      },
    ],
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="light" breakpoint="lg" collapsedWidth={80}>
        <div style={{ padding: 16, borderBottom: '1px solid #f0f0f0' }}>
          <h2 style={{ color: '#E00033', margin: 0 }}>EY Onboarding</h2>
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
          background: 'white',
          padding: '0 24px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
        }}>
          <Dropdown menu={userMenu}>
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} />
              <span>{user?.email}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 16 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
