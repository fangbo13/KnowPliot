/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// KB optimization spec §5.3: reference-library management.
// - Space view: owner/knowledge_admin picks published libraries (IFRS / CAS /
//   IPO cases ...) to widen RAG retrieval for this space.
// - Platform admin view: certify a space as a library, publish / unpublish.

import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  message,
} from 'antd';
import { BookOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { libraryApi } from '../../api/knowledge';
import type { ReferenceLibrary, SpaceLibraryReference } from '../../api/knowledge';
import { useSpaceStore } from '../../store/spaceStore';

const CATEGORY_COLORS: Record<string, string> = {
  ifrs: 'geekblue',
  cas: 'green',
  ipo_cases: 'purple',
  other: 'default',
};

interface Props {
  /** Whether the current user may manage this space's references. */
  canManage: boolean;
  /** Platform admin flag — shows the certify/publish management block. */
  isPlatformAdmin?: boolean;
}

export function LibraryReferencesPanel({ canManage, isPlatformAdmin = false }: Props) {
  const { t } = useTranslation('common');
  const activeSpaceId = useSpaceStore((s) => s.activeSpaceId);
  const [catalog, setCatalog] = useState<ReferenceLibrary[]>([]);
  const [references, setReferences] = useState<SpaceLibraryReference[]>([]);
  const [adminLibraries, setAdminLibraries] = useState<ReferenceLibrary[]>([]);
  const [loading, setLoading] = useState(false);
  const [certifyOpen, setCertifyOpen] = useState(false);
  const [certifyForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cat, refs] = await Promise.all([libraryApi.catalog(), libraryApi.getReferences()]);
      setCatalog(cat);
      setReferences(refs);
      if (isPlatformAdmin) {
        setAdminLibraries(await libraryApi.list());
      }
    } catch {
      message.error(t('kb_library_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [isPlatformAdmin, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const referencedIds = new Set(references.map((r) => r.library));

  const addReference = async (libraryId: string) => {
    try {
      await libraryApi.addReference(libraryId);
      message.success(t('kb_library_ref_added'));
      void load();
    } catch {
      message.error(t('kb_library_save_failed'));
    }
  };

  const toggleReference = async (ref: SpaceLibraryReference, enabled: boolean) => {
    try {
      await libraryApi.toggleReference(ref.id, enabled);
      void load();
    } catch {
      message.error(t('kb_library_save_failed'));
    }
  };

  const removeReference = async (ref: SpaceLibraryReference) => {
    try {
      await libraryApi.removeReference(ref.id);
      message.success(t('kb_library_ref_removed'));
      void load();
    } catch {
      message.error(t('kb_library_save_failed'));
    }
  };

  const certifyLibrary = async () => {
    const values = await certifyForm.validateFields();
    try {
      await libraryApi.create({ ...values, status: 'published' });
      message.success(t('kb_library_certified'));
      setCertifyOpen(false);
      certifyForm.resetFields();
      void load();
    } catch {
      message.error(t('kb_library_save_failed'));
    }
  };

  const setLibraryStatus = async (lib: ReferenceLibrary, status: 'published' | 'unpublished') => {
    try {
      await libraryApi.update(lib.id, { status });
      void load();
    } catch {
      message.error(t('kb_library_save_failed'));
    }
  };

  return (
    <div data-testid="library-references-panel">
      <Alert
        type="info"
        showIcon
        icon={<BookOutlined />}
        message={t('kb_library_intro_title')}
        description={t('kb_library_intro_desc')}
        style={{ marginBottom: 16 }}
      />

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>
          {t('refresh')}
        </Button>
        {isPlatformAdmin && (
          <Button icon={<PlusOutlined />} onClick={() => setCertifyOpen(true)}>
            {t('kb_library_certify')}
          </Button>
        )}
      </div>

      <Spin spinning={loading}>
        {/* Current space references */}
        <h4 style={{ margin: '8px 0' }}>{t('kb_library_my_references')}</h4>
        {references.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('kb_library_no_references')} />
        ) : (
          <List
            size="small"
            bordered
            dataSource={references}
            style={{ marginBottom: 16 }}
            renderItem={(ref) => (
              <List.Item
                actions={
                  canManage
                    ? [
                        <Switch
                          key="toggle"
                          size="small"
                          checked={ref.enabled}
                          onChange={(checked) => void toggleReference(ref, checked)}
                        />,
                        <Popconfirm
                          key="remove"
                          title={t('kb_library_remove_confirm')}
                          onConfirm={() => void removeReference(ref)}
                        >
                          <Button type="link" size="small" danger>
                            {t('kb_library_remove')}
                          </Button>
                        </Popconfirm>,
                      ]
                    : undefined
                }
              >
                <Space>
                  <span>{ref.library_name}</span>
                  <Tag color={CATEGORY_COLORS[ref.library_category] || 'default'}>
                    {t(`kb_library_cat_${ref.library_category}`)}
                  </Tag>
                  {ref.library_status !== 'published' && (
                    <Tag color="orange">{t('kb_library_unpublished')}</Tag>
                  )}
                  {!ref.enabled && <Tag>{t('kb_library_disabled')}</Tag>}
                </Space>
              </List.Item>
            )}
          />
        )}

        {/* Published catalog */}
        <h4 style={{ margin: '8px 0' }}>{t('kb_library_catalog')}</h4>
        {catalog.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('kb_library_catalog_empty')} />
        ) : (
          <List
            size="small"
            bordered
            dataSource={catalog}
            renderItem={(lib) => (
              <List.Item
                actions={
                  canManage
                    ? [
                        lib.space === activeSpaceId ? (
                          <Tag key="self" color="default">
                            {t('kb_library_self')}
                          </Tag>
                        ) : referencedIds.has(lib.id) ? (
                          <Tag key="added" color="success">
                            {t('kb_library_added')}
                          </Tag>
                        ) : (
                          <Button
                            key="add"
                            type="link"
                            size="small"
                            onClick={() => void addReference(lib.id)}
                          >
                            {t('kb_library_add')}
                          </Button>
                        ),
                      ]
                    : undefined
                }
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <span>{lib.name}</span>
                      <Tag color={CATEGORY_COLORS[lib.category] || 'default'}>
                        {t(`kb_library_cat_${lib.category}`)}
                      </Tag>
                      <Tag color="cyan">{t('kb_library_official')}</Tag>
                    </Space>
                  }
                  description={lib.description || lib.space_name}
                />
              </List.Item>
            )}
          />
        )}

        {/* Platform admin: all libraries incl. unpublished */}
        {isPlatformAdmin && (
          <>
            <h4 style={{ margin: '16px 0 8px' }}>{t('kb_library_admin_all')}</h4>
            <List
              size="small"
              bordered
              dataSource={adminLibraries}
              locale={{ emptyText: t('kb_library_catalog_empty') }}
              renderItem={(lib) => (
                <List.Item
                  actions={[
                    lib.status === 'published' ? (
                      <Button
                        key="unpublish"
                        type="link"
                        size="small"
                        danger
                        onClick={() => void setLibraryStatus(lib, 'unpublished')}
                      >
                        {t('kb_library_unpublish')}
                      </Button>
                    ) : (
                      <Button
                        key="publish"
                        type="link"
                        size="small"
                        onClick={() => void setLibraryStatus(lib, 'published')}
                      >
                        {t('kb_library_publish')}
                      </Button>
                    ),
                  ]}
                >
                  <Space>
                    <span>{lib.name}</span>
                    <Tag>{lib.space_code}</Tag>
                    <Tag color={lib.status === 'published' ? 'success' : 'orange'}>
                      {lib.status === 'published'
                        ? t('kb_library_published')
                        : t('kb_library_unpublished')}
                    </Tag>
                  </Space>
                </List.Item>
              )}
            />
          </>
        )}
      </Spin>

      {/* Platform admin certify modal */}
      <Modal
        title={t('kb_library_certify')}
        open={certifyOpen}
        onOk={() => void certifyLibrary()}
        onCancel={() => setCertifyOpen(false)}
        destroyOnClose
      >
        <Form form={certifyForm} layout="vertical">
          <Form.Item
            name="space"
            label={t('kb_library_space_id')}
            rules={[{ required: true }]}
            extra={t('kb_library_space_id_hint')}
          >
            <Input placeholder="space UUID" />
          </Form.Item>
          <Form.Item name="name" label={t('kb_taxonomy_name')} rules={[{ required: true }]}>
            <Input placeholder="IFRS 参考库" />
          </Form.Item>
          <Form.Item name="category" label={t('kb_library_category')} initialValue="other">
            <Select
              options={[
                { value: 'ifrs', label: t('kb_library_cat_ifrs') },
                { value: 'cas', label: t('kb_library_cat_cas') },
                { value: 'ipo_cases', label: t('kb_library_cat_ipo_cases') },
                { value: 'other', label: t('kb_library_cat_other') },
              ]}
            />
          </Form.Item>
          <Form.Item name="description" label={t('kb_library_description')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default LibraryReferencesPanel;
