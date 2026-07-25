/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Empty,
  Input,
  Modal,
  Segmented,
  Skeleton,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';

import { getApiErrorCode, getRateLimitDetails, isAbortError } from '../../api/client';
import {
  workspaceCreationApi,
  type WorkspaceCreationImpact,
  type WorkspaceCreationRequest,
  type WorkspaceCreationStatus,
} from '../../api/workspaceCreation';
import { useAuth } from '../../auth/AuthProvider';
import '../WorkspaceCreationPage.css';

const { Title, Paragraph, Text } = Typography;

function requestStatus(status: WorkspaceCreationStatus) {
  const values: Record<string, { color: string; label: string }> = {
    pending: { color: 'gold', label: '待审批' },
    completed: { color: 'green', label: '已批准' },
    rejected: { color: 'red', label: '已拒绝' },
    cancelled: { color: 'default', label: '已取消' },
    expired: { color: 'default', label: '已过期' },
    invalidated: { color: 'default', label: '已失效' },
    failed: { color: 'red', label: '处理失败' },
  };
  return values[status] ?? { color: 'default', label: status };
}

function reviewError(error: unknown): string {
  const rateLimit = getRateLimitDetails(error);
  if (rateLimit) return rateLimit.retryAfterSeconds == null
    ? '请求过于频繁，请稍后再试。'
    : `请求过于频繁，请在 ${rateLimit.retryAfterSeconds} 秒后重试。`;
  const code = getApiErrorCode(error);
  if (code === 'self_approval_forbidden') return '申请人与审批人必须分离，不能审批自己的申请。';
  if (code === 'impact_changed') return '影响快照已过期或发生变化，请刷新后重新审核。';
  if (code === 'stale_request_version' || code === 'stale_impact_version') return '申请或影响快照已经变化，请刷新后重新审核。';
  if (code === 'request_already_resolved' || code === 'request_not_pending') return '该申请已不再处于待审批状态。';
  if (code === 'reviewer_separation_unavailable') return '当前没有其他可用的审批人，无法满足职责分离要求。';
  if (code === 'space_locator_conflict') return '工作区标识冲突，该申请可能需要重新提交。';
  return '操作失败，请刷新队列后重试。';
}

export default function WorkspaceCreationReviewPage() {
  const { user } = useAuth();
  const [queue, setQueue] = useState<WorkspaceCreationRequest[]>([]);
  const [selected, setSelected] = useState<WorkspaceCreationRequest | null>(null);
  const [impact, setImpact] = useState<WorkspaceCreationImpact | null>(null);
  const [loading, setLoading] = useState(true);
  const [impactLoading, setImpactLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [bypassSeparation, setBypassSeparation] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reasonCode, setReasonCode] = useState('scope_not_approved');
  const [reasonText, setReasonText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<'pending' | 'processed' | 'all'>('pending');
  const queueController = useRef<AbortController | null>(null);
  const impactController = useRef<AbortController | null>(null);
  const sequence = useRef(0);

  const filteredQueue = useMemo(() => {
    if (filterStatus === 'all') return queue;
    if (filterStatus === 'pending') return queue.filter((r) => r.status === 'pending');
    return queue.filter((r) => r.status !== 'pending');
  }, [queue, filterStatus]);

  const loadQueue = useCallback(async () => {
    const current = ++sequence.current;
    queueController.current?.abort();
    const controller = new AbortController();
    queueController.current = controller;
    setLoading(true);
    setError(null);
    try {
      const rows = await workspaceCreationApi.reviewQueue(controller.signal);
      if (controller.signal.aborted || current !== sequence.current) return;
      setQueue(rows);
      setSelected((prior) => {
        const match = rows.find((row) => row.request_id === prior?.request_id);
        if (match) return match;
        const pendingRows = rows.filter((r) => r.status === 'pending');
        return pendingRows[0] ?? rows[0] ?? null;
      });
    } catch (loadError: unknown) {
      if (!isAbortError(loadError) && current === sequence.current) setError(reviewError(loadError));
    } finally {
      if (!controller.signal.aborted && current === sequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadQueue();
    return () => {
      sequence.current += 1;
      queueController.current?.abort();
      impactController.current?.abort();
    };
  }, [loadQueue]);

  useEffect(() => {
    impactController.current?.abort();
    setImpact(null);
    setAcknowledged(false);
    setBypassSeparation(false);
    if (!selected || selected.status !== 'pending') return;
    const controller = new AbortController();
    impactController.current = controller;
    setImpactLoading(true);
    workspaceCreationApi.impact(selected.request_id, controller.signal).then(
      (nextImpact) => { if (!controller.signal.aborted) setImpact(nextImpact); },
      (impactError: unknown) => { if (!isAbortError(impactError)) message.error(reviewError(impactError)); },
    ).finally(() => { if (!controller.signal.aborted) setImpactLoading(false); });
    return () => controller.abort();
  }, [selected?.request_id, selected?.status]);

  const approve = async () => {
    const isSelfReview = selected?.requester_uuid === user?.id;
    if (!selected || !acknowledged || acting) return;
    if (isSelfReview && !(user?.is_superuser && bypassSeparation)) return;
    setActing(true);
    try {
      // Approval always uses an impact fetched immediately before the mutation;
      // a previously rendered snapshot is informative only.
      const freshImpact = await workspaceCreationApi.impact(selected.request_id);
      await workspaceCreationApi.approve(selected, freshImpact, isSelfReview && bypassSeparation);
      message.success('申请已批准，工作区正在配置。');
      setSelected(null);
      await loadQueue();
    } catch (approveError: unknown) {
      message.error(reviewError(approveError));
    } finally {
      setActing(false);
    }
  };

  const reject = async () => {
    if (!selected || !reasonCode.trim() || acting) return;
    setActing(true);
    try {
      await workspaceCreationApi.reject(selected, reasonCode.trim(), reasonText.trim());
      message.success('申请已拒绝。');
      setRejectOpen(false);
      setReasonText('');
      setSelected(null);
      await loadQueue();
    } catch (rejectError: unknown) {
      message.error(reviewError(rejectError));
    } finally {
      setActing(false);
    }
  };

  if (loading) return <Skeleton active paragraph={{ rows: 9 }} />;

  const selfReview = selected?.requester_uuid === user?.id;
  const canBypassSeparation = selfReview && !!user?.is_superuser;
  const resources = Array.isArray(impact?.impact.resources) ? impact.impact.resources : [];
  const resourceKinds = resources.reduce<Record<string, number>>((acc, r) => {
    const kind = String(r.kind ?? 'resource');
    acc[kind] = (acc[kind] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="kp-review-page">
      <div className="kp-review-heading">
        <div>
          <div className="kp-creation-kicker">SEPARATION OF DUTIES</div>
          <Title level={1}>工作区创建审批</Title>
          <Paragraph>管理所有工作区创建申请；批准前会重新获取影响快照并执行服务端并发校验。</Paragraph>
        </div>
        <Button onClick={() => void loadQueue()}>刷新队列</Button>
      </div>

      {error && <Alert type="error" showIcon message="审批队列不可用" description={error} />}

      <div className="kp-creation-filter">
        <Segmented
          value={filterStatus}
          onChange={(value) => setFilterStatus(value as typeof filterStatus)}
          options={[
            { label: '待审批', value: 'pending' },
            { label: '已处理', value: 'processed' },
            { label: '全部', value: 'all' },
          ]}
        />
      </div>

      {filteredQueue.length === 0 ? <Empty description={filterStatus === 'pending' ? '当前没有待审批申请' : filterStatus === 'processed' ? '当前没有已处理申请' : '暂无申请记录'} /> : (
        <div className="kp-review-grid">
          <aside className="kp-review-queue" aria-label="审批申请队列">
            {filteredQueue.map((request) => {
              const status = requestStatus(request.status);
              return (
                <button
                  type="button"
                  key={request.request_id}
                  className={`kp-review-queue-item${selected?.request_id === request.request_id ? ' is-active' : ''}`}
                  onClick={() => setSelected(request)}
                >
                  <span>{request.submitted?.name ?? '未命名申请'}</span>
                  <small>{status.label} · {request.submitted?.code ?? request.request_id.slice(0, 8)}</small>
                </button>
              );
            })}
          </aside>

          <Card className="kp-review-detail" bordered={false}>
            {selected && (
              <>
                <Space wrap>
                  <Title level={3}>{selected.submitted?.name}</Title>
                  <Tag color={requestStatus(selected.status).color}>{requestStatus(selected.status).label} · v{selected.request_version}</Tag>
                </Space>
                <Paragraph>{selected.submitted?.purpose}</Paragraph>
                {selfReview && !canBypassSeparation && (
                  <Alert type="warning" showIcon message="职责分离" description="这是你提交的申请，必须由另一位具备平台审批能力的人员处理。" />
                )}
                {canBypassSeparation && (
                  <Alert
                    type="warning"
                    showIcon
                    message="职责分离 — 超管绕过"
                    description={
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Text>这是你提交的申请。作为超级管理员，你可以选择忽视职责分离政策直接审批。</Text>
                        <Checkbox
                          checked={bypassSeparation}
                          onChange={(event) => setBypassSeparation(event.target.checked)}
                        >
                          忽视职责分离政策，由我自行审批
                        </Checkbox>
                        {bypassSeparation && (
                          <Text type="danger" strong>
                            此操作将在审计日志中标记为“绕过职责分离”。
                          </Text>
                        )}
                      </Space>
                    }
                  />
                )}
                <Descriptions column={1} size="small" className="kp-review-descriptions">
                  <Descriptions.Item label="申请人 UUID">{selected.requester_uuid}</Descriptions.Item>
                  <Descriptions.Item label="短代码">{selected.submitted?.code}</Descriptions.Item>
                  <Descriptions.Item label="可见范围">{selected.submitted?.visibility}</Descriptions.Item>
                  <Descriptions.Item label="业务线">{selected.submitted?.business_line_name ?? selected.submitted?.business_line_id ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label="工作组">{selected.submitted?.work_group_name ?? selected.submitted?.work_group_id ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label="办公地点">
                    {selected.submitted?.office_location_names?.length
                      ? selected.submitted.office_location_names.join('、')
                      : selected.submitted?.office_location_ids?.join(', ') ?? '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="模板版本">{selected.submitted?.template_version_id ?? '无'}</Descriptions.Item>
                </Descriptions>

                {selected.status === 'pending' ? (
                  <>
                    <div className="kp-review-impact">
                      <Title level={4}>影响快照</Title>
                      {impactLoading ? <Skeleton active paragraph={{ rows: 3 }} /> : impact ? (
                        <>
                          <Text type="secondary">
                            版本 {impact.impact_revision} · {impact.impact_version.slice(0, 16)}…
                            {impact.impact_expires_at ? ` · 有效期至 ${new Date(impact.impact_expires_at).toLocaleString()}` : ''}
                          </Text>
                          {impact.impact.policy_version && (
                            <Descriptions column={1} size="small" className="kp-review-impact-policy">
                              <Descriptions.Item label="策略版本">
                                rev {impact.impact.policy_version.revision ?? '?'}
                              </Descriptions.Item>
                            </Descriptions>
                          )}
                          <Text type="secondary">
                            已锁定 {resources.length} 个资源引用
                            {Object.entries(resourceKinds).map(([kind, count]) => ` · ${kind} ×${count}`).join('')}
                          </Text>
                        </>
                      ) : <Alert type="error" message="未能读取有效影响快照" />}
                    </div>

                    <div className="kp-creation-confirmation">
                      <Checkbox checked={acknowledged} disabled={selfReview && !bypassSeparation} onChange={(event) => setAcknowledged(event.target.checked)}>
                        我确认获批后，申请人（不是审批人）将成为该工作区的唯一初始 Owner。
                      </Checkbox>
                    </div>
                    <Space>
                      <Button type="primary" loading={acting} disabled={!impact || !acknowledged || (selfReview && !bypassSeparation)} onClick={() => void approve()}>批准并创建</Button>
                      <Button danger disabled={acting || selfReview} onClick={() => setRejectOpen(true)}>拒绝</Button>
                    </Space>
                  </>
                ) : (
                  <Alert
                    type={selected.status === 'completed' ? 'success' : 'info'}
                    showIcon
                    message={`该申请已${requestStatus(selected.status).label}`}
                    description={
                      selected.result_uuid ? `已创建工作区: ${selected.result_uuid}`
                      : selected.failure_code ? `失败原因: ${selected.failure_code}`
                      : undefined
                    }
                  />
                )}
              </>
            )}
          </Card>
        </div>
      )}

      <Modal
        title="拒绝创建申请"
        open={rejectOpen}
        confirmLoading={acting}
        okButtonProps={{ danger: true, disabled: !reasonCode.trim() }}
        okText="确认拒绝"
        onOk={() => void reject()}
        onCancel={() => { if (!acting) setRejectOpen(false); }}
      >
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <div>
            <Text strong>原因代码</Text>
            <Input value={reasonCode} onChange={(event) => setReasonCode(event.target.value)} maxLength={100} />
          </div>
          <div>
            <Text strong>补充说明</Text>
            <Input.TextArea value={reasonText} onChange={(event) => setReasonText(event.target.value)} rows={4} maxLength={1000} showCount />
          </div>
        </Space>
      </Modal>
    </div>
  );
}
