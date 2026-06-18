import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, Upload, message, Typography } from 'antd';
import { ReloadOutlined, DeleteOutlined, UploadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { documentApi } from '../../api/documents';

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
            onClick={() => handleDelete(record.id)}
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
              Authorization: `Bearer ${localStorage.getItem('ey-auth') ? JSON.parse(localStorage.getItem('ey-auth')!).token : ''}`,
            }}
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
      />
    </Card>
  );
}
