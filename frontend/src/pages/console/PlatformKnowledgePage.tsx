/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Input, Select, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Link, useSearchParams } from 'react-router-dom';

import { getRateLimitDetails, isAbortError } from '../../api/client';
import {
  platformKnowledgeApi,
  type PlatformKnowledgeDocument,
  type PlatformKnowledgeFilters,
} from '../../api/platformKnowledge';

const { Title, Paragraph, Text } = Typography;

function scopeName(value: { name: string } | null): string {
  return value?.name || 'Unassigned';
}

export default function PlatformKnowledgePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState<PlatformKnowledgeDocument[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState(searchParams.get('q') ?? '');
  const controllerRef = useRef<AbortController | null>(null);
  const sequence = useRef(0);

  const filters: PlatformKnowledgeFilters = {
    q: searchParams.get('q') ?? undefined,
    organization_id: searchParams.get('organization_id') ?? undefined,
    business_line_id: searchParams.get('business_line_id') ?? undefined,
    work_group_id: searchParams.get('work_group_id') ?? undefined,
    space_id: searchParams.get('space_id') ?? undefined,
    status: searchParams.get('status') ?? undefined,
  };
  const filterKey = JSON.stringify(filters);

  const load = useCallback(async (cursor?: string, append = false) => {
    const current = ++sequence.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const page = await platformKnowledgeApi.list({ ...JSON.parse(filterKey), cursor }, controller.signal);
      if (controller.signal.aborted || current !== sequence.current) return;
      setRows((prior) => append ? [...prior, ...page.results] : page.results);
      setNextCursor(page.next_cursor);
    } catch (loadError: unknown) {
      if (isAbortError(loadError) || controller.signal.aborted || current !== sequence.current) return;
      const rateLimit = getRateLimitDetails(loadError);
      setError(rateLimit
        ? `请求过于频繁${rateLimit.retryAfterSeconds == null ? '' : `，请在 ${rateLimit.retryAfterSeconds} 秒后重试`}`
        : '无法加载平台知识元数据。');
    } finally {
      if (!controller.signal.aborted && current === sequence.current) setLoading(false);
    }
  }, [filterKey]);

  useEffect(() => {
    void load();
    return () => {
      sequence.current += 1;
      controllerRef.current?.abort();
    };
  }, [load]);

  const updateFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value.trim()) next.set(key, value.trim());
    else next.delete(key);
    setSearchParams(next);
  };

  const columns: ColumnsType<PlatformKnowledgeDocument> = [
    { title: 'Document', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: 'Organization', key: 'organization', render: (_, row) => scopeName(row.organization) },
    { title: 'Business line', key: 'business_line', render: (_, row) => scopeName(row.business_line) },
    { title: 'Work group', key: 'work_group', render: (_, row) => scopeName(row.work_group) },
    {
      title: 'Workspace',
      key: 'space',
      render: (_, row) => row.space.id ? (
        <Link to={`/platform-admin/knowledge?space_id=${encodeURIComponent(row.space.id)}`}>
          {row.space.name} <Text type="secondary">{row.space.code}</Text>
        </Link>
      ) : <Text type="secondary">Unassigned</Text>,
    },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (value: string) => <Tag>{value}</Tag> },
    { title: 'Version', dataIndex: 'version', key: 'version', width: 80 },
    { title: 'Updated', dataIndex: 'updated_at', key: 'updated_at', render: (value: string) => new Date(value).toLocaleString() },
  ];

  return (
    <div className="kp-platform-knowledge">
      <div className="kp-creation-kicker">METADATA BOUNDARY</div>
      <Title level={1} style={{ fontFamily: "var(--font-family-display, 'Fraunces', serif)", fontWeight: 500 }}>Platform Knowledge</Title>
      <Paragraph style={{ maxWidth: 760 }}>
        跨工作区的安全元数据清单。此页面不授予文档预览、下载、提取文本、chunk、citation 或聊天访问权。
      </Paragraph>

      <Card bordered={false} style={{ margin: '24px 0', border: '1px solid var(--color-border-secondary)', borderRadius: 16 }}>
        <Space wrap>
          <Input.Search
            value={query}
            allowClear
            placeholder="文档、工作区名称或代码"
            onChange={(event) => setQuery(event.target.value)}
            onSearch={(value) => updateFilter('q', value)}
            style={{ width: 280 }}
          />
          <Select
            allowClear
            placeholder="状态"
            value={filters.status}
            onChange={(value) => updateFilter('status', value ?? '')}
            style={{ width: 150 }}
            options={['uploading', 'processing', 'active', 'failed', 'archived'].map((value) => ({ value, label: value }))}
          />
          {filters.space_id && <Button onClick={() => updateFilter('space_id', '')}>清除 Workspace 筛选</Button>}
        </Space>
      </Card>

      {error && <Alert type="error" showIcon message="元数据清单不可用" description={error} action={<Button onClick={() => void load()}>重试</Button>} />}
      <Table<PlatformKnowledgeDocument>
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading && rows.length === 0}
        pagination={false}
        scroll={{ x: 1100 }}
        locale={{ emptyText: error ? '加载失败' : '当前筛选范围内没有文档元数据' }}
      />
      {nextCursor && (
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 20 }}>
          <Button loading={loading} onClick={() => void load(nextCursor, true)}>加载更多</Button>
        </div>
      )}
    </div>
  );
}
