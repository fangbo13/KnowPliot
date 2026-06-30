/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — publish version-update announcements (broadcast).
import { useEffect, useState, useCallback } from 'react';
import { Card, Table, Button, Tag, Modal, Select, Input, Space, message as antdMessage } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type Announcement, type BusinessLine, type Organization } from '../../api/admin';

export default function AdminAnnouncementsPage() {
  const { t } = useTranslation('common');
  const [items, setItems] = useState<Announcement[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [lines, setLines] = useState<BusinessLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [version, setVersion] = useState('');
  const [audience, setAudience] = useState('all');
  const [audienceRef, setAudienceRef] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [announcements, organizations, businessLines] = await Promise.all([
        adminApi.announcements(),
        adminApi.organizations().catch(() => []),
        adminApi.businessLines().catch(() => []),
      ]);
      setItems(announcements);
      setOrgs(organizations);
      setLines(businessLines);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

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
    <div>
      <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">{t('admin_announcements_title')}</h1>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)} style={{ borderRadius: 8 }}>{t('admin_publish')}</Button>
        </Space>
      </div>

      <Card styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
        <Table rowKey="id" loading={loading} dataSource={items} columns={columns} pagination={false} size="middle" />
      </Card>

      <Modal title={t('admin_publish')} open={open} onOk={publish} confirmLoading={creating} onCancel={() => setOpen(false)} okText={t('admin_publish')}>
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
  );
}
