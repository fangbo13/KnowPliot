/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — audit log viewer (reuses /audit/logs/).
import { useEffect, useState, useCallback, useMemo } from 'react';
import { Card, Table, Tag, Input, Button, Space, Select, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type AuditLog, type AdminUser, type Organization, type BusinessLine, type AdminSpaceListItem } from '../../api/admin';

const AUDIT_ACTION_OPTIONS = [
  { value: 'document_upload', label: 'Document Upload' },
  { value: 'document_download', label: 'Document Download' },
  { value: 'document_delete', label: 'Document Delete' },
  { value: 'document_reindex', label: 'Document Reindex' },
  { value: 'document_status_change', label: 'Document Status Change' },
  { value: 'template_create', label: 'Template Create' },
  { value: 'template_update', label: 'Template Update' },
  { value: 'template_delete', label: 'Template Delete' },
  { value: 'user_login', label: 'User Login' },
  { value: 'export_data', label: 'Export Data' },
  { value: 'category_create', label: 'Category Create' },
  { value: 'category_update', label: 'Category Update' },
  { value: 'role_assign', label: 'Role Assign' },
  { value: 'role_revoke', label: 'Role Revoke' },
  { value: 'user_create', label: 'User Create' },
  { value: 'user_update', label: 'User Update' },
  { value: 'user_deactivate', label: 'User Deactivate' },
  { value: 'config_change', label: 'Config Change' },
  { value: 'system_health_view', label: 'System Health View' },
  { value: 'ingestion_retry', label: 'Ingestion Retry' },
  { value: 'audit_export', label: 'Audit Export' },
  { value: 'role_change_log', label: 'Role Change Log' },
  { value: 'document_crawl', label: 'Document Crawl' },
  { value: 'document_crawl_withdraw', label: 'Document Crawl Withdraw' },
  { value: 'document_batch_import', label: 'Document Batch Import' },
  { value: 'document_batch_result_view', label: 'Document Batch Result View' },
  { value: 'space_create', label: 'Space Create' },
  { value: 'space_update', label: 'Space Update' },
  { value: 'space_archive', label: 'Space Archive' },
  { value: 'space_switch', label: 'Space Switch' },
  { value: 'space_join', label: 'Space Join (Access Code)' },
  { value: 'space_invite_create', label: 'Space Invite Code Create' },
  { value: 'space_invite_revoke', label: 'Space Invite Code Revoke' },
  { value: 'space_member_add', label: 'Space Member Add' },
  { value: 'space_member_update', label: 'Space Member Update' },
  { value: 'permission_denied', label: 'Permission Denied' },
  { value: 'user_register', label: 'User Register' },
  { value: 'admin_code_register', label: 'Admin Code Register' },
  { value: 'admin_code_create', label: 'Admin Code Create' },
  { value: 'admin_code_revoke', label: 'Admin Code Revoke' },
  { value: 'space_member_remove', label: 'Space Member Remove' },
  { value: 'space_email_invite', label: 'Space Email Invite' },
  { value: 'notification_broadcast', label: 'Notification Broadcast' },
  { value: 'signup_approved', label: 'Signup Approved' },
  { value: 'signup_rejected', label: 'Signup Rejected' },
  { value: 'user_promote_superadmin', label: 'User Promote Super Admin' },
  { value: 'feedback_submit', label: 'Feedback Submit' },
  { value: 'feedback_update', label: 'Feedback Update' },
  { value: 'feedback_withdraw', label: 'Feedback Withdraw' },
  { value: 'feedback_review_assign', label: 'Feedback Review Assign' },
  { value: 'feedback_review_claim', label: 'Feedback Review Claim' },
  { value: 'feedback_review_resolve', label: 'Feedback Review Resolve' },
  { value: 'feedback_review_dismiss', label: 'Feedback Review Dismiss' },
  { value: 'feedback_review_reopen', label: 'Feedback Review Reopen' },
  { value: 'knowledge_gap_create', label: 'Knowledge Gap Create' },
  { value: 'knowledge_gap_assign', label: 'Knowledge Gap Assign' },
  { value: 'knowledge_gap_resolve', label: 'Knowledge Gap Resolve' },
  { value: 'knowledge_gap_reopen', label: 'Knowledge Gap Reopen' },
  { value: 'export_job_create', label: 'Export Job Create' },
  { value: 'export_job_complete', label: 'Export Job Complete' },
  { value: 'export_job_retry', label: 'Export Job Retry' },
  { value: 'audit_export_download', label: 'Audit Export Download' },
  { value: 'sla_alert_created', label: 'SLA Alert Created' },
];

export default function AdminAuditPage() {
  const { t } = useTranslation('common');
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);

  // Filter state — all use dropdowns with search
  const [userFilter, setUserFilter] = useState<string | undefined>();
  const [actionFilter, setActionFilter] = useState<string | undefined>();
  const [resultFilter, setResultFilter] = useState<string | undefined>();
  const [organizationFilter, setOrganizationFilter] = useState<string | undefined>();
  const [businessLineFilter, setBusinessLineFilter] = useState<string | undefined>();
  const [spaceFilter, setSpaceFilter] = useState<string | undefined>();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Options data for dropdowns
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [businessLines, setBusinessLines] = useState<BusinessLine[]>([]);
  const [spaces, setSpaces] = useState<AdminSpaceListItem[]>([]);

  // Load filter options on mount
  useEffect(() => {
    adminApi.users().then(setUsers).catch(() => {});
    adminApi.organizations().then(setOrganizations).catch(() => {});
    adminApi.listSpaces({ page_size: 100 }).then((res) => setSpaces(res.results)).catch(() => {});
  }, []);

  // Cascade: load business lines when organization changes
  useEffect(() => {
    if (organizationFilter) {
      adminApi.businessLines(organizationFilter).then(setBusinessLines).catch(() => {});
    } else {
      setBusinessLines([]);
      setBusinessLineFilter(undefined);
    }
  }, [organizationFilter]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setLogs(await adminApi.auditLogs({
        ...(actionFilter ? { action: actionFilter } : {}),
        ...(resultFilter ? { result: resultFilter as 'success' | 'denied' | 'failure' } : {}),
        ...(userFilter ? { user_id: userFilter } : {}),
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
    userFilter,
    organizationFilter,
    businessLineFilter,
    spaceFilter,
    dateFrom,
    dateTo,
  ]);

  useEffect(() => { refresh(); }, [refresh]);

  // Build lookup maps for display
  const spaceNameMap = useMemo(() => {
    const map = new Map<string, string>();
    spaces.forEach((s) => map.set(s.id, s.name));
    return map;
  }, [spaces]);

  const DENY = 'permission_denied';
  const columns = [
    { title: t('kb_created') || 'Time', dataIndex: 'created_at', key: 'created_at', width: 180, render: (d: string) => new Date(d).toLocaleString() },
    { title: 'User', dataIndex: 'user_email', key: 'user_email', render: (v: string) => v || '-' },
    { title: 'Action', dataIndex: 'action', key: 'action', render: (a: string) => <Tag color={a === DENY ? 'red' : a.includes('register') || a.includes('code') ? 'gold' : 'blue'}>{a}</Tag> },
    { title: 'Result', dataIndex: 'result', key: 'result', render: (v: string) => <Tag color={v === 'denied' || v === 'failure' ? 'red' : 'green'}>{v}</Tag> },
    { title: 'Target', dataIndex: 'target_type', key: 'target_type' },
    { title: 'Space', dataIndex: 'space_id', key: 'space_id', render: (v: string | null) => v ? (spaceNameMap.get(v) ?? v.slice(0, 8)) : '-' },
    { title: 'Role', dataIndex: 'role_used', key: 'role_used', render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  ];

  return (
    <div className="page" style={{ background: 'transparent' }}>
      <div className="page-inner">
        <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1 className="page-title">{t('admin_audit_title')}</h1>
        </div>
        <Card className="glass-panel section-enter" styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
          <Space wrap style={{ marginBottom: 16 }}>
            <Select
              showSearch
              allowClear
              placeholder="User"
              value={userFilter}
              onChange={(value) => setUserFilter(value ?? undefined)}
              options={users.map((u) => ({ value: u.id, label: u.email }))}
              optionFilterProp="label"
              style={{ width: 220 }}
            />
            <Select
              showSearch
              allowClear
              placeholder="Action"
              value={actionFilter}
              onChange={(value) => setActionFilter(value ?? undefined)}
              options={AUDIT_ACTION_OPTIONS}
              optionFilterProp="label"
              style={{ width: 220 }}
            />
            <Select
              allowClear
              placeholder="Result"
              value={resultFilter}
              onChange={(value) => setResultFilter(value ?? undefined)}
              options={[
                { value: 'success', label: 'Success' },
                { value: 'denied', label: 'Denied' },
                { value: 'failure', label: 'Failure' },
              ]}
              style={{ width: 120 }}
            />
            <Select
              showSearch
              allowClear
              placeholder="Organization"
              value={organizationFilter}
              onChange={(value) => { setOrganizationFilter(value ?? undefined); }}
              options={organizations.map((o) => ({ value: o.id, label: o.name }))}
              optionFilterProp="label"
              style={{ width: 180 }}
            />
            <Select
              showSearch
              allowClear
              placeholder="Business Line"
              value={businessLineFilter}
              onChange={(value) => setBusinessLineFilter(value ?? undefined)}
              options={businessLines.map((b) => ({ value: b.id, label: b.name }))}
              optionFilterProp="label"
              style={{ width: 180 }}
            />
            <Select
              showSearch
              allowClear
              placeholder="Space"
              value={spaceFilter}
              onChange={(value) => setSpaceFilter(value ?? undefined)}
              options={spaces.map((s) => ({ value: s.id, label: s.name }))}
              optionFilterProp="label"
              style={{ width: 200 }}
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
          <Table rowKey="id" loading={loading} dataSource={logs} columns={columns} pagination={{ pageSize: 15 }} size="middle" scroll={{ x: 'max-content' }} />
        </Card>
      </div>
    </div>
  );
}
