/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — issue / list / revoke tiered Admin Registration Codes.
import { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Button, Tag, Modal, Select, Input, Space, Popconfirm,
  Typography, message as antdMessage,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type AdminCode, type Organization, type BusinessLine } from '../../api/admin';

const { Paragraph } = Typography;

export default function AdminCodesPage() {
  const { t } = useTranslation('common');
  const [codes, setCodes] = useState<AdminCode[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [lines, setLines] = useState<BusinessLine[]>([]);
  const [loading, setLoading] = useState(false);

  const [open, setOpen] = useState(false);
  const [grantsRole, setGrantsRole] = useState<'org_admin' | 'business_admin'>('business_admin');
  const [orgId, setOrgId] = useState<string>('');
  const [blId, setBlId] = useState<string>('');
  const [maxUses, setMaxUses] = useState(1);
  const [creating, setCreating] = useState(false);
  const [generated, setGenerated] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [c, o, b] = await Promise.all([
        adminApi.codes().catch(() => []),
        adminApi.organizations().catch(() => []),
        adminApi.businessLines().catch(() => []),
      ]);
      setCodes(c); setOrgs(o); setLines(b);
      if (!orgId && o.length) setOrgId(o[0].id);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const issue = async () => {
    if (!orgId) return;
    setCreating(true);
    try {
      const res = await adminApi.createCode({
        grants_role: grantsRole, organization: orgId,
        business_line: grantsRole === 'business_admin' ? blId || null : null,
        max_uses: maxUses,
      });
      setGenerated(res.code ?? null);
      setOpen(false);
      await refresh();
    } catch {
      antdMessage.error(t('register_failed') || 'Failed to issue code');
    } finally {
      setCreating(false);
    }
  };

  const revoke = async (id: string) => {
    try { await adminApi.revokeCode(id); await refresh(); antdMessage.success(t('invite_revoked') || 'Revoked'); }
    catch { antdMessage.error(t('invite_revoke_failed') || 'Failed'); }
  };

  const columns = [
    { title: t('access_code') || 'Code', dataIndex: 'code_prefix', key: 'code', render: (p: string) => `${p}…` },
    { title: t('admin_grants_role'), dataIndex: 'grants_role', key: 'grants_role', render: (r: string) => <Tag color={r === 'org_admin' ? 'gold' : 'blue'}>{r}</Tag> },
    {
      title: t('service_line_label') || 'Scope', key: 'scope',
      render: (_: any, r: AdminCode) => r.business_line_name || r.organization_name,
    },
    { title: t('invite_uses') || 'Uses', key: 'uses', render: (_: any, r: AdminCode) => `${r.used_count}${r.max_uses ? ` / ${r.max_uses}` : ''}` },
    { title: t('member_status') || 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : 'red'}>{s}</Tag> },
    {
      title: '', key: 'actions',
      render: (_: any, r: AdminCode) => r.status === 'active' ? (
        <Popconfirm title={t('invite_revoke_confirm') || 'Revoke?'} onConfirm={() => revoke(r.id)}>
          <Button type="link" danger size="small">{t('revoke') || 'Revoke'}</Button>
        </Popconfirm>
      ) : null,
    },
  ];

  const scopedLines = lines.filter((l) => l.organization === orgId);

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">{t('admin_codes_title')}</h1>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)} style={{ borderRadius: 8 }}>{t('admin_issue_code')}</Button>
        </Space>
      </div>

      <Card styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
        <Table rowKey="id" loading={loading} dataSource={codes} columns={columns} pagination={false} size="middle" />
      </Card>

      <Modal title={t('admin_issue_code')} open={open} onOk={issue} confirmLoading={creating} onCancel={() => setOpen(false)} okText={t('create') || 'Create'}>
        <Space direction="vertical" style={{ width: '100%', padding: '12px 0' }} size="middle">
          <Select value={grantsRole} onChange={(v) => setGrantsRole(v)} style={{ width: '100%' }}
            options={[{ value: 'business_admin', label: 'business_admin' }, { value: 'org_admin', label: 'org_admin' }]} />
          <Select value={orgId} onChange={(v) => { setOrgId(v); setBlId(''); }} style={{ width: '100%' }}
            placeholder={t('service_line_placeholder')}
            options={orgs.map((o) => ({ value: o.id, label: o.name }))} />
          {grantsRole === 'business_admin' && (
            <Select value={blId || undefined} onChange={setBlId} style={{ width: '100%' }} placeholder="Business line"
              options={scopedLines.map((l) => ({ value: l.id, label: l.name }))} />
          )}
          <Input type="number" min={0} value={maxUses} onChange={(e) => setMaxUses(Number(e.target.value) || 0)}
            addonBefore={t('invite_max_uses') || 'Max uses'} />
        </Space>
      </Modal>

      <Modal title={t('code_generated') || 'Code generated'} open={!!generated} onCancel={() => setGenerated(null)}
        footer={[<Button key="ok" type="primary" onClick={() => setGenerated(null)}>{t('done') || 'Done'}</Button>]}>
        <Paragraph type="warning" style={{ fontSize: 13, fontWeight: 500 }}>{t('admin_code_copy_hint')}</Paragraph>
        <Input.TextArea readOnly value={generated ?? ''} autoSize style={{ fontFamily: 'var(--font-family-mono)', borderRadius: 8 }} />
      </Modal>
    </div>
  );
}
