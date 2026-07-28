/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — organizations & business lines.
import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { Alert, Card, Table, Button, Tag, Modal, Input, Select, Space, message as antdMessage } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type BusinessLine, type Organization } from '../../api/admin';
import { getRateLimitDetails, isAbortError, withRequestSignal } from '../../api/client';

export default function AdminBusinessLinesPage() {
  const { t } = useTranslation('common');
  const [lines, setLines] = useState<BusinessLine[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);
  const sequenceRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  const [orgId, setOrgId] = useState('');
  const [name, setName] = useState('');
  const [code, setCode] = useState('');

  // Filter state
  const [orgFilter, setOrgFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [nameSearch, setNameSearch] = useState('');
  const [orgStatusFilter, setOrgStatusFilter] = useState<string | undefined>();

  const refresh = useCallback(async () => {
    const sequence = ++sequenceRef.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setLoadError(null);
    try {
      const [b, o] = await Promise.all([
        withRequestSignal(controller.signal, () => adminApi.businessLines()),
        withRequestSignal(controller.signal, () => adminApi.organizations()),
      ]);
      if (controller.signal.aborted || sequence !== sequenceRef.current) return;
      setLines(b); setOrgs(o);
      if (!orgId && o.length) setOrgId(o[0].id);
    } catch (error: unknown) {
      if (isAbortError(error) || controller.signal.aborted || sequence !== sequenceRef.current) return;
      const rateLimit = getRateLimitDetails(error);
      setLoadError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    } finally {
      if (sequence === sequenceRef.current && !controller.signal.aborted) setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    void refresh();
    return () => {
      sequenceRef.current += 1;
      controllerRef.current?.abort();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async () => {
    if (!orgId || !name.trim() || !code.trim()) return;
    setCreating(true);
    try {
      await adminApi.createBusinessLine({ organization: orgId, name, code });
      setOpen(false); setName(''); setCode('');
      await refresh();
      antdMessage.success(t('member_added') || 'Created');
    } catch {
      antdMessage.error(t('register_failed') || 'Failed');
    } finally { setCreating(false); }
  };

  const filteredLines = useMemo(() => {
    return lines.filter((line) => {
      if (orgFilter && line.organization !== orgFilter) return false;
      if (statusFilter && line.status !== statusFilter) return false;
      if (nameSearch && !line.name.toLowerCase().includes(nameSearch.toLowerCase())) return false;
      return true;
    });
  }, [lines, orgFilter, statusFilter, nameSearch]);

  const filteredOrgs = useMemo(() => {
    return orgs.filter((org) => {
      if (orgStatusFilter && org.status !== orgStatusFilter) return false;
      return true;
    });
  }, [orgs, orgStatusFilter]);

  const orgName = (id: string) => orgs.find((o) => o.id === id)?.name || id;

  const changeLifecycle = async (line: BusinessLine) => {
    const archive = line.status === 'active';
    try {
      if (archive) await adminApi.archiveBusinessLine(line.id);
      else await adminApi.restoreBusinessLine(line.id);
      antdMessage.success(archive ? 'Business line archived' : 'Business line restored');
      await refresh();
    } catch {
      antdMessage.error('Unable to update business line status');
    }
  };

  const changeOrganizationLifecycle = async (organization: Organization) => {
    const archive = organization.status === 'active';
    try {
      if (archive) await adminApi.archiveOrganization(organization.id);
      else await adminApi.restoreOrganization(organization.id);
      antdMessage.success(archive ? 'Organization archived' : 'Organization restored');
      await refresh();
    } catch {
      antdMessage.error('Unable to update organization status');
    }
  };

  const columns = [
    { title: t('kb_title') || 'Name', dataIndex: 'name', key: 'name' },
    { title: 'Code', dataIndex: 'code', key: 'code', render: (c: string) => <Tag>{c}</Tag> },
    { title: 'Organization', dataIndex: 'organization', key: 'organization', render: (o: string) => orgName(o) },
    { title: t('kb_status') || 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag> },
    { title: 'Lifecycle', key: 'lifecycle', render: (_: unknown, line: BusinessLine) => (
      <Button size="small" onClick={() => changeLifecycle(line)}>
        {line.status === 'active' ? 'Archive' : 'Restore'}
      </Button>
    ) },
  ];

  return (
    <div className="page" style={{ background: 'transparent' }}>
      <div className="page-inner">
        <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 className="page-title">{t('admin_business_lines_title')}</h1>
            <p className="page-sub">{t('admin_business_lines_subtitle')}</p>
          </div>
          <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)} style={{ borderRadius: 8 }}>{t('admin_create_business_line')}</Button>
        </Space>
      </div>
      <Card className="glass-panel section-enter" styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
        {loadError && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
            message={loadError.code === 'rate_limited'
              ? `${t('rate_limited') || 'Too many requests'}${loadError.retryAfterSeconds == null ? '' : ` — ${t('retry_after_seconds', { seconds: loadError.retryAfterSeconds })}`}`
              : t('load_error')}
            action={<Button onClick={() => void refresh()}>{t('error_retry')}</Button>}
          />
        )}
        <Space wrap style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder={t('kb_title') || 'Search name'}
            value={nameSearch}
            onChange={(e) => setNameSearch(e.target.value)}
            allowClear
            style={{ width: 180 }}
          />
          <Select
            showSearch
            allowClear
            placeholder="Organization"
            value={orgFilter}
            onChange={(value) => setOrgFilter(value ?? undefined)}
            options={orgs.map((o) => ({ value: o.id, label: o.name }))}
            optionFilterProp="label"
            style={{ width: 200 }}
          />
          <Select
            allowClear
            placeholder="Status"
            value={statusFilter}
            onChange={(value) => setStatusFilter(value ?? undefined)}
            options={[
              { value: 'active', label: 'Active' },
              { value: 'inactive', label: 'Inactive' },
            ]}
            style={{ width: 120 }}
          />
        </Space>
        <Table rowKey="id" loading={loading} dataSource={filteredLines} columns={columns} pagination={{ pageSize: 12 }} size="middle" scroll={{ x: 'max-content' }} />
      </Card>

      <Card title="Organizations" className="glass-panel section-enter" styles={{ body: { padding: 20 } }} style={{ marginTop: 24, borderRadius: 'var(--radius-lg)' }}>
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            allowClear
            placeholder="Status"
            value={orgStatusFilter}
            onChange={(value) => setOrgStatusFilter(value ?? undefined)}
            options={[
              { value: 'active', label: 'Active' },
              { value: 'inactive', label: 'Inactive' },
            ]}
            style={{ width: 120 }}
          />
        </Space>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={filteredOrgs}
          pagination={false}
          size="small"
          columns={[
            { title: 'Name', dataIndex: 'name', key: 'name' },
            { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag> },
            { title: 'Lifecycle', key: 'lifecycle', render: (_: unknown, org: Organization) => <Button size="small" onClick={() => changeOrganizationLifecycle(org)}>{org.status === 'active' ? 'Archive' : 'Restore'}</Button> },
          ]}
        />
      </Card>

      <Modal styles={{ mask: { backdropFilter: 'blur(6px)' } }} transitionName="fade" title={t('admin_create_business_line')} open={open} onOk={create} confirmLoading={creating} onCancel={() => setOpen(false)} okText={t('create') || 'Create'}>
        <Space direction="vertical" style={{ width: '100%', padding: '12px 0' }} size="middle">
          <Select value={orgId || undefined} onChange={setOrgId} style={{ width: '100%' }} placeholder="Organization"
            options={orgs.map((o) => ({ value: o.id, label: o.name }))} />
          <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input placeholder="Code (e.g. risk)" value={code} onChange={(e) => setCode(e.target.value)} />
        </Space>
      </Modal>
      </div>
    </div>
  );
}
