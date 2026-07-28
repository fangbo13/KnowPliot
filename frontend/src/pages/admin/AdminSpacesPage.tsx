/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
  Descriptions,
  Spin,
} from 'antd';
import {
  ReloadOutlined,
  SearchOutlined,
  DeleteOutlined,
  InboxOutlined,
  RollbackOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import { adminApi, type AdminSpaceListItem } from '../../api/admin';
import { spacesApi, type WorkspaceDeletionImpact } from '../../api/spaces';
import { getRateLimitDetails, isAbortError } from '../../api/client';

const { Text } = Typography;

type StatusFilter = 'all' | 'active' | 'archived';

export default function AdminSpacesPage() {
  const { t } = useTranslation('common');
  const [spaces, setSpaces] = useState<AdminSpaceListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

  // --- Deletion modal state ---
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AdminSpaceListItem | null>(null);
  const [deletionImpact, setDeletionImpact] = useState<WorkspaceDeletionImpact | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [confirmInput, setConfirmInput] = useState('');
  const [deleting, setDeleting] = useState(false);

  // --- Archive/restore action loading ---
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  const loadSpaces = useCallback(async () => {
    const seq = ++seqRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        page,
        page_size: pageSize,
      };
      if (statusFilter !== 'all') params.status = statusFilter;
      if (searchQuery.trim()) params.q = searchQuery.trim();
      const data = await adminApi.listSpaces(
        params as { status?: 'active' | 'archived'; q?: string; page?: number; page_size?: number },
        controller.signal,
      );
      if (controller.signal.aborted || seq !== seqRef.current) return;
      setSpaces(data.results || []);
      setTotal(data.count || 0);
    } catch (err: unknown) {
      if (isAbortError(err) || controller.signal.aborted || seq !== seqRef.current) return;
      const rateLimit = getRateLimitDetails(err);
      message.error(
        rateLimit
          ? `${t('rate_limited') || 'Too many requests'}${rateLimit.retryAfterSeconds == null ? '' : ` — ${t('retry_after_seconds', { seconds: rateLimit.retryAfterSeconds })}`}`
          : (err as { response?: { status?: number } })?.response?.status === 403
            ? t('permission_denied') || 'Permission denied'
            : t('load_error') || 'Failed to load workspaces',
      );
    } finally {
      if (seq === seqRef.current && !controller.signal.aborted) setLoading(false);
    }
  }, [page, statusFilter, searchQuery, t]);

  useEffect(() => {
    void loadSpaces();
    return () => {
      seqRef.current += 1;
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, statusFilter]);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (page !== 1) setPage(1);
      else void loadSpaces();
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  const handleArchive = async (record: AdminSpaceListItem) => {
    setActionLoadingId(record.id);
    try {
      await adminApi.archiveSpace(record.id);
      message.success(t('kb_status') === 'Status' ? 'Workspace archived' : '工作空间已归档');
      await loadSpaces();
    } catch (err: unknown) {
      const rateLimit = getRateLimitDetails(err);
      message.error(
        rateLimit
          ? `${t('rate_limited') || 'Too many requests'}`
          : 'Failed to archive workspace',
      );
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleRestore = async (record: AdminSpaceListItem) => {
    setActionLoadingId(record.id);
    try {
      await adminApi.restoreSpace(record.id);
      message.success(t('kb_status') === 'Status' ? 'Workspace restored' : '工作空间已恢复');
      await loadSpaces();
    } catch (err: unknown) {
      const rateLimit = getRateLimitDetails(err);
      message.error(
        rateLimit
          ? `${t('rate_limited') || 'Too many requests'}`
          : 'Failed to restore workspace',
      );
    } finally {
      setActionLoadingId(null);
    }
  };

  // --- GitHub-style deletion flow ---
  const openDeleteModal = async (record: AdminSpaceListItem) => {
    setDeleteTarget(record);
    setDeleteModalOpen(true);
    setConfirmInput('');
    setDeletionImpact(null);
    setImpactLoading(true);
    try {
      const impact = await spacesApi.deletionImpact(record.id);
      setDeletionImpact(impact);
    } catch (err: unknown) {
      const rateLimit = getRateLimitDetails(err);
      message.error(
        rateLimit
          ? `${t('rate_limited') || 'Too many requests'}`
          : 'Failed to load deletion impact. The workspace may not support permanent deletion.',
      );
      setDeleteModalOpen(false);
    } finally {
      setImpactLoading(false);
    }
  };

  const closeDeleteModal = () => {
    setDeleteModalOpen(false);
    setDeleteTarget(null);
    setDeletionImpact(null);
    setConfirmInput('');
    setDeleting(false);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget || !deletionImpact) return;
    if (confirmInput.trim() !== deletionImpact.confirmation_phrase) {
      message.error(t('deletion_phrase_mismatch'));
      return;
    }
    setDeleting(true);
    try {
      // Step 1: submit deletion request
      const request = await spacesApi.submitDeletion(deleteTarget.id, deletionImpact);
      // Step 2: confirm with typed phrase
      await spacesApi.confirmDeletion(
        deleteTarget.id,
        request,
        deletionImpact,
        confirmInput.trim(),
      );
      message.success(
        t('kb_status') === 'Status'
          ? 'Workspace permanently deleted'
          : '工作空间已永久删除',
      );
      closeDeleteModal();
      await loadSpaces();
    } catch (err: unknown) {
      const rateLimit = getRateLimitDetails(err);
      const errMsg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(
        rateLimit
          ? `${t('rate_limited') || 'Too many requests'}`
          : errMsg || 'Failed to delete workspace',
      );
    } finally {
      setDeleting(false);
    }
  };

  const isEn = t('kb_title') === 'Title';

  const columns: ColumnsType<AdminSpaceListItem> = [
    {
      title: isEn ? 'Name' : '名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      width: 180,
      render: (name: string, record: AdminSpaceListItem) => (
        <Space direction="vertical" size={0}>
          <Text strong style={{ fontSize: 13 }}>{name}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{record.code}</Text>
        </Space>
      ),
    },
    {
      title: isEn ? 'Owner' : '所有者',
      dataIndex: 'owner_name',
      key: 'owner_name',
      width: 160,
      ellipsis: true,
      render: (val: string | null, record: AdminSpaceListItem) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>{val || '-'}</Text>
          {record.owner_email && (
            <Text type="secondary" style={{ fontSize: 11 }}>{record.owner_email}</Text>
          )}
        </Space>
      ),
    },
    {
      title: isEn ? 'Organization' : '组织',
      key: 'organization',
      width: 140,
      ellipsis: true,
      render: (_: unknown, record: AdminSpaceListItem) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>{record.organization_name || '-'}</Text>
          {record.business_line_name && (
            <Text type="secondary" style={{ fontSize: 11 }}>{record.business_line_name}</Text>
          )}
        </Space>
      ),
    },
    {
      title: isEn ? 'Status' : '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const isActive = status === 'active';
        return (
          <Tag color={isActive ? 'success' : 'default'} style={{ borderRadius: '999px', fontSize: 11.5, fontWeight: 500 }}>
            {isActive ? 'ACTIVE' : 'ARCHIVED'}
          </Tag>
        );
      },
    },
    {
      title: isEn ? 'Members' : '成员',
      dataIndex: 'member_count',
      key: 'member_count',
      width: 80,
      render: (val: number) => <Text style={{ fontSize: 12 }}>{val}</Text>,
    },
    {
      title: isEn ? 'Docs' : '文档',
      dataIndex: 'document_count',
      key: 'document_count',
      width: 80,
      render: (val: number) => <Text style={{ fontSize: 12 }}>{val}</Text>,
    },
    {
      title: isEn ? 'Created' : '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
      render: (val: string) => (
        <Text type="secondary" style={{ fontSize: 11.5 }}>
          {val ? new Date(val).toLocaleDateString() : '-'}
        </Text>
      ),
    },
    {
      title: isEn ? 'Actions' : '操作',
      key: 'actions',
      width: 200,
      fixed: 'right' as const,
      render: (_: unknown, record: AdminSpaceListItem) => {
        const isActive = record.status === 'active';
        return (
          <Space size={8}>
            {isActive ? (
              <Button
                size="small"
                icon={<InboxOutlined />}
                loading={actionLoadingId === record.id}
                onClick={() => handleArchive(record)}
                style={{ borderRadius: 6 }}
              >
                {isEn ? 'Archive' : '归档'}
              </Button>
            ) : (
              <Button
                size="small"
                icon={<RollbackOutlined />}
                loading={actionLoadingId === record.id}
                onClick={() => handleRestore(record)}
                style={{ borderRadius: 6 }}
              >
                {isEn ? 'Restore' : '恢复'}
              </Button>
            )}
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => void openDeleteModal(record)}
              style={{ borderRadius: 6 }}
            >
              {isEn ? 'Delete' : '删除'}
            </Button>
          </Space>
        );
      },
    },
  ];

  // GitHub-style delete confirmation modal content
  const renderDeleteModalContent = () => {
    if (!deleteTarget) return null;
    if (impactLoading) {
      return (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip="Loading deletion impact..." />
        </div>
      );
    }
    if (!deletionImpact) {
      return (
        <Alert
          type="error"
          showIcon
          message={t('deletion_impact_load_failed')}
        />
      );
    }

    const hasBlockers = deletionImpact.blockers && deletionImpact.blockers.length > 0;

    return (
      <div>
        <Alert
          type="warning"
          showIcon
          icon={<ExclamationCircleOutlined />}
          style={{ marginBottom: 16 }}
          message={isEn
            ? 'This action CANNOT be undone. This will permanently delete the workspace and all associated data.'
            : '此操作不可撤销。这将永久删除工作空间及所有关联数据。'}
        />

        <Descriptions
          column={1}
          size="small"
          bordered
          style={{ marginBottom: 16 }}
        >
          <Descriptions.Item label={isEn ? 'Workspace' : '工作空间'}>
            <Text strong>{deleteTarget.name}</Text>
            <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>({deleteTarget.code})</Text>
          </Descriptions.Item>
          <Descriptions.Item label={isEn ? 'Content to delete' : '将删除的内容'}>
            <Space size={16}>
              <Tag>{isEn ? 'Content items' : '内容项'}: {deletionImpact.counts.eligible_content}</Tag>
              <Tag>{isEn ? 'Retained evidence' : '保留证据'}: {deletionImpact.counts.retained_evidence}</Tag>
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label={isEn ? 'Documents' : '文档'}>
            <Text>{deleteTarget.document_count}</Text>
          </Descriptions.Item>
          <Descriptions.Item label={isEn ? 'Members' : '成员'}>
            <Text>{deleteTarget.member_count}</Text>
          </Descriptions.Item>
          {hasBlockers && (
            <Descriptions.Item label={isEn ? 'Blockers' : '阻止项'}>
              {deletionImpact.blockers.map((b, i) => (
                <Tag key={i} color="error" style={{ marginBottom: 4 }}>
                  {b.kind}: {b.status}
                </Tag>
              ))}
            </Descriptions.Item>
          )}
        </Descriptions>

        {hasBlockers && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
            message={isEn
              ? 'This workspace has blockers that must be resolved before deletion can proceed.'
              : '此工作空间存在阻止项，必须先解决才能进行删除。'}
          />
        )}

        <div style={{ marginBottom: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: 500 }}>
            {isEn
              ? 'To confirm deletion, please type the following confirmation phrase:'
              : '为确认删除，请输入以下确认短语：'}
          </Text>
        </div>
        <div style={{
          padding: '10px 14px',
          background: 'var(--color-fill)',
          border: '1px solid var(--color-border-secondary)',
          borderRadius: 8,
          marginBottom: 12,
        }}>
          <Text code style={{ fontSize: 14, fontWeight: 600 }}>
            {deletionImpact.confirmation_phrase}
          </Text>
        </div>
        <Input
          placeholder={isEn ? 'Type the confirmation phrase to confirm' : '输入确认短语以确认'}
          value={confirmInput}
          onChange={(e) => setConfirmInput(e.target.value)}
          status={confirmInput && confirmInput !== deletionImpact.confirmation_phrase ? 'error' : undefined}
          style={{ borderRadius: 6 }}
        />
        {confirmInput && confirmInput !== deletionImpact.confirmation_phrase && (
          <Text type="danger" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
            {isEn ? 'Confirmation phrase does not match' : '确认短语不匹配'}
          </Text>
        )}
      </div>
    );
  };

  const canConfirmDelete =
    deletionImpact &&
    confirmInput.trim() === deletionImpact.confirmation_phrase &&
    !deletionImpact.blockers?.length;

  return (
    <div className="page">
      <div className="page-head" style={{ marginBottom: 24 }}>
        <h1 className="page-title">
          {isEn ? 'Workspace Management' : '工作空间管理'}
        </h1>
      </div>

      <Card
        className="glass-panel hover-lift"
        style={{ borderRadius: 'var(--radius-lg)' }}
        styles={{ body: { padding: '24px' } }}
        extra={
          <Button icon={<ReloadOutlined />} onClick={loadSpaces} style={{ borderRadius: 8 }}>
            {t('refresh') || 'Refresh'}
          </Button>
        }
      >
        <Space style={{ marginBottom: 16, width: '100%' }} direction="vertical" size={12}>
          <Space size={12} wrap>
            <Select<StatusFilter>
              value={statusFilter}
              onChange={(val) => {
                setStatusFilter(val);
                setPage(1);
              }}
              style={{ width: 140 }}
              options={[
                { value: 'all', label: isEn ? 'All' : '全部' },
                { value: 'active', label: isEn ? 'Active' : '活跃' },
                { value: 'archived', label: isEn ? 'Archived' : '已归档' },
              ]}
            />
            <Input
              placeholder={isEn ? 'Search by name or code...' : '按名称或代码搜索...'}
              prefix={<SearchOutlined />}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              allowClear
              style={{ width: 260, borderRadius: 6 }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isEn ? `${total} workspace(s)` : `共 ${total} 个工作空间`}
            </Text>
          </Space>
        </Space>

        <Table<AdminSpaceListItem>
          columns={columns}
          dataSource={spaces}
          loading={loading}
          rowKey="id"
          size="middle"
          scroll={{ x: 'max-content' }}
          pagination={{
            current: page,
            pageSize,
            total,
            onChange: (p) => setPage(p),
            showSizeChanger: false,
            showTotal: (cnt) => isEn ? `${cnt} workspace(s)` : `共 ${cnt} 个工作空间`,
          }}
        />
      </Card>

      {/* GitHub-style permanent deletion modal */}
      <Modal
        open={deleteModalOpen}
        onCancel={closeDeleteModal}
        width={560}
        footer={[
          <Button key="cancel" onClick={closeDeleteModal} style={{ borderRadius: 8 }}>
            {isEn ? 'Cancel' : '取消'}
          </Button>,
          <Button
            key="confirm"
            type="primary"
            danger
            disabled={!canConfirmDelete}
            loading={deleting}
            onClick={() => void handleConfirmDelete()}
            style={{ borderRadius: 8 }}
          >
            {isEn ? 'I understand the consequences — delete this workspace' : '我了解后果 — 删除此工作空间'}
          </Button>,
        ]}
      >
        {renderDeleteModalContent()}
      </Modal>
    </div>
  );
}
