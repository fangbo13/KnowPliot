/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — publish version-update announcements (broadcast).
import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { Alert, Card, Table, Button, Tag, Modal, Select, Input, Space, message as antdMessage } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type Announcement, type BusinessLine, type Organization } from '../../api/admin';
import { getRateLimitDetails, isAbortError, withRequestSignal } from '../../api/client';

export default function AdminAnnouncementsPage() {
  const { t } = useTranslation('common');
  const [items, setItems] = useState<Announcement[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [lines, setLines] = useState<BusinessLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);
  const sequenceRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [version, setVersion] = useState('');
  const [audience, setAudience] = useState('all');
  const [audienceRef, setAudienceRef] = useState('');

  // Filter state
  const [audienceFilter, setAudienceFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [versionFilter, setVersionFilter] = useState<string | undefined>();
  const [titleSearch, setTitleSearch] = useState('');

  const refresh = useCallback(async () => {
    const sequence = ++sequenceRef.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setLoadError(null);
    try {
      const [announcements, organizations, businessLines] = await Promise.all([
        withRequestSignal(controller.signal, () => adminApi.announcements()),
        withRequestSignal(controller.signal, () => adminApi.organizations()),
        withRequestSignal(controller.signal, () => adminApi.businessLines()),
      ]);
      if (controller.signal.aborted || sequence !== sequenceRef.current) return;
      setItems(announcements);
      setOrgs(organizations);
      setLines(businessLines);
    } catch (error: unknown) {
      if (isAbortError(error) || controller.signal.aborted || sequence !== sequenceRef.current) return;
      const rateLimit = getRateLimitDetails(error);
      setLoadError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    } finally {
      if (sequence === sequenceRef.current && !controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => {
      sequenceRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [refresh]);

  const publish = async () => {
    if (!title.trim()) return;
    if (audience !== 'all' && !audienceRef) {
      antdMessage.error(t('admin_audience_ref_required') || 'Audience target is required');
      return;
    }
    setCreating(true);
    try {
      await adminApi.createAnnouncement({
        title,
        body,
        audience,
        audience_ref: audience === 'all' ? '' : audienceRef,
        version,
      });
      setOpen(false); setTitle(''); setBody(''); setVersion(''); setAudienceRef('');
      await refresh();
      antdMessage.success(t('admin_publish') + ' ✓');
    } catch {
      antdMessage.error(t('register_failed') || 'Failed to publish');
    } finally {
      setCreating(false);
    }
  };

  const versionOptions = useMemo(() => {
    const versions = [...new Set(items.map((a) => a.version).filter(Boolean))];
    return versions.map((v) => ({ value: v, label: v }));
  }, [items]);

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      if (audienceFilter && item.audience !== audienceFilter) return false;
      if (statusFilter && (item.is_active ? 'active' : 'inactive') !== statusFilter) return false;
      if (versionFilter && item.version !== versionFilter) return false;
      if (titleSearch && !item.title.toLowerCase().includes(titleSearch.toLowerCase())) return false;
      return true;
    });
  }, [items, audienceFilter, statusFilter, versionFilter, titleSearch]);

  const columns = [
    { title: t('kb_title') || 'Title', dataIndex: 'title', key: 'title' },
    { title: 'Version', dataIndex: 'version', key: 'version', render: (v: string) => v ? <Tag color="blue">{v}</Tag> : '-' },
    { title: t('admin_audience'), dataIndex: 'audience', key: 'audience', render: (a: string) => <Tag>{a}</Tag> },
    { title: t('kb_status') || 'Status', dataIndex: 'is_active', key: 'is_active', render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? t('admin_active') : t('admin_inactive')}</Tag> },
    { title: t('kb_created') || 'Published', dataIndex: 'published_at', key: 'published_at', render: (d: string | null) => d ? new Date(d).toLocaleString() : '-' },
  ];

  const audienceRefOptions =
    audience === 'role'
      ? [
          { value: 'employee', label: 'employee' },
          { value: 'business_admin', label: 'business_admin' },
          { value: 'org_admin', label: 'org_admin' },
          { value: 'super_admin', label: 'super_admin' },
        ]
      : audience === 'org'
        ? orgs.map((o) => ({ value: o.slug, label: o.name }))
        : audience === 'business_line'
          ? lines.map((l) => ({ value: l.code, label: `${l.name} (${l.code})` }))
          : [];

  return (
    <div className="page" style={{ background: 'transparent' }}>
      <div className="page-inner">
        <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 className="page-title">{t('admin_announcements_title')}</h1>
            <p className="page-sub">{t('admin_announcements_subtitle')}</p>
          </div>
          <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)} style={{ borderRadius: 8 }}>{t('admin_publish')}</Button>
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
            placeholder={t('kb_title') || 'Search title'}
            value={titleSearch}
            onChange={(e) => setTitleSearch(e.target.value)}
            allowClear
            style={{ width: 200 }}
          />
          <Select
            showSearch
            allowClear
            placeholder="Audience"
            value={audienceFilter}
            onChange={(value) => setAudienceFilter(value ?? undefined)}
            options={[
              { value: 'all', label: 'all' },
              { value: 'org', label: 'org' },
              { value: 'business_line', label: 'business_line' },
              { value: 'role', label: 'role' },
            ]}
            optionFilterProp="label"
            style={{ width: 160 }}
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
          <Select
            showSearch
            allowClear
            placeholder="Version"
            value={versionFilter}
            onChange={(value) => setVersionFilter(value ?? undefined)}
            options={versionOptions}
            optionFilterProp="label"
            style={{ width: 160 }}
          />
        </Space>
        <Table rowKey="id" loading={loading} dataSource={filteredItems} columns={columns} pagination={{ pageSize: 12 }} size="middle" scroll={{ x: 'max-content' }} />
      </Card>

      <Modal styles={{ mask: { backdropFilter: 'blur(6px)' } }} transitionName="fade" title={t('admin_publish')} open={open} onOk={publish} confirmLoading={creating} onCancel={() => setOpen(false)} okText={t('admin_publish')}>
        <Space direction="vertical" style={{ width: '100%', padding: '12px 0' }} size="middle">
          <Input placeholder={t('kb_title') || 'Title'} value={title} onChange={(e) => setTitle(e.target.value)} />
          <Input.TextArea rows={4} placeholder="Body" value={body} onChange={(e) => setBody(e.target.value)} />
          <Space style={{ width: '100%' }}>
            <Input placeholder="Version e.g. V7.0" value={version} onChange={(e) => setVersion(e.target.value)} style={{ width: 180 }} />
            <Select value={audience} onChange={(v) => { setAudience(v); setAudienceRef(''); }} style={{ width: 200 }}
              options={[
                { value: 'all', label: 'all' },
                { value: 'role', label: 'role' },
                { value: 'org', label: 'org' },
                { value: 'business_line', label: 'business_line' },
              ]} />
          </Space>
          {audience !== 'all' && (
            <Select
              value={audienceRef || undefined}
              onChange={setAudienceRef}
              placeholder={t('admin_audience_ref') || 'Audience target'}
              style={{ width: '100%' }}
              options={audienceRefOptions}
            />
          )}
        </Space>
      </Modal>
      </div>
    </div>
  );
}
