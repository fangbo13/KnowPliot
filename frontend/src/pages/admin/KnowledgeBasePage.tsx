import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, Upload, message, Modal, Empty } from 'antd';
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

const statusColors: Record<string, string> = {
  active: 'green',
  processing: 'blue',
  failed: 'red',
  draft: 'default',
  uploading: 'orange',
  expired: 'gray',
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
    { title: t('kb_category'), dataIndex: 'category_name', key: 'category', width: 120 },
    { title: t('kb_type'), dataIndex: 'file_type', key: 'file_type', width: 80 },
    { title: t('kb_chunks'), dataIndex: 'chunk_count', key: 'chunk_count', width: 80 },
    {
      title: t('kb_status'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => (
        <Tag color={statusColors[status] || 'default'}>
          {statusLabels[status] || status}
        </Tag>
      ),
    },
    { title: t('kb_created'), dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: t('kb_actions'),
      key: 'actions',
      width: 150,
      render: (_: unknown, record: Document) => (
        <Space>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => handleReindex(record.id)}
            disabled={record.status === 'processing'}
          />
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => confirmDelete(record.id, record.title)}
          />
        </Space>
      ),
    },
  ];

  return (
    <div className="page"><div className="page-inner">
      <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 18, margin: 0 }}>
          {t('nav_knowledge')}
        </span>
        <Space>
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
