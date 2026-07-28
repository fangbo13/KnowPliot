/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// KB optimization spec §5.2: space taxonomy manager — dimension/term tree with
// create / rename / archive, plus one-click "import default preset" for
// space-mode spaces. Rendered inside the Knowledge Base page for
// owner/knowledge_admin users.

import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Switch,
  Tag,
  Tree,
  message,
} from 'antd';
import { DownloadOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import { useTranslation } from 'react-i18next';
import { taxonomyApi } from '../../api/knowledge';
import type { TaxonomyDimension, TaxonomyTerm } from '../../api/knowledge';

interface Props {
  /** Active space taxonomy mode: inherit / space / none. */
  taxonomyMode: string;
  /** Whether the current user may manage taxonomy (owner/knowledge_admin). */
  canManage: boolean;
  /** Notify parent (filters etc.) after dimensions change. */
  onChanged?: () => void;
}

interface TermFormValues {
  code: string;
  label: string;
  parent?: string;
}

export function TaxonomyManagerPanel({ taxonomyMode, canManage, onChanged }: Props) {
  const { t } = useTranslation('common');
  const [dimensions, setDimensions] = useState<TaxonomyDimension[]>([]);
  const [loading, setLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [dimModalOpen, setDimModalOpen] = useState(false);
  const [termModalDim, setTermModalDim] = useState<TaxonomyDimension | null>(null);
  const [termModalParent, setTermModalParent] = useState<TaxonomyTerm | null>(null);
  const [dimForm] = Form.useForm();
  const [termForm] = Form.useForm<TermFormValues>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDimensions(await taxonomyApi.getDimensions());
    } catch {
      message.error(t('kb_taxonomy_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const notifyChanged = useCallback(() => {
    onChanged?.();
    void load();
  }, [onChanged, load]);

  const handleSeedDefaults = async () => {
    setSeeding(true);
    try {
      const res = await taxonomyApi.seedDefaults('audit_default');
      message.success(
        res.created > 0
          ? t('kb_taxonomy_seed_done', { count: res.created })
          : t('kb_taxonomy_seed_noop'),
      );
      notifyChanged();
    } catch {
      message.error(t('kb_taxonomy_seed_failed'));
    } finally {
      setSeeding(false);
    }
  };

  const handleCreateDimension = async () => {
    const values = await dimForm.validateFields();
    try {
      await taxonomyApi.createDimension(values);
      message.success(t('kb_taxonomy_dim_created'));
      setDimModalOpen(false);
      dimForm.resetFields();
      notifyChanged();
    } catch {
      message.error(t('kb_taxonomy_save_failed'));
    }
  };

  const handleCreateTerm = async () => {
    if (!termModalDim) return;
    const values = await termForm.validateFields();
    try {
      await taxonomyApi.createTerm({
        dimension: termModalDim.id,
        code: values.code,
        label: values.label,
        parent: termModalParent?.id ?? null,
      });
      message.success(t('kb_taxonomy_term_created'));
      setTermModalDim(null);
      setTermModalParent(null);
      termForm.resetFields();
      notifyChanged();
    } catch {
      message.error(t('kb_taxonomy_save_failed'));
    }
  };

  const archiveDimension = async (dim: TaxonomyDimension) => {
    try {
      await taxonomyApi.updateDimension(dim.id, { status: 'archived' });
      message.success(t('kb_taxonomy_archived'));
      notifyChanged();
    } catch {
      message.error(t('kb_taxonomy_save_failed'));
    }
  };

  const archiveTerm = async (term: TaxonomyTerm) => {
    try {
      await taxonomyApi.updateTerm(term.id, { status: 'archived' });
      message.success(t('kb_taxonomy_archived'));
      notifyChanged();
    } catch {
      message.error(t('kb_taxonomy_save_failed'));
    }
  };

  if (taxonomyMode === 'none') {
    return (
      <Alert
        type="info"
        showIcon
        message={t('kb_taxonomy_mode_none_title')}
        description={t('kb_taxonomy_mode_none_desc')}
      />
    );
  }

  const editable = canManage && taxonomyMode === 'space';

  const buildTermNodes = (dim: TaxonomyDimension, parentId: string | null): DataNode[] =>
    dim.terms
      .filter((term) => (term.parent ?? null) === parentId)
      .map((term) => ({
        key: term.id,
        title: (
          <Space size={6}>
            <span>{term.label}</span>
            <Tag style={{ marginInlineEnd: 0 }}>{term.code}</Tag>
            {editable && (
              <>
                <Button
                  type="link"
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    setTermModalDim(dim);
                    setTermModalParent(term);
                  }}
                >
                  {t('kb_taxonomy_add_child')}
                </Button>
                <Popconfirm
                  title={t('kb_taxonomy_archive_confirm')}
                  onConfirm={() => void archiveTerm(term)}
                >
                  <Button type="link" size="small" danger onClick={(e) => e.stopPropagation()}>
                    {t('kb_taxonomy_archive')}
                  </Button>
                </Popconfirm>
              </>
            )}
          </Space>
        ),
        children: buildTermNodes(dim, term.id),
      }));

  return (
    <div data-testid="taxonomy-manager-panel">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        {editable && (
          <>
            <Button icon={<PlusOutlined />} onClick={() => setDimModalOpen(true)}>
              {t('kb_taxonomy_add_dimension')}
            </Button>
            <Button icon={<DownloadOutlined />} loading={seeding} onClick={() => void handleSeedDefaults()}>
              {t('kb_taxonomy_import_defaults')}
            </Button>
          </>
        )}
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>
          {t('refresh')}
        </Button>
        {taxonomyMode === 'inherit' && (
          <Tag color="blue" style={{ alignSelf: 'center' }}>
            {t('kb_taxonomy_mode_inherit_badge')}
          </Tag>
        )}
      </div>

      <Spin spinning={loading}>
        {dimensions.length === 0 ? (
          <Empty description={t('kb_taxonomy_empty')}>
            {editable && (
              <Space>
                <Button type="primary" icon={<DownloadOutlined />} loading={seeding} onClick={() => void handleSeedDefaults()}>
                  {t('kb_taxonomy_import_defaults')}
                </Button>
                <Button icon={<PlusOutlined />} onClick={() => setDimModalOpen(true)}>
                  {t('kb_taxonomy_add_dimension')}
                </Button>
              </Space>
            )}
          </Empty>
        ) : (
          dimensions.map((dim) => (
            <div
              key={dim.id}
              style={{
                border: '1px solid var(--color-border)',
                borderRadius: 8,
                padding: 12,
                marginBottom: 12,
                background: 'var(--color-bg-container)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                <strong>{dim.name}</strong>
                <Tag>{dim.code}</Tag>
                {dim.required && <Tag color="red">{t('kb_taxonomy_required')}</Tag>}
                {dim.space === null && <Tag color="blue">{t('kb_taxonomy_shared')}</Tag>}
                {editable && dim.space !== null && (
                  <Space size={4}>
                    <Button
                      type="link"
                      size="small"
                      onClick={() => {
                        setTermModalDim(dim);
                        setTermModalParent(null);
                      }}
                    >
                      {t('kb_taxonomy_add_term')}
                    </Button>
                    <Popconfirm
                      title={t('kb_taxonomy_archive_confirm')}
                      onConfirm={() => void archiveDimension(dim)}
                    >
                      <Button type="link" size="small" danger>
                        {t('kb_taxonomy_archive')}
                      </Button>
                    </Popconfirm>
                  </Space>
                )}
              </div>
              {dim.terms.length === 0 ? (
                <span style={{ fontSize: 12, color: 'var(--color-text-tertiary)' }}>
                  {t('kb_taxonomy_no_terms')}
                </span>
              ) : (
                <Tree treeData={buildTermNodes(dim, null)} defaultExpandAll selectable={false} />
              )}
            </div>
          ))
        )}
      </Spin>

      {/* Create dimension modal */}
      <Modal
        title={t('kb_taxonomy_add_dimension')}
        open={dimModalOpen}
        onOk={() => void handleCreateDimension()}
        onCancel={() => setDimModalOpen(false)}
        destroyOnClose
      >
        <Form form={dimForm} layout="vertical">
          <Form.Item
            name="code"
            label={t('kb_taxonomy_code')}
            rules={[
              { required: true },
              { pattern: /^[a-z0-9_-]+$/, message: t('kb_taxonomy_code_rule') },
            ]}
          >
            <Input placeholder="risk_area" />
          </Form.Item>
          <Form.Item name="name" label={t('kb_taxonomy_name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="required" label={t('kb_taxonomy_required')} valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
          <Form.Item name="is_hierarchical" label={t('kb_taxonomy_hierarchical')} valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
          <Form.Item name="sort_order" label={t('kb_taxonomy_sort')} initialValue={0}>
            <InputNumber min={0} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Create term modal */}
      <Modal
        title={
          termModalParent
            ? `${t('kb_taxonomy_add_child')} — ${termModalParent.label}`
            : `${t('kb_taxonomy_add_term')} — ${termModalDim?.name ?? ''}`
        }
        open={termModalDim !== null}
        onOk={() => void handleCreateTerm()}
        onCancel={() => {
          setTermModalDim(null);
          setTermModalParent(null);
        }}
        destroyOnClose
      >
        <Form form={termForm} layout="vertical">
          <Form.Item
            name="code"
            label={t('kb_taxonomy_code')}
            rules={[
              { required: true },
              { pattern: /^[a-z0-9_-]+$/, message: t('kb_taxonomy_code_rule') },
            ]}
          >
            <Input placeholder="accounts_receivable" />
          </Form.Item>
          <Form.Item name="label" label={t('kb_taxonomy_label')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default TaxonomyManagerPanel;
