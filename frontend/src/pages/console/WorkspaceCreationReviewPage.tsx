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
  Checkbox,
  Descriptions,
  Empty,
  Input,
  Modal,
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
} from '../../api/workspaceCreation';
import { useAuth } from '../../auth/AuthProvider';
import '../WorkspaceCreationPage.css';

const { Title, Paragraph, Text } = Typography;

function reviewError(error: unknown): string {
  const rateLimit = getRateLimitDetails(error);
  if (rateLimit) return rateLimit.retryAfterSeconds == null
    ? '请求过于频繁，请稍后再试。'
    : `请求过于频繁，请在 ${rateLimit.retryAfterSeconds} 秒后重试。`;
  const code = getApiErrorCode(error);
  if (code === 'self_approval_forbidden') return '申请人与审批人必须分离，不能审批自己的申请。';
  if (code === 'stale_request_version' || code === 'stale_impact_version') return '申请或影响快照已经变化，请刷新后重新审核。';
  if (code === 'request_not_pending') return '该申请已不再处于待审批状态。';
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
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reasonCode, setReasonCode] = useState('scope_not_approved');
  const [reasonText, setReasonText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const queueController = useRef<AbortController | null>(null);
  const impactController = useRef<AbortController | null>(null);
  const sequence = useRef(0);

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
      setSelected((prior) => rows.find((row) => row.request_id === prior?.request_id) ?? rows[0] ?? null);
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
    if (!selected) return;
    const controller = new AbortController();
    impactController.current = controller;
    setImpactLoading(true);
    workspaceCreationApi.impact(selected.request_id, controller.signal).then(
      (nextImpact) => { if (!controller.signal.aborted) setImpact(nextImpact); },
      (impactError: unknown) => { if (!isAbortError(impactError)) message.error(reviewError(impactError)); },
    ).finally(() => { if (!controller.signal.aborted) setImpactLoading(false); });
    return () => controller.abort();
  }, [selected?.request_id]);

  const approve = async () => {
    if (!selected || !acknowledged || acting || selected.requester_uuid === user?.id) return;
    setActing(true);
    try {
      // Approval always uses an impact fetched immediately before the mutation;
      // a previously rendered snapshot is informative only.
      const freshImpact = await workspaceCreationApi.impact(selected.request_id);
      await workspaceCreationApi.approve(selected, freshImpact);
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
  const resources = Array.isArray(impact?.impact.resources) ? impact.impact.resources : [];

  return (
    <div className="kp-review-page">
      <div className="kp-review-heading">
        <div>
          <div className="kp-creation-kicker">SEPARATION OF DUTIES</div>
          <Title level={1}>工作区创建审批</Title>
          <Paragraph>只处理待审批请求；批准前会重新获取影响快照并执行服务端并发校验。</Paragraph>
        </div>
        <Button onClick={() => void loadQueue()}>刷新队列</Button>
      </div>

      {error && <Alert type="error" showIcon message="审批队列不可用" description={error} />}
      {queue.length === 0 ? <Empty description="当前没有待审批申请" /> : (
        <div className="kp-review-grid">
          <aside className="kp-review-queue" aria-label="待审批申请">
            {queue.map((request) => (
              <button
                type="button"
                key={request.request_id}
                className={`kp-review-queue-item${selected?.request_id === request.request_id ? ' is-active' : ''}`}
                onClick={() => setSelected(request)}
              >
                <span>{request.submitted?.name ?? '未命名申请'}</span>
                <small>{request.submitted?.code ?? request.request_id}</small>
              </button>
            ))}
          </aside>

          <Card className="kp-review-detail" bordered={false}>
            {selected && (
              <>
                <Space wrap>
                  <Title level={3}>{selected.submitted?.name}</Title>
                  <Tag color="gold">待审批 · v{selected.request_version}</Tag>
                </Space>
                <Paragraph>{selected.submitted?.purpose}</Paragraph>
                {selfReview && (
                  <Alert type="warning" showIcon message="职责分离" description="这是你提交的申请，必须由另一位具备平台审批能力的人员处理。" />
                )}
                <Descriptions column={1} size="small" className="kp-review-descriptions">
                  <Descriptions.Item label="申请人 UUID">{selected.requester_uuid}</Descriptions.Item>
                  <Descriptions.Item label="短代码">{selected.submitted?.code}</Descriptions.Item>
                  <Descriptions.Item label="可见范围">{selected.submitted?.visibility}</Descriptions.Item>
                  <Descriptions.Item label="业务线">{selected.submitted?.business_line_id}</Descriptions.Item>
                  <Descriptions.Item label="工作组">{selected.submitted?.work_group_id}</Descriptions.Item>
                  <Descriptions.Item label="办公地点">{selected.submitted?.office_location_ids.join(', ')}</Descriptions.Item>
                  <Descriptions.Item label="模板版本">{selected.submitted?.template_version_id ?? '无'}</Descriptions.Item>
                </Descriptions>

                <div className="kp-review-impact">
                  <Title level={4}>影响快照</Title>
                  {impactLoading ? <Skeleton active paragraph={{ rows: 3 }} /> : impact ? (
                    <>
                      <Text type="secondary">revision {impact.impact_revision} · {impact.impact_version.slice(0, 16)}…</Text>
                      <ul>
                        {resources.map((resource, index) => (
                          <li key={`${String(resource.kind ?? 'resource')}-${index}`}>
                            <strong>{String(resource.kind ?? 'resource')}</strong>
                            {' · '}{String(resource.code ?? resource.id ?? resource.organization_id ?? '')}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : <Alert type="error" message="未能读取有效影响快照" />}
                </div>

                <div className="kp-creation-confirmation">
                  <Checkbox checked={acknowledged} disabled={selfReview} onChange={(event) => setAcknowledged(event.target.checked)}>
                    我确认获批后，申请人（不是审批人）将成为该工作区的唯一初始 Owner。
                  </Checkbox>
                </div>
                <Space>
                  <Button type="primary" loading={acting} disabled={!impact || !acknowledged || selfReview} onClick={() => void approve()}>批准并创建</Button>
                  <Button danger disabled={acting || selfReview} onClick={() => setRejectOpen(true)}>拒绝</Button>
                </Space>
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
