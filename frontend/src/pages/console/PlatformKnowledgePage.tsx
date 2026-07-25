/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Col, Empty, Input, Pagination, Row, Select, Skeleton, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ArrowLeftOutlined, EnvironmentOutlined, FileTextOutlined, ReloadOutlined, TeamOutlined } from '@ant-design/icons';

import { getRateLimitDetails, isAbortError } from '../../api/client';
import { adminApi, type AdminSpaceListItem, type BusinessLine, type Organization } from '../../api/admin';
import { platformKnowledgeApi, type PlatformKnowledgeDocument } from '../../api/platformKnowledge';
import { workspaceCreationApi, type TaxonomyOption } from '../../api/workspaceCreation';

const { Paragraph, Text, Title } = Typography;

const PAGE_SIZE = 12;

const STATUS_COLORS: Record<string, string> = {
  active: 'green',
  archived: 'default',
};

export default function PlatformKnowledgePage() {
  // ── View mode: null = workspace card grid, non-null = document table ──
  const [selectedSpace, setSelectedSpace] = useState<AdminSpaceListItem | null>(null);

  // ── Hierarchical filter state ──
  const [orgFilter, setOrgFilter] = useState<string | undefined>();
  const [officeFilter, setOfficeFilter] = useState<string | undefined>();
  const [blFilter, setBlFilter] = useState<string | undefined>();
  const [wgFilter, setWgFilter] = useState<string | undefined>();
  const [spaceQuery, setSpaceQuery] = useState('');

  // ── Filter option data ──
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [officeLocations, setOfficeLocations] = useState<TaxonomyOption[]>([]);
  const [businessLines, setBusinessLines] = useState<BusinessLine[]>([]);
  const [workGroups, setWorkGroups] = useState<TaxonomyOption[]>([]);

  // ── Space card grid state ──
  const [spaces, setSpaces] = useState<AdminSpaceListItem[]>([]);
  const [spaceCount, setSpaceCount] = useState(0);
  const [spacePage, setSpacePage] = useState(1);
  const [spaceLoading, setSpaceLoading] = useState(false);
  const [spaceError, setSpaceError] = useState<string | null>(null);
  const spaceControllerRef = useRef<AbortController | null>(null);

  const spaceFilterKey = JSON.stringify({ spaceQuery, orgFilter, blFilter, wgFilter, officeFilter, spacePage });

  // ── Document table state ──
  const [docs, setDocs] = useState<PlatformKnowledgeDocument[]>([]);
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [docQuery, setDocQuery] = useState('');
  const [docStatus, setDocStatus] = useState<string | undefined>();
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const docControllerRef = useRef<AbortController | null>(null);

  const docFilterKey = JSON.stringify({ spaceId: selectedSpace?.id, docQuery, docStatus });

  // ── Load organizations on mount ──
  useEffect(() => {
    adminApi.organizations().then(setOrganizations).catch(() => {});
  }, []);

  // Cascade: organization → office-locations + business-lines
  useEffect(() => {
    if (orgFilter) {
      workspaceCreationApi.taxonomy('office-locations', orgFilter).then(setOfficeLocations).catch(() => {});
      adminApi.businessLines(orgFilter).then(setBusinessLines).catch(() => {});
    } else {
      setOfficeLocations([]);
      setBusinessLines([]);
    }
    setOfficeFilter(undefined);
    setBlFilter(undefined);
  }, [orgFilter]);

  // Cascade: business-line → work-groups
  useEffect(() => {
    if (blFilter) {
      workspaceCreationApi.taxonomy('work-groups', blFilter).then(setWorkGroups).catch(() => {});
    } else {
      setWorkGroups([]);
    }
    setWgFilter(undefined);
  }, [blFilter]);

  // ── Load workspace cards ──
  const loadSpaces = useCallback(async () => {
    spaceControllerRef.current?.abort();
    const controller = new AbortController();
    spaceControllerRef.current = controller;
    setSpaceLoading(true);
    setSpaceError(null);
    try {
      const res = await adminApi.listSpaces({
        ...(spaceQuery ? { q: spaceQuery } : {}),
        ...(orgFilter ? { organization: orgFilter } : {}),
        ...(blFilter ? { business_line: blFilter } : {}),
        ...(wgFilter ? { work_group: wgFilter } : {}),
        ...(officeFilter ? { office_location: officeFilter } : {}),
        page: spacePage,
        page_size: PAGE_SIZE,
      }, controller.signal);
      setSpaces(res.results);
      setSpaceCount(res.count);
    } catch (err: unknown) {
      if (isAbortError(err) || controller.signal.aborted) return;
      const rl = getRateLimitDetails(err);
      setSpaceError(rl
        ? `请求过于频繁${rl.retryAfterSeconds == null ? '' : `，请在 ${rl.retryAfterSeconds} 秒后重试`}`
        : '无法加载工作空间列表。');
    } finally {
      if (!controller.signal.aborted) setSpaceLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spaceFilterKey]);

  useEffect(() => {
    if (selectedSpace) return;
    void loadSpaces();
    return () => { spaceControllerRef.current?.abort(); };
  }, [loadSpaces, selectedSpace]);

  // ── Load documents for selected workspace ──
  const loadDocs = useCallback(async (cursor?: string, append = false) => {
    if (!selectedSpace) return;
    docControllerRef.current?.abort();
    const controller = new AbortController();
    docControllerRef.current = controller;
    setDocLoading(true);
    setDocError(null);
    try {
      const page = await platformKnowledgeApi.list({
        space_id: selectedSpace.id,
        ...(docQuery ? { q: docQuery } : {}),
        ...(docStatus ? { status: docStatus } : {}),
        cursor,
      }, controller.signal);
      setDocs((prev) => append ? [...prev, ...page.results] : page.results);
      setNextCursor(page.next_cursor);
    } catch (err: unknown) {
      if (isAbortError(err) || controller.signal.aborted) return;
      const rl = getRateLimitDetails(err);
      setDocError(rl
        ? `请求过于频繁${rl.retryAfterSeconds == null ? '' : `，请在 ${rl.retryAfterSeconds} 秒后重试`}`
        : '无法加载文档列表。');
    } finally {
      if (!controller.signal.aborted) setDocLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docFilterKey]);

  useEffect(() => {
    if (!selectedSpace) return;
    setDocs([]);
    setNextCursor(null);
    void loadDocs();
    return () => { docControllerRef.current?.abort(); };
  }, [loadDocs]);

  // ── Filter handlers (reset page on change) ──
  const resetPage = () => setSpacePage(1);

  const handleCardClick = (space: AdminSpaceListItem) => {
    setSelectedSpace(space);
    setDocQuery('');
    setDocStatus(undefined);
    setDocs([]);
    setNextCursor(null);
  };

  const handleBack = () => {
    setSelectedSpace(null);
    setDocQuery('');
    setDocStatus(undefined);
    setDocs([]);
    setNextCursor(null);
  };

  // ── Document table columns ──
  const docColumns: ColumnsType<PlatformKnowledgeDocument> = [
    { title: '文档', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={STATUS_COLORS[v] ?? 'blue'}>{v}</Tag> },
    { title: '版本', dataIndex: 'version', key: 'version', width: 80 },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', render: (v: string) => new Date(v).toLocaleString() },
  ];

  // ════════════════════════════════════════════════════════════════════
  // Render: Document view (selected workspace)
  // ════════════════════════════════════════════════════════════════════
  if (selectedSpace) {
    return (
      <div className="kp-platform-knowledge">
        <Button icon={<ArrowLeftOutlined />} onClick={handleBack} style={{ marginBottom: 16 }}>
          返回工作空间列表
        </Button>
        <Title level={2} style={{ fontFamily: "var(--font-family-display, 'Fraunces', serif)", fontWeight: 500 }}>
          {selectedSpace.name}
          <Text type="secondary" style={{ fontSize: 14, marginLeft: 12 }}>{selectedSpace.code}</Text>
        </Title>
        <Space size="small" wrap style={{ marginBottom: 16 }}>
          {selectedSpace.organization_name && <Tag>{selectedSpace.organization_name}</Tag>}
          {selectedSpace.business_line_name && <Tag color="blue">{selectedSpace.business_line_name}</Tag>}
          {selectedSpace.work_group_name && <Tag color="cyan">{selectedSpace.work_group_name}</Tag>}
          {selectedSpace.office_locations?.map((loc) => (
            <Tag key={loc.id} icon={<EnvironmentOutlined />} color="geekblue">{loc.display_name}</Tag>
          ))}
        </Space>

        <Card bordered={false} style={{ margin: '16px 0', border: '1px solid var(--color-border-secondary)', borderRadius: 12 }}>
          <Space wrap>
            <Input.Search
              value={docQuery}
              allowClear
              placeholder="搜索文档"
              onChange={(e) => setDocQuery(e.target.value)}
              onSearch={(v) => setDocQuery(v)}
              style={{ width: 280 }}
            />
            <Select
              allowClear
              placeholder="状态"
              value={docStatus}
              onChange={(v) => setDocStatus(v)}
              style={{ width: 150 }}
              options={['uploading', 'processing', 'active', 'failed', 'archived'].map((v) => ({ value: v, label: v }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => void loadDocs()} loading={docLoading}>刷新</Button>
          </Space>
        </Card>

        {docError && (
          <Alert type="error" showIcon message="文档列表不可用" description={docError} style={{ margin: '16px 0' }} />
        )}
        <Table<PlatformKnowledgeDocument>
          rowKey="id"
          columns={docColumns}
          dataSource={docs}
          loading={docLoading && docs.length === 0}
          pagination={false}
          locale={{ emptyText: docError ? '加载失败' : '此工作空间暂无文档' }}
        />
        {nextCursor && (
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 20 }}>
            <Button loading={docLoading} onClick={() => void loadDocs(nextCursor, true)}>加载更多</Button>
          </div>
        )}
      </div>
    );
  }

  // ════════════════════════════════════════════════════════════════════
  // Render: Workspace card grid (default)
  // ════════════════════════════════════════════════════════════════════
  return (
    <div className="kp-platform-knowledge">
      <Title level={1} style={{ fontFamily: "var(--font-family-display, 'Fraunces', serif)", fontWeight: 500 }}>
        知识库管理
      </Title>
      <Paragraph style={{ maxWidth: 760 }}>
        查看所有工作空间的知识库。按办公地点、业务线、工作组进行层级筛选，点击卡片查看空间内文档。
      </Paragraph>

      <Card bordered={false} style={{ margin: '24px 0', border: '1px solid var(--color-border-secondary)', borderRadius: 16 }}>
        <Space wrap size="middle">
          <Select
            showSearch
            allowClear
            placeholder="组织"
            value={orgFilter}
            onChange={(v) => { setOrgFilter(v); resetPage(); }}
            style={{ width: 200 }}
            optionFilterProp="label"
            options={organizations.map((o) => ({ value: o.id, label: o.name }))}
          />
          <Select
            showSearch
            allowClear
            placeholder="办公地点"
            value={officeFilter}
            onChange={(v) => { setOfficeFilter(v); resetPage(); }}
            style={{ width: 200 }}
            optionFilterProp="label"
            options={officeLocations.map((l) => ({ value: l.id, label: l.display_name }))}
            disabled={!orgFilter}
          />
          <Select
            showSearch
            allowClear
            placeholder="业务线"
            value={blFilter}
            onChange={(v) => { setBlFilter(v); resetPage(); }}
            style={{ width: 200 }}
            optionFilterProp="label"
            options={businessLines.map((b) => ({ value: b.id, label: b.name }))}
            disabled={!orgFilter}
          />
          <Select
            showSearch
            allowClear
            placeholder="工作组"
            value={wgFilter}
            onChange={(v) => { setWgFilter(v); resetPage(); }}
            style={{ width: 200 }}
            optionFilterProp="label"
            options={workGroups.map((w) => ({ value: w.id, label: w.display_name }))}
            disabled={!blFilter}
          />
          <Input.Search
            value={spaceQuery}
            allowClear
            placeholder="工作空间名称或代码"
            onChange={(e) => setSpaceQuery(e.target.value)}
            onSearch={(v) => { setSpaceQuery(v); resetPage(); }}
            style={{ width: 240 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void loadSpaces()} loading={spaceLoading}>刷新</Button>
        </Space>
      </Card>

      {spaceError && (
        <Alert type="error" showIcon message="工作空间列表不可用" description={spaceError} style={{ margin: '16px 0' }} />
      )}

      {spaceLoading && spaces.length === 0 ? (
        <Row gutter={[16, 16]}>
          {Array.from({ length: 6 }).map((_, i) => (
            <Col key={i} xs={24} sm={12} md={8} lg={6}>
              <Card style={{ borderRadius: 12 }}>
                <Skeleton active paragraph={{ rows: 4 }} />
              </Card>
            </Col>
          ))}
        </Row>
      ) : spaces.length === 0 ? (
        <Empty description={spaceError ? '加载失败' : '当前筛选范围内没有工作空间'} />
      ) : (
        <>
          <Row gutter={[16, 16]}>
            {spaces.map((space) => (
              <Col key={space.id} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  onClick={() => handleCardClick(space)}
                  style={{ borderRadius: 12, height: '100%', cursor: 'pointer' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <Text strong style={{ fontSize: 16 }}>{space.name}</Text>
                    <Tag color={space.status === 'active' ? 'green' : 'default'}>{space.status}</Tag>
                  </div>
                  <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 12 }}>{space.code}</Text>
                  {space.description && (
                    <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ fontSize: 13, marginBottom: 12 }}>
                      {space.description}
                    </Paragraph>
                  )}
                  <Space size={[4, 8]} wrap style={{ marginBottom: 12 }}>
                    {space.organization_name && <Tag>{space.organization_name}</Tag>}
                    {space.business_line_name && <Tag color="blue">{space.business_line_name}</Tag>}
                    {space.work_group_name && <Tag color="cyan">{space.work_group_name}</Tag>}
                    {space.office_locations?.map((loc) => (
                      <Tag key={loc.id} color="geekblue">{loc.display_name}</Tag>
                    ))}
                  </Space>
                  <Space size="large">
                    <Space size={4}>
                      <TeamOutlined style={{ color: 'var(--color-text-secondary)' }} />
                      <Text type="secondary">{space.member_count} 成员</Text>
                    </Space>
                    <Space size={4}>
                      <FileTextOutlined style={{ color: 'var(--color-text-secondary)' }} />
                      <Text type="secondary">{space.document_count} 文档</Text>
                    </Space>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24 }}>
            <Pagination
              current={spacePage}
              total={spaceCount}
              pageSize={PAGE_SIZE}
              onChange={(page) => setSpacePage(page)}
              showTotal={(total) => `共 ${total} 个工作空间`}
            />
          </div>
        </>
      )}
    </div>
  );
}
