import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, Upload, message, Typography, Modal, Empty } from 'antd';
import { ReloadOutlined, DeleteOutlined, UploadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { documentApi } from '../../api/documents';
import { getAuthToken } from '../../api/client';

const { Title } = Typography;

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

const statusLabels: Record<string, string> = {
  active: 'Active',
  processing: 'Processing',
  failed: 'Failed',
  draft: 'Draft',
  uploading: 'Uploading',
  expired: 'Expired',
};

const ALLOWED_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx', '.pptx'];
const MAX_FILE_SIZE_MB = 50;

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const data = await documentApi.getDocuments();
      setDocuments(data.results || data);
    } catch {
      message.error('Failed to load documents');
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
      message.success('Reindexing started');
      loadDocuments();
    } catch {
      message.error('Failed to start reindexing');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await documentApi.deleteDocument(id);
      message.success('Document deleted');
      loadDocuments();
    } catch {
      message.error('Failed to delete document');
    }
  };

  const confirmDelete = (id: string, title: string) => {
    Modal.confirm({
      title: 'Delete Document',
      content: `Are you sure you want to delete "${title}"? This action cannot be undone.`,
      okText: 'Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: () => handleDelete(id),
    });
  };

  const beforeUpload = (file: File) => {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    const isValidType = ALLOWED_EXTENSIONS.includes(ext);
    if (!isValidType) {
      message.error('Only PDF, Word, Text, CSV, Excel, and PowerPoint files are allowed.');
      return Upload.LIST_IGNORE;
    }
    const isLt50M = file.size / 1024 / 1024 < MAX_FILE_SIZE_MB;
    if (!isLt50M) {
      message.error(`File must be smaller than ${MAX_FILE_SIZE_MB}MB.`);
      return Upload.LIST_IGNORE;
    }
    return true;
  };

  const columns: ColumnsType<Document> = [
    { title: 'Title', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: 'Category', dataIndex: 'category_name', key: 'category', width: 120 },
    { title: 'Type', dataIndex: 'file_type', key: 'file_type', width: 80 },
    { title: 'Chunks', dataIndex: 'chunk_count', key: 'chunk_count', width: 80 },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => (
        <Tag color={statusColors[status] || 'default'}>
          {statusLabels[status] || status}
        </Tag>
      ),
    },
    { title: 'Created', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: 'Actions',
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
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>Knowledge Base</Title>
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
                message.success('Document uploaded');
                loadDocuments();
              } else if (info.file.status === 'error') {
                message.error('Upload failed');
              }
            }}
          >
            <Button icon={<UploadOutlined />}>Upload</Button>
          </Upload>
          <Button icon={<ReloadOutlined />} onClick={loadDocuments}>
            Refresh
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
              description="No documents yet. Upload your first document to get started."
            />
          ),
        }}
      />
    </Card>
  );
}
