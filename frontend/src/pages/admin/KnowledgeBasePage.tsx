/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useState } from 'react';
import { Card, Table, Button, Space, Upload, message, Modal, Input, Alert, Tag, Drawer, Tabs, Spin, Tooltip } from 'antd';
import {
  InboxOutlined,
  DownloadOutlined,
  ReloadOutlined,
  UploadOutlined,
  EditOutlined,
  FileTextOutlined,
  HistoryOutlined,
  SaveOutlined,
  RollbackOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import {
  ALLOWED_DOCUMENT_EXTENSIONS,
  documentApi,
  isSupportedDocumentFile,
} from '../../api/documents';
import { useAuthorization } from '../../auth/CapabilityProvider';
import { MarkdownEditor } from '../../components/knowledge/MarkdownEditor';
import { DiffPreview } from '../../components/knowledge/DiffPreview';
import type { DiffPreviewData } from '../../components/knowledge/DiffPreview';

interface Document {
  id: string;
  title: string;
  file_type: string;
  status: string;
  chunk_count: number;
  category_name?: string;
  created_at: string;
  // KB-12-Features §4: version metadata fields returned by DocumentSerializer
  text_content?: string;
  version?: number;
  parent_document?: string | null;
  effective_from?: string;
  effective_to?: string | null;
}

/** KB-12-Features §2: Version info returned by GET /documents/{id}/versions/ */
interface VersionInfo {
  id: string;
  version: number;
  status: string;
  effective_from: string;
  effective_to: string | null;
  created_at: string;
  title?: string;
}

// Bug#6/#21: theme-aware tag colours via CSS variables (auto dark-mode adaptation)
const tagStyleMap: Record<string, { bg: string; text: string; border: string }> = {
  active: { bg: 'rgba(var(--color-success-rgb), 0.12)', text: 'var(--color-success)', border: 'rgba(var(--color-success-rgb), 0.3)' },
  processing: { bg: 'rgba(var(--color-accent-rgb), 0.12)', text: 'var(--color-accent)', border: 'rgba(var(--color-accent-rgb), 0.3)' },
  failed: { bg: 'rgba(var(--color-error-rgb), 0.12)', text: 'var(--color-error)', border: 'rgba(var(--color-error-rgb), 0.3)' },
  draft: { bg: 'var(--color-fill)', text: 'var(--color-text-secondary)', border: 'var(--color-border)' },
  uploading: { bg: 'rgba(var(--color-warning-rgb), 0.12)', text: 'var(--color-warning)', border: 'rgba(var(--color-warning-rgb), 0.3)' },
  expired: { bg: 'var(--color-fill)', text: 'var(--color-text-tertiary)', border: 'var(--color-border-secondary)' },
  stale: { bg: 'rgba(var(--color-warning-rgb), 0.12)', text: 'var(--color-warning)', border: 'rgba(var(--color-warning-rgb), 0.3)' },
  archived: { bg: 'var(--color-fill)', text: 'var(--color-text-tertiary)', border: 'var(--color-border)' },
};

export default function KnowledgeBasePage() {
  const { t } = useTranslation('common');
  const access = useAuthorization();
  const canRead = access.has('knowledge.read');
  const canManage = access.has('knowledge.manage');
  const canIndex = access.has('knowledge.index');
  const canDownload = access.has('knowledge.download');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  // Bug#21: tutorial banner + edit modal state
  const [showTutorial, setShowTutorial] = useState(() => !localStorage.getItem('ey-kb-tutorial-dismissed'));
  const [editTarget, setEditTarget] = useState<{ id: string; title: string; category?: string } | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  // KB-12-Features §2: Version management drawer state
  const [versionDrawer, setVersionDrawer] = useState<Document | null>(null);
  const [editText, setEditText] = useState('');
  const [originalText, setOriginalText] = useState('');
  const [diffData, setDiffData] = useState<DiffPreviewData | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionSaving, setVersionSaving] = useState(false);
  const [versionReason, setVersionReason] = useState('');
  const [rollbackSaving, setRollbackSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('content');

  const loadDocuments = useCallback(async () => {
    if (!canRead) return;
    setLoading(true);
    try {
      const data = await documentApi.getDocuments();
      setDocuments(data.results || data);
    } catch {
      message.error(t('upload_error'));
    } finally {
      setLoading(false);
    }
  }, [canRead, t]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  const handleReindex = async (id: string) => {
    if (!canIndex) return;
    try {
      await documentApi.reindexDocument(id);
      message.success(t('reindex_success'));
      loadDocuments();
    } catch {
      message.error(t('upload_error'));
    }
  };

  const handleArchive = async (id: string) => {
    if (!canManage) return;
    try {
      await documentApi.archiveDocument(id);
      message.success(t('archive_success'));
      loadDocuments();
    } catch {
      message.error(t('upload_error'));
    }
  };

  const handleDownload = async (record: Document) => {
    if (!canDownload) return;
    try {
      const { blob, filename } = await documentApi.downloadDocument(
        record.id,
        record.title,
      );
      const objectUrl = URL.createObjectURL(blob);
      try {
        const anchor = window.document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = filename;
        window.document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
      message.success(t('download_success'));
    } catch {
      message.error(t('download_error'));
    }
  };

  // Bug#21: edit document metadata
  const handleEditOpen = (record: Document) => {
    setEditTarget({ id: record.id, title: record.title, category: record.category_name });
    setEditTitle(record.title);
    setEditCategory(record.category_name || '');
  };

  const handleEditSave = async () => {
    if (!editTarget) return;
    setEditSaving(true);
    try {
      await documentApi.updateDocument(editTarget.id, { title: editTitle, category_name: editCategory });
      message.success(t('kb_update_success'));
      setEditTarget(null);
      loadDocuments();
    } catch {
      message.error(t('kb_update_failed'));
    } finally {
      setEditSaving(false);
    }
  };

  const dismissTutorial = () => {
    localStorage.setItem('ey-kb-tutorial-dismissed', 'true');
    setShowTutorial(false);
  };

  const confirmArchive = (id: string, title: string) => {
    if (!canManage) return;
    Modal.confirm({
      title: t('archive_confirm'),
      content: t('archive_confirm_content').replace('%s', title),
      okText: t('archive'),
      cancelText: t('cancel'),
      onOk: () => handleArchive(id),
    });
  };

  // KB-12-Features §2: Version management handlers
  const openVersionDrawer = (record: Document) => {
    setVersionDrawer(record);
    setEditText(record.text_content || '');
    setOriginalText(record.text_content || '');
    setDiffData(null);
    setDiffError(null);
    setVersionReason('');
    setActiveTab('content');
    void loadVersions(record.id);
  };

  const closeVersionDrawer = () => {
    setVersionDrawer(null);
    setDiffData(null);
    setDiffError(null);
    setVersionReason('');
  };

  const loadVersions = async (id: string) => {
    setVersionsLoading(true);
    try {
      const data = await documentApi.getVersions(id);
      setVersions(data.results || data || []);
    } catch {
      setVersions([]);
    } finally {
      setVersionsLoading(false);
    }
  };

  const handlePreviewDiff = async () => {
    if (!versionDrawer) return;
    setDiffLoading(true);
    setDiffError(null);
    try {
      const data = await documentApi.previewDiff(versionDrawer.id, editText);
      setDiffData(data);
    } catch (err) {
      setDiffError(err instanceof Error ? err.message : t('kb_version_failed'));
    } finally {
      setDiffLoading(false);
    }
  };

  const handleCreateVersion = async () => {
    if (!versionDrawer) return;
    setVersionSaving(true);
    try {
      await documentApi.createVersion(versionDrawer.id, {
        text_content: editText,
        reason: versionReason || undefined,
      });
      message.success(t('kb_version_created'));
      setVersionReason('');
      setDiffData(null);
      setOriginalText(editText);
      void loadVersions(versionDrawer.id);
      loadDocuments();
    } catch {
      message.error(t('kb_version_failed'));
    } finally {
      setVersionSaving(false);
    }
  };

  const handleRollback = (record: VersionInfo) => {
    if (!versionDrawer || !canManage) return;
    Modal.confirm({
      title: t('kb_rollback_confirm', { number: record.version }),
      okText: t('kb_rollback'),
      cancelText: t('cancel'),
      onOk: async () => {
        setRollbackSaving(true);
        try {
          await documentApi.rollbackVersion(versionDrawer.id, {
            target_version: record.version,
          });
          message.success(t('kb_rollback_success'));
          void loadVersions(versionDrawer.id);
          loadDocuments();
          try {
            const doc = await documentApi.getDocument(versionDrawer.id);
            setEditText(doc.text_content || '');
            setOriginalText(doc.text_content || '');
          } catch {
            // keep current text if fetch fails
          }
        } catch {
          message.error(t('kb_rollback_failed'));
        } finally {
          setRollbackSaving(false);
        }
      },
    });
  };

  const MAX_FILE_SIZE_MB = 50;

  const beforeUpload = (file: File) => {
    if (!canManage) return Upload.LIST_IGNORE;
    if (!isSupportedDocumentFile(file.name)) {
      message.error(t('file_type_error'));
      return Upload.LIST_IGNORE;
    }
    const isLt50M = file.size / 1024 / 1024 < MAX_FILE_SIZE_MB;
    if (!isLt50M) {
      message.error(t('file_size_error', { maxSize: MAX_FILE_SIZE_MB }));
      return Upload.LIST_IGNORE;
    }
    return true;
  };

  if (!canRead) return null;

  const statusLabels: Record<string, string> = {
    active: t('status_active'),
    processing: t('status_processing'),
    failed: t('status_failed'),
    draft: t('status_draft'),
    uploading: t('status_uploading'),
    expired: t('status_expired'),
    stale: t('status_stale'),
    archived: t('status_archived'),
  };

  const columns: ColumnsType<Document> = [
    { title: t('kb_title'), dataIndex: 'title', key: 'title', ellipsis: true },
    { title: t('kb_category'), dataIndex: 'category_name', key: 'category', width: 140 },
    { title: t('kb_type'), dataIndex: 'file_type', key: 'file_type', width: 90 },
    { title: t('kb_chunks'), dataIndex: 'chunk_count', key: 'chunk_count', width: 90 },
    {
      title: t('kb_status'),
      dataIndex: 'status',
      key: 'status',
      width: 130,
      render: (status: string) => {
        const style = tagStyleMap[status] || { bg: 'var(--color-fill)', text: 'var(--color-text-secondary)', border: 'var(--color-border-secondary)' };
        return (
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '4px 12px',
            borderRadius: '999px',
            fontSize: '12px',
            fontWeight: 500,
            background: style.bg,
            color: style.text,
            border: `1px solid ${style.border}`,
            lineHeight: 1,
            whiteSpace: 'nowrap'
          }}>
            {statusLabels[status] || status}
          </span>
        );
      },
    },
    { title: t('kb_created'), dataIndex: 'created_at', key: 'created_at', width: 180 },
  ];

  if (canDownload || canIndex || canManage) {
    columns.push({
      title: t('kb_actions'),
      key: 'actions',
      width: 250,
      render: (_: unknown, record: Document) => (
        <Space size="middle">
          {canDownload && (
            <Button
              size="small"
              icon={<DownloadOutlined />}
              aria-label={t('download')}
              title={t('download')}
              onClick={() => handleDownload(record)}
              style={{ borderRadius: 6 }}
            />
          )}
          {canIndex && (
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => handleReindex(record.id)}
              disabled={record.status === 'processing'}
              aria-label={t('reindex')}
              title={t('reindex')}
              style={{ borderRadius: 6 }}
            />
          )}
          {canManage && (
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEditOpen(record)}
              disabled={record.status === 'archived'}
              aria-label={t('kb_edit')}
              title={t('kb_edit')}
              style={{ borderRadius: 6 }}
            />
          )}
          {canManage && (
            <Tooltip title={t('kb_versions')}>
              <Button
                size="small"
                icon={<HistoryOutlined />}
                onClick={() => openVersionDrawer(record)}
                aria-label={t('kb_versions')}
                style={{ borderRadius: 6 }}
              />
            </Tooltip>
          )}
          {canManage && (
            <Button
              size="small"
              icon={<InboxOutlined />}
              onClick={() => confirmArchive(record.id, record.title)}
              disabled={record.status === 'archived'}
              aria-label={t('archive')}
              title={t('archive')}
              style={{ borderRadius: 6 }}
            />
          )}
        </Space>
      ),
    });
  }

  return (
    <div className="page" style={{ background: 'transparent' }}>
      <div className="page-inner">
        <div className="page-head" style={{ marginBottom: 32 }}>
          <h1 className="page-title">{t('nav_knowledge')}</h1>
        </div>
        <Card
          styles={{ body: { padding: '28px 28px 24px' } }}
          className="glass-panel hover-lift"
          style={{ borderRadius: 'var(--radius-lg)' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 18, color: 'var(--color-text)' }}>
              {t('document_list') || 'Document List'}
            </span>
            <Space size="middle">
              {canManage && (
                <Upload
                  customRequest={async ({ file, onError, onSuccess }) => {
                    try {
                      const result = await documentApi.uploadDocument(file as File);
                      onSuccess?.(result);
                    } catch (error) {
                      onError?.(
                        error instanceof Error
                          ? error
                          : new Error('Document upload failed'),
                      );
                    }
                  }}
                  accept={ALLOWED_DOCUMENT_EXTENSIONS.join(',')}
                  beforeUpload={beforeUpload}
                  showUploadList={false}
                  onChange={(info) => {
                    if (info.file.status === 'done') {
                      message.success(t('upload_success'));
                      loadDocuments();
                    } else if (info.file.status === 'error') {
                      message.error(t('upload_error'));
                    }
                  }}
                >
                  <Button type="primary" icon={<UploadOutlined />} aria-label={t('upload')} style={{ borderRadius: 8 }} className="btn-press">
                    {t('upload')}
                  </Button>
                </Upload>
              )}
              {canManage && (
                <Tag icon={<FileTextOutlined />} style={{ borderRadius: 6, border: '1px solid rgba(var(--color-accent-rgb), 0.3)', background: 'rgba(var(--color-accent-rgb), 0.08)', color: 'var(--color-accent)' }}>
                  {t('kb_md_recommended')}
                </Tag>
              )}
              <Button icon={<ReloadOutlined />} aria-label={t('refresh')} onClick={loadDocuments} style={{ borderRadius: 8 }} className="btn-press">
                {t('refresh')}
              </Button>
            </Space>
          </div>

          {showTutorial && canManage && (
            <Alert
              type="info"
              showIcon
              icon={<FileTextOutlined />}
              message={t('kb_upload_tutorial_title')}
              description={t('kb_upload_tutorial_desc')}
              closable
              onClose={dismissTutorial}
              action={
                <button className="msg-action-btn" onClick={dismissTutorial} style={{ whiteSpace: 'nowrap' }}>
                  {t('kb_upload_tutorial_dismiss')}
                </button>
              }
              style={{ marginBottom: 16 }}
            />
          )}

          <Table
            columns={columns}
            dataSource={documents}
            loading={loading}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            scroll={{ x: 'max-content' }}
            locale={{
              emptyText: (
                <div className="section-enter" style={{ padding: '60px 0', textAlign: 'center' }}>
                  <div style={{ fontSize: 48, color: 'var(--color-border-secondary)', fontFamily: "'Fraunces', serif" }}>K</div>
                  <div style={{ marginTop: 16, color: 'var(--color-text-secondary)', fontSize: 15 }}>{t('no_documents') || 'No documents'}</div>
                </div>
              ),
            }}
          />
        </Card>

        {editTarget && (
          <Modal
            open
            title={t('kb_edit_title')}
            okText={t('kb_save')}
            cancelText={t('kb_cancel')}
            confirmLoading={editSaving}
            onOk={handleEditSave}
            onCancel={() => setEditTarget(null)}
          >
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>{t('kb_document_title')}</label>
              <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} placeholder={t('kb_document_title')} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>{t('kb_document_category')}</label>
              <Input value={editCategory} onChange={(e) => setEditCategory(e.target.value)} placeholder={t('kb_document_category')} />
            </div>
          </Modal>
        )}

        {versionDrawer && (
          <Drawer
            title={`${versionDrawer.title} — ${t('kb_versions')}`}
            open
            width={720}
            onClose={closeVersionDrawer}
            destroyOnClose
          >
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              items={[
                {
                  key: 'content',
                  label: t('kb_edit_content'),
                  children: (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      <MarkdownEditor
                        value={editText}
                        onChange={setEditText}
                        readOnly={!canManage}
                        placeholder={t('kb_editor_placeholder')}
                        minHeight={280}
                      />
                      {canManage && (
                        <>
                          <div style={{ display: 'flex', gap: 8 }}>
                            <Button
                              icon={<FileTextOutlined />}
                              onClick={handlePreviewDiff}
                              loading={diffLoading}
                              disabled={editText === originalText}
                            >
                              {t('kb_diff_preview')}
                            </Button>
                            <Button
                              type="primary"
                              icon={<SaveOutlined />}
                              onClick={handleCreateVersion}
                              loading={versionSaving}
                              disabled={editText === originalText}
                            >
                              {t('kb_editor_save_version')}
                            </Button>
                          </div>
                          <Input.TextArea
                            value={versionReason}
                            onChange={(e) => setVersionReason(e.target.value)}
                            placeholder={t('kb_diff_reason_placeholder')}
                            autoSize={{ minRows: 2, maxRows: 4 }}
                          />
                          {(diffData || diffLoading || diffError) && (
                            <DiffPreview
                              data={diffData}
                              loading={diffLoading}
                              error={diffError}
                            />
                          )}
                        </>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'versions',
                  label: t('kb_versions'),
                  children: (
                    <Spin spinning={versionsLoading}>
                      {versions.length === 0 ? (
                        <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--color-text-tertiary)' }}>
                          {t('no_documents') || 'No versions'}
                        </div>
                      ) : (
                        <Space direction="vertical" style={{ width: '100%' }}>
                          {versions.map((v) => (
                            <Card
                              key={v.id}
                              size="small"
                              style={{
                                borderColor: 'var(--color-border)',
                                background: 'var(--color-bg-container)',
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div>
                                  <Space size="small">
                                    <Tag color="blue">{t('kb_version')} {v.version}</Tag>
                                    <Tag>{v.status}</Tag>
                                  </Space>
                                  <div style={{ marginTop: 8, fontSize: 13, color: 'var(--color-text-secondary)' }}>
                                    <div>{t('kb_effective_from')}: {v.effective_from ? new Date(v.effective_from).toLocaleString() : '—'}</div>
                                    <div>{t('kb_effective_to')}: {v.effective_to ? new Date(v.effective_to).toLocaleString() : '—'}</div>
                                    <div>{t('kb_created')}: {new Date(v.created_at).toLocaleString()}</div>
                                  </div>
                                </div>
                                {canManage && (
                                  <Button
                                    size="small"
                                    icon={<RollbackOutlined />}
                                    onClick={() => handleRollback(v)}
                                    loading={rollbackSaving}
                                    disabled={v.version === versionDrawer.version}
                                  >
                                    {t('kb_rollback')}
                                  </Button>
                                )}
                              </div>
                            </Card>
                          ))}
                        </Space>
                      )}
                    </Spin>
                  ),
                },
              ]}
            />
          </Drawer>
        )}
      </div>
    </div>
  );
}
