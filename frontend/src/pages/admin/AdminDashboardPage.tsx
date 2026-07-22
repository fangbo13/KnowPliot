/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useState, useRef } from 'react';
import { Alert, Card, Table, Button, Space, Typography, Spin, message, Descriptions } from 'antd';
import {
  ReloadOutlined, TeamOutlined,
  DashboardOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import apiClient, { getRateLimitDetails, isAbortError, withRequestSignal } from '../../api/client';
import {
  adminApi,
  type DocumentQuality,
  type IngestionJob,
  type SystemHealth,
  type SystemMetrics,
} from '../../api/admin';

const { Text } = Typography;

const READINESS_SERVICE_LABELS: Record<string, string> = {
  migrations: 'health_migrations',
  static_files: 'health_static_files',
  media_storage: 'health_media_storage',
  security_config: 'health_security_config',
  export_limits: 'health_export_limits',
  long_run_operations: 'health_long_run_operations',
};

interface UserRecord {
  id: string;
  email: string;
  username: string;
  is_hr_admin: boolean;
  roles: string[];
  is_active: boolean;
  service_line: string | null;
  office_location: string | null;
  role_level: string | null;
}

export default function AdminDashboardPage() {
  const { t } = useTranslation('common');
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [systemMetrics, setSystemMetrics] = useState<SystemMetrics | null>(null);
  const [ingestionJobs, setIngestionJobs] = useState<IngestionJob[]>([]);
  const [documentQuality, setDocumentQuality] = useState<DocumentQuality[]>([]);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);
  const usersSequenceRef = useRef(0);
  const usersControllerRef = useRef<AbortController | null>(null);
  const statusSequenceRef = useRef(0);
  const statusControllerRef = useRef<AbortController | null>(null);

  const loadUsers = async () => {
    const sequence = ++usersSequenceRef.current;
    usersControllerRef.current?.abort();
    const controller = new AbortController();
    usersControllerRef.current = controller;
    setLoading(true);
    try {
      const response = await apiClient.get('/rbac/users/', { signal: controller.signal });
      const data = response.data;
      if (controller.signal.aborted || sequence !== usersSequenceRef.current) return;
      if (!Array.isArray(data) && !Array.isArray(data?.results)) throw new Error('invalid_admin_users_response');
      setUsers(Array.isArray(data) ? data : data.results);
    } catch (err: unknown) {
      if (isAbortError(err) || controller.signal.aborted || sequence !== usersSequenceRef.current) return;
      const rateLimit = getRateLimitDetails(err);
      if (rateLimit) {
        message.error(`${t('rate_limited') || 'Too many requests'}${rateLimit.retryAfterSeconds == null ? '' : ` — ${t('retry_after_seconds', { seconds: rateLimit.retryAfterSeconds })}`}`);
      } else if ((err as { response?: { status?: number } })?.response?.status === 403) {
        message.error(t('permission_denied') || 'Permission denied');
      } else {
        message.error(t('load_error') || 'Failed to load users');
      }
    } finally {
      if (sequence === usersSequenceRef.current && !controller.signal.aborted) setLoading(false);
    }
  };

  // Phase 4B: health and metrics come from dedicated server-side checks.
  const loadSystemStatus = async () => {
    const sequence = ++statusSequenceRef.current;
    statusControllerRef.current?.abort();
    const controller = new AbortController();
    statusControllerRef.current = controller;
    setStatusLoading(true);
    setStatusError(null);
    try {
      const [health, metrics, jobs, quality] = await Promise.all([
        withRequestSignal(controller.signal, () => adminApi.health()),
        withRequestSignal(controller.signal, () => adminApi.metrics()),
        withRequestSignal(controller.signal, () => adminApi.ingestionJobs()),
        withRequestSignal(controller.signal, () => adminApi.documentQuality()),
      ]);
      if (controller.signal.aborted || sequence !== statusSequenceRef.current) return;
      setSystemHealth(health);
      setSystemMetrics(metrics);
      setIngestionJobs(jobs);
      setDocumentQuality(quality);
    } catch (error: unknown) {
      if (isAbortError(error) || controller.signal.aborted || sequence !== statusSequenceRef.current) return;
      const rateLimit = getRateLimitDetails(error);
      setStatusError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    } finally {
      if (sequence === statusSequenceRef.current && !controller.signal.aborted) setStatusLoading(false);
    }
  };

  const retryIngestion = async (jobId: string) => {
    setRetryingJobId(jobId);
    try {
      await adminApi.retryIngestionJob(jobId);
      message.success('Ingestion retry queued');
      await loadSystemStatus();
    } catch {
      message.error('Failed to retry ingestion job');
    } finally {
      setRetryingJobId(null);
    }
  };

  useEffect(() => {
    void loadUsers();
    void loadSystemStatus();
    return () => {
      usersSequenceRef.current += 1;
      statusSequenceRef.current += 1;
      usersControllerRef.current?.abort();
      statusControllerRef.current?.abort();
    };
  }, []);

  const roleStyleMap: Record<string, { bg: string; text: string; border: string }> = {
    admin: { bg: 'rgba(var(--color-error-rgb), 0.10)', text: 'var(--color-error)', border: 'rgba(var(--color-error-rgb), 0.20)' },
    hr: { bg: 'rgba(var(--color-warning-rgb), 0.10)', text: 'var(--color-warning)', border: 'rgba(var(--color-warning-rgb), 0.20)' },
    employee: { bg: 'var(--color-fill)', text: 'var(--color-text-secondary)', border: 'var(--color-border-secondary)' },
  };

  const healthStyleMap: Record<string, { bg: string; text: string; border: string }> = {
    running: { bg: 'rgba(var(--color-success-rgb), 0.10)', text: 'var(--color-success)', border: 'rgba(var(--color-success-rgb), 0.20)' },
    connected: { bg: 'rgba(var(--color-success-rgb), 0.10)', text: 'var(--color-success)', border: 'rgba(var(--color-success-rgb), 0.20)' },
    up: { bg: 'rgba(var(--color-success-rgb), 0.10)', text: 'var(--color-success)', border: 'rgba(var(--color-success-rgb), 0.20)' },
    configured: { bg: 'rgba(var(--color-success-rgb), 0.10)', text: 'var(--color-success)', border: 'rgba(var(--color-success-rgb), 0.20)' },
    not_configured: { bg: 'var(--color-fill)', text: 'var(--color-text-secondary)', border: 'var(--color-border-secondary)' },
    degraded: { bg: 'rgba(var(--color-warning-rgb), 0.10)', text: 'var(--color-warning)', border: 'rgba(var(--color-warning-rgb), 0.20)' },
    unknown: { bg: 'var(--color-fill)', text: 'var(--color-text-secondary)', border: 'var(--color-border-secondary)' },
    down: { bg: 'rgba(var(--color-error-rgb), 0.10)', text: 'var(--color-error)', border: 'rgba(var(--color-error-rgb), 0.20)' },
    disconnected: { bg: 'rgba(var(--color-error-rgb), 0.10)', text: 'var(--color-error)', border: 'rgba(var(--color-error-rgb), 0.20)' },
  };

  const renderHealthTag = (status: string) => {
    const style = healthStyleMap[status] || { bg: 'var(--color-fill)', text: 'var(--color-text-secondary)', border: 'var(--color-border-secondary)' };
    const isGood = ['running', 'connected', 'up', 'configured'].includes(status);
    return (
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '4px 12px',
        borderRadius: '999px',
        fontSize: '11.5px',
        fontWeight: 600,
        background: style.bg,
        color: style.text,
        border: `1px solid ${style.border}`,
        lineHeight: 1,
      }}>
        {isGood && (
          <span style={{
            display: 'inline-block',
            width: 6,
            height: 6,
            borderRadius: '50%',
            backgroundColor: style.text,
            marginRight: 6
          }} />
        )}
        {status.toUpperCase()}
      </span>
    );
  };

  const renderReadinessDetail = (key: string) => {
    const service = systemHealth?.services[key];
    if (!service) return null;
    const details = [
      service.detail,
      service.missing && service.missing.length > 0
        ? `${t('health_missing')}: ${service.missing.join(', ')}`
        : null,
      service.max_sync_rows != null
        ? `${t('health_max_sync_rows')}: ${service.max_sync_rows}`
        : null,
    ].filter(Boolean).join(' · ');
    return (
      <Descriptions.Item
        key={key}
        label={<span style={{ fontWeight: 500, color: 'var(--color-text-secondary)' }}>{t(READINESS_SERVICE_LABELS[key])}</span>}
      >
        <Space direction="vertical" size={2}>
          {renderHealthTag(service.status)}
          {details && <Text type="secondary" style={{ fontSize: 11.5 }}>{details}</Text>}
        </Space>
      </Descriptions.Item>
    );
  };

  const userColumns: ColumnsType<UserRecord> = [
    {
      title: t('kb_title') === 'Title' ? 'Email' : '邮箱',
      dataIndex: 'email',
      key: 'email',
      ellipsis: true,
      width: 200,
    },
    {
      title: t('kb_title') === 'Title' ? 'Username' : '用户名',
      dataIndex: 'username',
      key: 'username',
      width: 120,
    },
    {
      title: 'Role',
      dataIndex: 'roles',
      key: 'roles',
      width: 120,
      render: (roles: string[], record: UserRecord) => {
        const displayRoles = [...roles];
        if (record.is_hr_admin && !roles.includes('hr')) {
          displayRoles.push('hr');
        }
        if (displayRoles.length === 0 && !record.is_hr_admin) {
          const style = roleStyleMap.employee;
          return (
            <span style={{
              display: 'inline-flex',
              padding: '3px 10px',
              borderRadius: '999px',
              fontSize: '11.5px',
              fontWeight: 500,
              background: style.bg,
              color: style.text,
              border: `1px solid ${style.border}`
            }}>
              EMPLOYEE
            </span>
          );
        }
        return (
          <Space size={6}>
            {displayRoles.map(role => {
              const style = roleStyleMap[role] || roleStyleMap.employee;
              return (
                <span key={role} style={{
                  display: 'inline-flex',
                  padding: '3px 10px',
                  borderRadius: '999px',
                  fontSize: '11.5px',
                  fontWeight: 500,
                  background: style.bg,
                  color: style.text,
                  border: `1px solid ${style.border}`
                }}>
                  {role.toUpperCase()}
                </span>
              );
            })}
          </Space>
        );
      },
    },
    {
      title: t('kb_title') === 'Title' ? 'Service Line' : '业务线',
      dataIndex: 'service_line',
      key: 'service_line',
      width: 120,
      render: (val: string | null) => val || '-',
    },
    {
      title: t('kb_status') === 'Status' ? 'Active' : '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      render: (isActive: boolean) => {
        const style = isActive ? { bg: 'rgba(var(--color-success-rgb), 0.10)', text: 'var(--color-success)', border: 'rgba(var(--color-success-rgb), 0.20)' } : { bg: 'rgba(var(--color-error-rgb), 0.10)', text: 'var(--color-error)', border: 'rgba(var(--color-error-rgb), 0.20)' };
        return (
          <span style={{
            display: 'inline-flex',
            padding: '3px 10px',
            borderRadius: '999px',
            fontSize: '11.5px',
            fontWeight: 500,
            background: style.bg,
            color: style.text,
            border: `1px solid ${style.border}`
          }}>
            {isActive ? 'Active' : 'Inactive'}
          </span>
        );
      },


    },
  ];

  return (
    <div className="page" style={{ background: 'transparent' }}>
      <div className="page-head" style={{ marginBottom: 24 }}>
        <h1 className="page-title">{t('admin_dashboard') || 'Admin Dashboard'}</h1>
      </div>
      
      {systemMetrics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
          <Card className="glass-panel" style={{ borderRadius: 'var(--radius-lg)' }} styles={{ body: { padding: '20px' } }}>
            <div style={{ color: 'var(--color-text-secondary)', fontSize: 13, fontWeight: 500, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Users</div>
            <div style={{ fontSize: 28, fontWeight: 600, fontFamily: 'var(--font-family-display)' }}>{systemMetrics.users.total}</div>
          </Card>
          <Card className="glass-panel" style={{ borderRadius: 'var(--radius-lg)' }} styles={{ body: { padding: '20px' } }}>
            <div style={{ color: 'var(--color-text-secondary)', fontSize: 13, fontWeight: 500, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Active Users</div>
            <div style={{ fontSize: 28, fontWeight: 600, fontFamily: 'var(--font-family-display)', color: 'var(--color-success)' }}>{systemMetrics.users.active}</div>
          </Card>
          <Card className="glass-panel" style={{ borderRadius: 'var(--radius-lg)' }} styles={{ body: { padding: '20px' } }}>
            <div style={{ color: 'var(--color-text-secondary)', fontSize: 13, fontWeight: 500, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Documents</div>
            <div style={{ fontSize: 28, fontWeight: 600, fontFamily: 'var(--font-family-display)' }}>{systemMetrics.documents.total}</div>
          </Card>
          <Card className="glass-panel" style={{ borderRadius: 'var(--radius-lg)' }} styles={{ body: { padding: '20px' } }}>
            <div style={{ color: 'var(--color-text-secondary)', fontSize: 13, fontWeight: 500, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Generated Tokens</div>
            <div style={{ fontSize: 28, fontWeight: 600, fontFamily: 'var(--font-family-display)' }}>{systemMetrics.model_api.total_tokens.toLocaleString()}</div>
          </Card>
        </div>
      )}

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        {/* Left: User list table */}
        <Card
          className="glass-panel hover-lift"
          style={{ flex: 2, minWidth: 320, borderRadius: 'var(--radius-lg)' }}
          styles={{ body: { padding: '24px' } }}
          title={
            <Space size="middle">
              <TeamOutlined style={{ color: 'var(--accent)' }} />
              <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 18, color: 'var(--color-text)' }}>
                {t('admin_users') || 'User Management'}
              </span>
            </Space>
          }
          extra={
            <Button icon={<ReloadOutlined />} onClick={loadUsers} style={{ borderRadius: 8 }}>
              {t('refresh') || 'Refresh'}
            </Button>
          }
        >
          {statusError && (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 16 }}
              message={statusError.code === 'rate_limited'
                ? `${t('rate_limited') || 'Too many requests'}${statusError.retryAfterSeconds == null ? '' : ` — ${t('retry_after_seconds', { seconds: statusError.retryAfterSeconds })}`}`
                : t('load_error')}
              action={<Button onClick={() => void loadSystemStatus()}>{t('error_retry')}</Button>}
            />
          )}
          <Table
            columns={userColumns}
            dataSource={users}
            loading={loading}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            scroll={{ x: 'max-content' }}
            size="middle"
          />
        </Card>

        {/* Right: System status panel */}
        <Card
          className="glass-panel hover-lift"
          style={{ flex: 1, minWidth: 280, borderRadius: 'var(--radius-lg)' }}
          styles={{ body: { padding: '24px' } }}
          title={
            <Space size="middle">
              <DashboardOutlined style={{ color: 'var(--accent)' }} />
              <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 18, color: 'var(--color-text)' }}>
                System Health
              </span>
            </Space>
          }
        >
          {statusError && !statusLoading && !systemHealth && (
            <Alert
              type="error"
              showIcon
              message={statusError.code === 'rate_limited'
                ? `${t('rate_limited') || 'Too many requests'}${statusError.retryAfterSeconds == null ? '' : ` — ${t('retry_after_seconds', { seconds: statusError.retryAfterSeconds })}`}`
                : t('load_error')}
              action={<Button onClick={() => void loadSystemStatus()}>{t('error_retry')}</Button>}
            />
          )}
          {statusLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Spin />
            </div>
          ) : systemHealth && systemMetrics ? (
            <Descriptions column={1} size="small" bordered={false} style={{ marginBottom: 12 }}>
              <Descriptions.Item label={<span style={{ fontWeight: 500, color: 'var(--color-text-secondary)' }}>Backend</span>}>
                {renderHealthTag(systemHealth.services.backend.status)}
              </Descriptions.Item>
              <Descriptions.Item label={<span style={{ fontWeight: 500, color: 'var(--color-text-secondary)' }}>Celery</span>}>
                {renderHealthTag(systemHealth.services.celery.status)}
              </Descriptions.Item>
              <Descriptions.Item label={<span style={{ fontWeight: 500, color: 'var(--color-text-secondary)' }}>Database</span>}>
                {renderHealthTag(systemHealth.services.database.status)}
              </Descriptions.Item>
              <Descriptions.Item label={<span style={{ fontWeight: 500, color: 'var(--color-text-secondary)' }}>Redis</span>}>
                {renderHealthTag(systemHealth.services.redis.status)}
              </Descriptions.Item>
              <Descriptions.Item label={<span style={{ fontWeight: 500, color: 'var(--color-text-secondary)' }}>Vector DB</span>}>
                {renderHealthTag(systemHealth.services.vector_db.status)}
              </Descriptions.Item>
              <Descriptions.Item label={<span style={{ fontWeight: 500, color: 'var(--color-text-secondary)' }}>LLM</span>}>
                {renderHealthTag(systemHealth.services.llm.status)}
              </Descriptions.Item>
              {Object.keys(READINESS_SERVICE_LABELS).map(renderReadinessDetail)}
            </Descriptions>
          ) : (
            <div style={{ textAlign: 'center', padding: 20, color: 'var(--color-text-secondary)' }}>
              No status data available
            </div>
          )}

          <div style={{ marginTop: 20, padding: 16, background: 'var(--color-fill)', border: '1px solid var(--color-border-secondary)', borderRadius: 12 }}>
            <Space direction="vertical" size={6}>
              <Text style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text)' }}>
                <SafetyCertificateOutlined style={{ color: 'var(--accent)', marginRight: 6 }} /> V4.0 Dual-Track RBAC Active
              </Text>
              <Text type="secondary" style={{ fontSize: 11.5, lineHeight: 1.4 }}>
                HR: Content domain (22 perms) · Admin: System domain (35 perms)
              </Text>
            </Space>
          </div>
        </Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 24, marginTop: 24 }}>
        <Card
          title="Ingestion queue"
          extra={<Button icon={<ReloadOutlined />} onClick={loadSystemStatus}>Refresh</Button>}
          className="glass-panel hover-lift"
          style={{ borderRadius: 'var(--radius-lg)' }}
        >
          <Table<IngestionJob>
            rowKey="id"
            size="small"
            pagination={{ pageSize: 5 }}
            dataSource={ingestionJobs}
            columns={[
              { title: 'Document', dataIndex: 'document_title', key: 'document_title', ellipsis: true },
              { title: 'Space', dataIndex: 'space_name', key: 'space_name', ellipsis: true },
              {
                title: 'Status',
                dataIndex: 'status',
                key: 'status',
                render: (value: string) => renderHealthTag(value === 'succeeded' ? 'up' : value === 'failed' ? 'down' : 'degraded'),
              },
              {
                title: 'Action',
                key: 'action',
                render: (_value, record) => record.status === 'failed' ? (
                  <Button
                    size="small"
                    loading={retryingJobId === record.id}
                    onClick={() => retryIngestion(record.id)}
                  >
                    Retry
                  </Button>
                ) : null,
              },
            ]}
          />
        </Card>

        <Card
          title="Knowledge quality"
          className="glass-panel hover-lift"
          style={{ borderRadius: 'var(--radius-lg)' }}
        >
          <Table<DocumentQuality>
            rowKey="id"
            size="small"
            pagination={{ pageSize: 5 }}
            dataSource={documentQuality}
            columns={[
              { title: 'Document', dataIndex: 'title', key: 'title', ellipsis: true },
              { title: 'Status', dataIndex: 'status', key: 'status' },
              { title: 'Citations', dataIndex: 'citation_count', key: 'citation_count' },
              {
                title: 'Avg relevance',
                dataIndex: 'average_relevance',
                key: 'average_relevance',
                render: (value: number | null) => value == null ? '-' : value.toFixed(2),
              },
              {
                title: 'Risk',
                key: 'risk',
                render: (_value, record) => (
                  record.flags.stale_source ? 'Stale source'
                    : record.flags.unused ? 'Unused'
                      : record.flags.high_usage ? 'High use'
                        : '-'
                ),
              },
            ]}
          />
        </Card>
      </div>
    </div>
  );
}
