/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — audit log viewer (reuses /audit/logs/).
import { useEffect, useState, useCallback } from 'react';
import { Card, Table, Tag, Input, Button, Space } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type AuditLog } from '../../api/admin';

export default function AdminAuditPage() {
  const { t } = useTranslation('common');
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionFilter, setActionFilter] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setLogs(await adminApi.auditLogs(actionFilter ? { action: actionFilter } : undefined)); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, [actionFilter]);

  useEffect(() => { refresh(); }, [refresh]);

  const DENY = 'permission_denied';
  const columns = [
    { title: t('kb_created') || 'Time', dataIndex: 'created_at', key: 'created_at', width: 180, render: (d: string) => new Date(d).toLocaleString() },
    { title: 'User', dataIndex: 'user_email', key: 'user_email', render: (v: string) => v || '-' },
    { title: 'Action', dataIndex: 'action', key: 'action', render: (a: string) => <Tag color={a === DENY ? 'red' : a.includes('register') || a.includes('code') ? 'gold' : 'blue'}>{a}</Tag> },
    { title: 'Target', dataIndex: 'target_type', key: 'target_type' },
    { title: 'Role', dataIndex: 'role_used', key: 'role_used', render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  ];

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">{t('admin_audit_title')}</h1>
        <Space>
          <Input.Search placeholder="action e.g. admin_code_register" allowClear value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)} onSearch={refresh} style={{ width: 280 }} />
          <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
        </Space>
      </div>
      <Card styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
        <Table rowKey="id" loading={loading} dataSource={logs} columns={columns} pagination={{ pageSize: 15 }} size="middle" scroll={{ x: 'max-content' }} />
      </Card>
    </div>
  );
}
