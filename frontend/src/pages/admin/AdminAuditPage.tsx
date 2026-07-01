/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — audit log viewer (reuses /audit/logs/).
import { useEffect, useState, useCallback } from 'react';
import { Card, Table, Tag, Input, Button, Space, Select, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type AuditLog } from '../../api/admin';

export default function AdminAuditPage() {
  const { t } = useTranslation('common');
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionFilter, setActionFilter] = useState('');
  const [resultFilter, setResultFilter] = useState<string | undefined>();
  const [organizationFilter, setOrganizationFilter] = useState('');
  const [businessLineFilter, setBusinessLineFilter] = useState('');
  const [spaceFilter, setSpaceFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setLogs(await adminApi.auditLogs({
        ...(actionFilter ? { action: actionFilter } : {}),
        ...(resultFilter ? { result: resultFilter as 'success' | 'denied' | 'failure' } : {}),
        ...(organizationFilter ? { organization: organizationFilter } : {}),
        ...(businessLineFilter ? { business_line: businessLineFilter } : {}),
        ...(spaceFilter ? { space: spaceFilter } : {}),
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      }));
    } catch {
      message.error('Failed to load audit logs');
    } finally {
      setLoading(false);
    }
  }, [
    actionFilter,
    resultFilter,
    organizationFilter,
    businessLineFilter,
    spaceFilter,
    dateFrom,
    dateTo,
  ]);

  useEffect(() => { refresh(); }, [refresh]);

  const DENY = 'permission_denied';
  const columns = [
    { title: t('kb_created') || 'Time', dataIndex: 'created_at', key: 'created_at', width: 180, render: (d: string) => new Date(d).toLocaleString() },
    { title: 'User', dataIndex: 'user_email', key: 'user_email', render: (v: string) => v || '-' },
    { title: 'Action', dataIndex: 'action', key: 'action', render: (a: string) => <Tag color={a === DENY ? 'red' : a.includes('register') || a.includes('code') ? 'gold' : 'blue'}>{a}</Tag> },
    { title: 'Result', dataIndex: 'result', key: 'result', render: (v: string) => <Tag color={v === 'denied' || v === 'failure' ? 'red' : 'green'}>{v}</Tag> },
    { title: 'Target', dataIndex: 'target_type', key: 'target_type' },
    { title: 'Space', dataIndex: 'space_id', key: 'space_id', render: (v: string | null) => v || '-' },
    { title: 'Role', dataIndex: 'role_used', key: 'role_used', render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  ];

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">{t('admin_audit_title')}</h1>
        <Space wrap>
          <Input.Search placeholder="action e.g. admin_code_register" allowClear value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)} onSearch={refresh} style={{ width: 280 }} />
          <Select
            allowClear
            placeholder="Result"
            value={resultFilter}
            onChange={setResultFilter}
            options={[
              { value: 'success', label: 'Success' },
              { value: 'denied', label: 'Denied' },
              { value: 'failure', label: 'Failure' },
            ]}
            style={{ width: 120 }}
          />
          <Input
            allowClear
            placeholder="Organization UUID"
            value={organizationFilter}
            onChange={(event) => setOrganizationFilter(event.target.value.trim())}
            style={{ width: 190 }}
          />
          <Input
            allowClear
            placeholder="Business line UUID"
            value={businessLineFilter}
            onChange={(event) => setBusinessLineFilter(event.target.value.trim())}
            style={{ width: 190 }}
          />
          <Input
            allowClear
            placeholder="Space UUID"
            value={spaceFilter}
            onChange={(event) => setSpaceFilter(event.target.value.trim())}
            style={{ width: 220 }}
          />
          <Input
            aria-label="Audit date from"
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
            style={{ width: 145 }}
          />
          <Input
            aria-label="Audit date to"
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
            style={{ width: 145 }}
          />
          <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
        </Space>
      </div>
      <Card styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
        <Table rowKey="id" loading={loading} dataSource={logs} columns={columns} pagination={{ pageSize: 15 }} size="middle" scroll={{ x: 'max-content' }} />
      </Card>
    </div>
  );
}
