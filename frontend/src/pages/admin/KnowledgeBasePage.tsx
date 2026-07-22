/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useState } from 'react';
import { Card, Table, Button, Space, Upload, message, Modal, Input, Alert, Tag } from 'antd';
import {
  InboxOutlined,
  DownloadOutlined,
  ReloadOutlined,
  UploadOutlined,
  EditOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import {
  ALLOWED_DOCUMENT_EXTENSIONS,
  documentApi,
  isSupportedDocumentFile,
} from '../../api/documents';
import { useAuthorization } from '../../auth/CapabilityProvider';

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
      width: 190,
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
      </div>
    </div>
  );
}
