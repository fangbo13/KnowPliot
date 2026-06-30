/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — organizations & business lines.
import { useEffect, useState, useCallback } from 'react';
import { Card, Table, Button, Tag, Modal, Input, Select, Space, message as antdMessage } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type BusinessLine, type Organization } from '../../api/admin';

export default function AdminBusinessLinesPage() {
  const { t } = useTranslation('common');
  const [lines, setLines] = useState<BusinessLine[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  const [orgId, setOrgId] = useState('');
  const [name, setName] = useState('');
  const [code, setCode] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [b, o] = await Promise.all([adminApi.businessLines().catch(() => []), adminApi.organizations().catch(() => [])]);
      setLines(b); setOrgs(o);
      if (!orgId && o.length) setOrgId(o[0].id);
    } finally { setLoading(false); }
  }, [orgId]);

  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

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

  const orgName = (id: string) => orgs.find((o) => o.id === id)?.name || id;

  const columns = [
    { title: t('kb_title') || 'Name', dataIndex: 'name', key: 'name' },
    { title: 'Code', dataIndex: 'code', key: 'code', render: (c: string) => <Tag>{c}</Tag> },
    { title: 'Organization', dataIndex: 'organization', key: 'organization', render: (o: string) => orgName(o) },
    { title: t('kb_status') || 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag> },
  ];

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">{t('admin_business_lines_title')}</h1>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)} style={{ borderRadius: 8 }}>{t('admin_create_business_line')}</Button>
        </Space>
      </div>
      <Card styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
        <Table rowKey="id" loading={loading} dataSource={lines} columns={columns} pagination={false} size="middle" />
      </Card>

      <Modal title={t('admin_create_business_line')} open={open} onOk={create} confirmLoading={creating} onCancel={() => setOpen(false)} okText={t('create') || 'Create'}>
        <Space direction="vertical" style={{ width: '100%', padding: '12px 0' }} size="middle">
          <Select value={orgId || undefined} onChange={setOrgId} style={{ width: '100%' }} placeholder="Organization"
            options={orgs.map((o) => ({ value: o.id, label: o.name }))} />
          <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input placeholder="Code (e.g. risk)" value={code} onChange={(e) => setCode(e.target.value)} />
        </Space>
      </Modal>
    </div>
  );
}
