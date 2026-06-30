/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — users & global roles (reuses rbac endpoints).
import { useEffect, useState, useCallback } from 'react';
import { Card, Table, Button, Tag, Select, Space, Popconfirm, message as antdMessage } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type AdminUser } from '../../api/admin';

export default function AdminUsersPage() {
  const { t } = useTranslation('common');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setUsers(await adminApi.users()); } catch { antdMessage.error(t('load_error') || 'Failed'); } finally { setLoading(false); }
  }, [t]);

  useEffect(() => { refresh(); }, [refresh]);

  const assignRole = async (userId: string, roleName: string) => {
    try { await adminApi.assignRole(userId, roleName); await refresh(); antdMessage.success(t('member_role_updated') || 'Role assigned'); }
    catch { antdMessage.error(t('member_update_failed') || 'Failed'); }
  };

  const deactivate = async (userId: string) => {
    try { await adminApi.deactivateUser(userId); await refresh(); antdMessage.success(t('admin_deactivate_success') || 'User deactivated'); }
    catch { antdMessage.error(t('member_update_failed') || 'Failed'); }
  };

  const activate = async (userId: string) => {
    try { await adminApi.activateUser(userId); await refresh(); antdMessage.success(t('admin_activate_success') || 'User activated'); }
    catch { antdMessage.error(t('member_update_failed') || 'Failed'); }
  };

  const columns = [
    { title: t('email_label') || 'Email', dataIndex: 'email', key: 'email', ellipsis: true },
    { title: t('service_line_label'), dataIndex: 'service_line', key: 'service_line', render: (v: string | null) => v || '-' },
    {
      title: t('member_role') || 'Roles', dataIndex: 'roles', key: 'roles',
      render: (roles: string[], rec: AdminUser) => {
        const all = [...roles];
        if (rec.is_hr_admin && !all.includes('hr')) all.push('hr');
        return all.length ? all.map((r) => <Tag key={r} color={r === 'admin' ? 'red' : r === 'hr' ? 'blue' : 'default'}>{r}</Tag>) : <Tag>employee</Tag>;
      },
    },
    {
      title: t('kb_status') || 'Status', dataIndex: 'is_active', key: 'is_active',
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? t('admin_active') : t('admin_inactive')}</Tag>,
    },
    {
      title: t('admin_role_assign'), key: 'assign',
      render: (_: any, rec: AdminUser) => (
        <Space>
          <Select<string>
            size="small" placeholder={t('admin_role_assign')} style={{ width: 120 }}
            value={undefined}
            onChange={(v) => assignRole(rec.id, v)}
            options={[{ value: 'admin', label: 'admin' }, { value: 'hr', label: 'hr' }]}
          />
          {!rec.is_active && (
            <Button type="link" size="small" onClick={() => activate(rec.id)}>{t('admin_activate')}</Button>
          )}
          {rec.is_active && (
            <Popconfirm title={`${t('admin_deactivate')}?`} onConfirm={() => deactivate(rec.id)}>
              <Button type="link" danger size="small">{t('admin_deactivate')}</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">{t('admin_users_title')}</h1>
        <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
      </div>
      <Card styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
        <Table rowKey="id" loading={loading} dataSource={users} columns={columns} pagination={{ pageSize: 12 }} size="middle" scroll={{ x: 'max-content' }} />
      </Card>
    </div>
  );
}
