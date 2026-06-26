/** Crawler Admin Page — V4.1 KB-V4.1-011~017 frontend UI.

Admin-only page for submitting URL crawl requests and viewing
crawled document status. Includes withdraw (takedown) functionality
for copyright compliance.
 **/

import { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Typography, Input, Switch,
  Modal, message, Tooltip, Spin, Alert, Form,
} from 'antd';
import {
  GlobalOutlined, SendOutlined, StopOutlined,
  ReloadOutlined, DeleteOutlined, LinkOutlined,
  WarningOutlined, CheckCircleOutlined, ClockCircleOutlined,
  CloseCircleOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import {
  submitCrawl, listCrawledDocuments, withdrawCrawl, withdrawByURL,
  type CrawledDocument, type CrawlRequest,
} from '../../api/crawler';

const { Title, Text } = Typography;

// Status color mapping
const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  fetching: 'processing',
  parsing: 'processing',
  cleaning: 'processing',
  embedding: 'processing',
  active: 'success',
  failed: 'error',
  withdrawn: 'warning',
  duplicate_skipped: 'orange',
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  pending: <ClockCircleOutlined />,
  fetching: <Spin size="small" />,
  parsing: <Spin size="small" />,
  cleaning: <Spin size="small" />,
  embedding: <Spin size="small" />,
  active: <CheckCircleOutlined />,
  failed: <CloseCircleOutlined />,
  withdrawn: <StopOutlined />,
  duplicate_skipped: <ExclamationCircleOutlined />,
};

export default function CrawlerAdminPage() {
  const { t } = useTranslation('admin');
  const [crawlDocs, setCrawlDocs] = useState<CrawledDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [crawlUrl, setCrawlUrl] = useState('');
  const [internalOnly, setInternalOnly] = useState(false);
  const [polling, setPolling] = useState(false);

  // Fetch crawl documents
  const fetchDocs = useCallback(async () => {
    setLoading(true);
    try {
      const docs = await listCrawledDocuments();
      setCrawlDocs(docs);
    } catch (err: any) {
      message.error(err.response?.data?.detail || t('crawler_fetch_error', 'Failed to fetch crawl documents'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // V4.2 UI-V4.2-001: Empty dependency array — mount-only fetch.
  // Previously [fetchDocs] caused API re-trigger every time useCallback recreated
  // fetchDocs (e.g. on language switch or HMR). Now mount-once, refreshed by
  // polling interval or manual Refresh button click.
  // [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-001]
  useEffect(() => {
    fetchDocs();
  }, []);

  // Poll for status updates when pending tasks exist
  useEffect(() => {
    const hasPending = crawlDocs.some(d =>
      ['pending', 'fetching', 'parsing', 'cleaning', 'embedding'].includes(d.crawl_status)
    );
    if (hasPending && !polling) {
      setPolling(true);
      const interval = setInterval(() => {
        fetchDocs();
      }, 5000);
      return () => {
        clearInterval(interval);
        setPolling(false);
      };
    }
    if (!hasPending) {
      setPolling(false);
    }
  }, [crawlDocs, polling, fetchDocs]);

  // Submit crawl request
  const handleSubmit = async () => {
    if (!crawlUrl.trim()) {
      message.warning(t('crawler_url_required', 'Please enter a URL'));
      return;
    }
    setSubmitting(true);
    try {
      const request: CrawlRequest = {
        url: crawlUrl.trim(),
        internal_only: internalOnly,
      };
      await submitCrawl(request);
      message.success(t('crawler_submit_success', 'Crawl request submitted successfully'));
      setCrawlUrl('');
      setInternalOnly(false);
      fetchDocs();
    } catch (err: any) {
      const errorDetail = err.response?.data?.url?.[0] || err.response?.data?.detail || 'Submission failed';
      message.error(errorDetail);
    } finally {
      setSubmitting(false);
    }
  };

  // Withdraw a crawled document
  const handleWithdraw = async (doc: CrawledDocument) => {
    Modal.confirm({
      title: t('crawler_withdraw_confirm_title', 'Withdraw Crawled Content'),
      content: t('crawler_withdraw_confirm', `Are you sure you want to withdraw content from "${doc.source_url}"? This will remove it from active search.`),
      okText: t('crawler_withdraw', 'Withdraw'),
      okType: 'danger',
      onOk: async () => {
        try {
          await withdrawCrawl(doc.id);
          message.success(t('crawler_withdraw_success', 'Content withdrawn successfully'));
          fetchDocs();
        } catch (err: any) {
          message.error(err.response?.data?.detail || 'Withdraw failed');
        }
      },
    });
  };

  // Table columns
  const columns: ColumnsType<CrawledDocument> = [
    {
      title: t('crawler_source_url', 'Source URL'),
      dataIndex: 'source_url',
      key: 'source_url',
      width: 200,
      render: (url: string) => (
        <Tooltip title={url}>
          <Text ellipsis style={{ maxWidth: 180 }}>
            <LinkOutlined /> {url}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: t('crawler_title', 'Title'),
      dataIndex: 'title_extracted',
      key: 'title_extracted',
      width: 150,
      render: (title: string) => <Text ellipsis style={{ maxWidth: 140 }}>{title || '-'}</Text>,
    },
    {
      title: t('crawler_status', 'Status'),
      dataIndex: 'crawl_status',
      key: 'crawl_status',
      width: 120,
      render: (status: string) => (
        <Tag color={STATUS_COLORS[status]} icon={STATUS_ICONS[status]}>
          {t(`crawler_status_${status}`, status)}
        </Tag>
      ),
      filters: Object.keys(STATUS_COLORS).map(s => ({ text: s, value: s })),
      onFilter: (value, record) => record.crawl_status === value,
    },
    {
      title: t('crawler_internal', 'Internal Only'),
      dataIndex: 'internal_only',
      key: 'internal_only',
      width: 80,
      render: (internal: boolean) => internal ? <Tag color="orange">🔒</Tag> : <Tag color="green">🌐</Tag>,
    },
    {
      title: t('crawler_submitted_by', 'Submitted By'),
      dataIndex: 'submitted_by_email',
      key: 'submitted_by_email',
      width: 120,
    },
    {
      title: t('crawler_submitted_at', 'Submitted At'),
      dataIndex: 'submitted_at',
      key: 'submitted_at',
      width: 130,
      render: (date: string) => date ? new Date(date).toLocaleString() : '-',
    },
    {
      title: t('crawler_error', 'Error'),
      dataIndex: 'error_message',
      key: 'error_message',
      width: 150,
      render: (error: string) => error ? (
        <Tooltip title={error}>
          <Tag color="error"><WarningOutlined /> {error.slice(0, 50)}</Tag>
        </Tooltip>
      ) : null,
    },
    {
      title: t('crawler_actions', 'Actions'),
      key: 'actions',
      width: 80,
      render: (_, record) => record.crawl_status === 'active' ? (
        <Button
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleWithdraw(record)}
        >
          {t('crawler_withdraw', 'Withdraw')}
        </Button>
      ) : null,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <GlobalOutlined /> {t('crawler_title', 'Web Crawler')}
      </Title>

      {/* Submit URL form */}
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              placeholder={t('crawler_url_placeholder', 'Enter URL to crawl (e.g., https://example.com/doc)')}
              value={crawlUrl}
              onChange={(e) => setCrawlUrl(e.target.value)}
              onPressEnter={handleSubmit}
              style={{ width: 'calc(100% - 200px)' }}
              prefix={<LinkOutlined />}
            />
            <Switch
              checked={internalOnly}
              onChange={setInternalOnly}
              checkedChildren={t('crawler_internal_only', '🔒 Internal')}
              unCheckedChildren={t('crawler_public', '🌐 Public')}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              loading={submitting}
              onClick={handleSubmit}
            >
              {t('crawler_submit', 'Submit')}
            </Button>
          </Space.Compact>
          {polling && (
            <Alert
              type="info"
              message={t('crawler_polling', 'Auto-refreshing: pending tasks detected')}
              showIcon
              banner
            />
          )}
        </Space>
      </Card>

      {/* Crawl documents table */}
      <Card>
        <Space style={{ marginBottom: 8 }}>
          <Button icon={<ReloadOutlined />} onClick={fetchDocs} loading={loading}>
            {t('crawler_refresh', 'Refresh')}
          </Button>
        </Space>
        <Table
          dataSource={crawlDocs}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 900 }}
        />
      </Card>
    </div>
  );
}
