/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useState } from 'react';
import { Card, Table, Button, Space, Upload, message, Modal, Empty } from 'antd';
import { ReloadOutlined, DeleteOutlined, UploadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import { documentApi } from '../../api/documents';
import { getAuthToken } from '../../api/client';

interface Document {
  id: string;
  title: string;
  file_type: string;
  status: string;
  chunk_count: number;
  category_name?: string;
  created_at: string;
}

const tagStyleMap: Record<string, { bg: string; text: string; border: string }> = {
  active: { bg: '#EBF6ED', text: '#2E6930', border: '#D3ECDB' },
  processing: { bg: '#EAF2FD', text: '#1A56DB', border: '#D0E1FD' },
  failed: { bg: '#FDF2F2', text: '#C81E1E', border: '#FDE8E8' },
  draft: { bg: '#F3F4F6', text: '#4B5563', border: '#E5E7EB' },
  uploading: { bg: '#FFF8EB', text: '#B85B35', border: '#FFEBD3' },
  expired: { bg: '#F3F4F6', text: '#9CA3AF', border: '#E5E7EB' },
};

export default function KnowledgeBasePage() {
  const { t } = useTranslation('common');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const data = await documentApi.getDocuments();
      setDocuments(data.results || data);
    } catch {
      message.error(t('upload_error'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const handleReindex = async (id: string) => {
    try {
      await documentApi.reindexDocument(id);
      message.success(t('reindex_success'));
      loadDocuments();
    } catch {
      message.error(t('upload_error'));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await documentApi.deleteDocument(id);
      message.success(t('delete_success'));
      loadDocuments();
    } catch {
      message.error(t('upload_error'));
    }
  };

  const confirmDelete = (id: string, title: string) => {
    Modal.confirm({
      title: t('delete_confirm'),
      content: t('delete_confirm_content').replace('"%s"', `"${title}"`),
      okText: t('delete'),
      okType: 'danger',
      cancelText: t('cancel'),
      onOk: () => handleDelete(id),
    });
  };

  const ALLOWED_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx', '.pptx'];
  const MAX_FILE_SIZE_MB = 50;

  const beforeUpload = (file: File) => {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    const isValidType = ALLOWED_EXTENSIONS.includes(ext);
    if (!isValidType) {
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

  const statusLabels: Record<string, string> = {
    active: t('status_active'),
    processing: t('status_processing'),
    failed: t('status_failed'),
    draft: t('status_draft'),
    uploading: t('status_uploading'),
    expired: t('status_expired'),
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
    {
      title: t('kb_actions'),
      key: 'actions',
      width: 150,
      render: (_: unknown, record: Document) => (
        <Space size="middle">
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => handleReindex(record.id)}
            disabled={record.status === 'processing'}
            style={{ borderRadius: 6 }}
          />
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => confirmDelete(record.id, record.title)}
            style={{ borderRadius: 6 }}
          />
        </Space>
      ),
    },
  ];

  return (
    <div className="page" style={{ background: 'transparent' }}>
      <div className="page-inner">
        <div className="page-head" style={{ marginBottom: 32 }}>
          <h1 className="page-title">{t('nav_knowledge')}</h1>
        </div>
        <Card
          styles={{ body: { padding: '28px 28px 24px' } }}
          style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
            <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 18, color: 'var(--color-text)' }}>
              {t('document_list') || 'Document List'}
            </span>
            <Space size="middle">
          <Upload
            action="/api/v1/documents/"
            headers={{
              Authorization: `Bearer ${getAuthToken()}`,
            }}
            accept={ALLOWED_EXTENSIONS.join(',')}
            beforeUpload={beforeUpload}
            onChange={(info) => {
              if (info.file.status === 'done') {
                message.success(t('upload_success'));
                loadDocuments();
              } else if (info.file.status === 'error') {
                message.error(t('upload_error'));
              }
            }}
          >
            <Button icon={<UploadOutlined />}>{t('upload')}</Button>
          </Upload>
          <Button icon={<ReloadOutlined />} onClick={loadDocuments}>
            {t('refresh')}
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={documents}
        loading={loading}
        rowKey="id"
        pagination={{ pageSize: 10 }}
        scroll={{ x: 'max-content' }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('no_documents')}
            />
          ),
        }}
      />
    </Card>
    </div></div>
  );
}
