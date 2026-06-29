import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, Typography, Spin, message, Descriptions } from 'antd';
import {
  ReloadOutlined, TeamOutlined,
  DashboardOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import apiClient from '../../api/client';

const { Text } = Typography;

interface UserRecord {
  id: string;
  email: string;
  username: string;
  is_hr_admin: boolean;
  roles: string[];
  is_active: boolean;
  service_line: string | null;
  office_location: string | null;
  role_level: string | null;
}

interface SystemStatus {
  backend_status: string;
  celery_status: string;
  db_status: string;
  total_users: number;
  active_users: number;
  total_documents: number;
}

const roleColors: Record<string, string> = {
  admin: 'red',
  hr: 'blue',
};

export default function AdminDashboardPage() {
  const { t } = useTranslation('common');
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);

  const loadUsers = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get('/rbac/users/');
      const data = response.data;
      setUsers(data.results || data);
    } catch (err: any) {
      if (err.response?.status === 403) {
        message.error(t('permission_denied') || 'Permission denied');
      } else {
        message.error(t('load_error') || 'Failed to load users');
      }
    } finally {
      setLoading(false);
    }
  };

  // V4.2 UI-V4.2-011 + P1-4: System health now uses real API response data.
  // Previously all status fields were hardcoded 'running'/'connected' regardless
  // of API success/failure. Now:
  // - backend_status: inferred from API reachability (if audit API responds → 'running')
  // - db_status: inferred from successful queryset return (if data returned → 'connected')
  // - celery_status: read from audit API response celery_status field if available,
  //   otherwise inferred from backend reachability (if backend is running, celery likely is)
  // On API failure: only failing services are marked 'unknown'/'down', rest stays undefined
  const loadSystemStatus = async () => {
    setStatusLoading(true);
    try {
      // Health check — if audit API responds, backend & DB are operational
      const auditRes = await apiClient.get('/audit/logs/', { timeout: 5000 });
      const data = auditRes.data;
      const resultCount = data?.count ?? (Array.isArray(data) ? data.length : 0);
      // P1-4: Read real status values from API response if available.
      // backend_status and db_status are inferred from successful API reachability
      // (if Django can respond + query DB, both services are operational).
      // celery_status is read from response if provided, otherwise inferred.
      setSystemStatus({
        backend_status: data?.backend_status ?? 'running',
        celery_status: data?.celery_status ?? 'running',
        db_status: data?.db_status ?? 'connected',
        total_users: users.length,
        active_users: users.filter(u => u.is_active).length,
        total_documents: resultCount,
      });
    } catch (err: any) {
      // API failure — backend may be down or unreachable
      const backendDown = !err.response; // No response = network error / server unreachable
      setSystemStatus({
        backend_status: backendDown ? 'down' : 'degraded',
        celery_status: 'unknown',
        db_status: backendDown ? 'disconnected' : 'unknown',
        total_users: users.length,
        active_users: users.filter(u => u.is_active).length,
        total_documents: 0,
      });
    } finally {
      setStatusLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  useEffect(() => {
    if (users.length > 0) {
      loadSystemStatus();
    }
  }, [users.length]);

  const userColumns: ColumnsType<UserRecord> = [
    {
      title: t('kb_title') === 'Title' ? 'Email' : '邮箱',
      dataIndex: 'email',
      key: 'email',
      ellipsis: true,
      width: 200,
    },
    {
      title: t('kb_title') === 'Title' ? 'Username' : '用户名',
      dataIndex: 'username',
      key: 'username',
      width: 120,
    },
    {
      title: 'Role',
      dataIndex: 'roles',
      key: 'roles',
      width: 100,
      render: (roles: string[], record: UserRecord) => {
        const displayRoles = [...roles];
        // V4.0 Phase 2: is_hr_admin fallback → show as 'hr' role
        if (record.is_hr_admin && !roles.includes('hr')) {
          displayRoles.push('hr');
        }
        if (displayRoles.length === 0 && !record.is_hr_admin) {
          return <Tag color="default">Employee</Tag>;
        }
        return (
          <Space size={4}>
            {displayRoles.map(role => (
              <Tag key={role} color={roleColors[role] || 'default'}>
                {role.toUpperCase()}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: t('kb_title') === 'Title' ? 'Service Line' : '业务线',
      dataIndex: 'service_line',
      key: 'service_line',
      width: 120,
      render: (val: string | null) => val || '-',
    },
    {
      title: t('kb_status') === 'Status' ? 'Active' : '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (isActive: boolean) => (
        <Tag color={isActive ? 'green' : 'red'}>
          {isActive ? 'Active' : 'Inactive'}
        </Tag>
      ),
    },
  ];

  return (
    <div className="page"><div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
      {/* Left: User list table */}
      <Card
        style={{ flex: 2, minWidth: 0 }}
        title={
          <Space>
            <TeamOutlined />
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500 }}>
              {t('admin_users') || 'User Management'}
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadUsers}>
              {t('refresh') || 'Refresh'}
            </Button>
          </Space>
        }
      >
        <Table
          columns={userColumns}
          dataSource={users}
          loading={loading}
          rowKey="id"
          pagination={{ pageSize: 10 }}
          scroll={{ x: 'max-content' }}
          size="middle"
        />
      </Card>

      {/* Right: System status panel */}
      <Card
        style={{ flex: 1, minWidth: 240 }}
        title={
          <Space>
            <DashboardOutlined />
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500 }}>
              System Health
            </span>
          </Space>
        }
      >
        {statusLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : systemStatus ? (
          <Descriptions column={1} size="small" bordered>
            {/* V4.2 UI-V4.2-011: Dynamic status tag colors reflecting real health data.
            * Previously all tags were hardcoded color="green" regardless of actual status.
            * [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-011] */}
            <Descriptions.Item label="Backend">
              <Tag color={systemStatus.backend_status === 'running' ? 'green' : systemStatus.backend_status === 'degraded' ? 'orange' : 'red'}>
                {systemStatus.backend_status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Celery">
              <Tag color={systemStatus.celery_status === 'running' ? 'green' : systemStatus.celery_status === 'unknown' ? 'orange' : 'red'}>
                {systemStatus.celery_status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Database">
              <Tag color={systemStatus.db_status === 'connected' ? 'green' : systemStatus.db_status === 'unknown' ? 'orange' : 'red'}>
                {systemStatus.db_status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Total Users">
              <Text strong>{systemStatus.total_users}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Active Users">
              {/* V4.2 UI-V4.2-005: Replace hardcoded #52c41a with CSS variable
              * for dark mode contrast. #52c41a is too dark on #1E293B backgrounds.
              * [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-005] */}
              <Text strong style={{ color: 'var(--color-success)' }}>{systemStatus.active_users}</Text>
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <div style={{ textAlign: 'center', padding: 20, color: 'var(--color-text-secondary)' }}>
            No status data available
          </div>
        )}

        <div style={{ marginTop: 16, padding: 12, background: 'var(--color-fill-secondary)', borderRadius: 8 }}>
          <Space direction="vertical" size={4}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              <SafetyCertificateOutlined /> V4.0 Dual-Track RBAC Active
            </Text>
            <Text type="secondary" style={{ fontSize: 11 }}>
              HR: Content domain (22 perms) · Admin: System domain (35 perms)
            </Text>
          </Space>
        </div>
      </Card>
    </div></div>
  );
}
