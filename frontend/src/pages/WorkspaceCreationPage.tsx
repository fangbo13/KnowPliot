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
  Empty,
  Form,
  Input,
  Radio,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';
import { ArrowLeftOutlined, PlusOutlined } from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';

import { getApiErrorCode, getRateLimitDetails, isAbortError } from '../api/client';
import { templatesApi, type ScenarioTemplate } from '../api/templates';
import {
  workspaceCreationApi,
  type TaxonomyOption,
  type WorkspaceCreationRequest,
  type WorkspaceCreationSubmission,
} from '../api/workspaceCreation';
import { useCapabilities } from '../auth/CapabilityProvider';
import './WorkspaceCreationPage.css';

const { Text, Title, Paragraph } = Typography;
const TERMINAL = new Set(['completed', 'rejected', 'cancelled', 'expired', 'invalidated', 'failed']);

function errorDescription(error: unknown): string {
  const rateLimit = getRateLimitDetails(error);
  if (rateLimit) {
    return rateLimit.retryAfterSeconds == null
      ? '请求过于频繁，请稍后再试。'
      : `请求过于频繁，请在 ${rateLimit.retryAfterSeconds} 秒后再试。`;
  }
  const code = getApiErrorCode(error);
  if (code === 'workspace_creation_disabled') return '创建申请当前不可用，请联系平台管理员检查内测策略。';
  if (code === 'space_locator_conflict') return '该工作区短代码已被占用，请更换后重试。';
  if (code === 'request_already_pending') return '该短代码已经有一条待审批申请。';
  return '暂时无法完成请求，请检查内容后重试。';
}

function requestStatus(status: WorkspaceCreationRequest['status']) {
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

export default function WorkspaceCreationPage() {
  const capabilities = useCapabilities();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm<WorkspaceCreationSubmission>();
  const [businessLines, setBusinessLines] = useState<TaxonomyOption[]>([]);
  const [workGroups, setWorkGroups] = useState<TaxonomyOption[]>([]);
  const [offices, setOffices] = useState<TaxonomyOption[]>([]);
  const [templates, setTemplates] = useState<ScenarioTemplate[]>([]);
  const [requests, setRequests] = useState<WorkspaceCreationRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [dependentLoading, setDependentLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const loadSequence = useRef(0);
  const loadController = useRef<AbortController | null>(null);
  const dependentController = useRef<AbortController | null>(null);
  const submitController = useRef<AbortController | null>(null);

  const creationEnabled = capabilities.snapshot?.feature_availability.workspace_creation_approval ?? false;

  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    loadController.current?.abort();
    const controller = new AbortController();
    loadController.current = controller;
    setLoading(true);
    setError(null);
    try {
      const [lines, mine, availableTemplates] = await Promise.all([
        workspaceCreationApi.taxonomy('business-lines', undefined, controller.signal),
        workspaceCreationApi.mine(controller.signal),
        templatesApi.list({ is_active: true, sort: 'recommended' }, controller.signal).catch(() => []),
      ]);
      if (controller.signal.aborted || sequence !== loadSequence.current) return;
      setBusinessLines(lines);
      setRequests(mine);
      setTemplates(availableTemplates);
    } catch (loadError: unknown) {
      if (!isAbortError(loadError) && sequence === loadSequence.current) setError(errorDescription(loadError));
    } finally {
      if (!controller.signal.aborted && sequence === loadSequence.current) setLoading(false);
      if (loadController.current === controller) loadController.current = null;
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      loadSequence.current += 1;
      loadController.current?.abort();
      dependentController.current?.abort();
      submitController.current?.abort();
    };
  }, [load]);

  useEffect(() => {
    const requestedRevision = searchParams.get('template_version_id');
    if (!requestedRevision || !templates.some((template) => template.current_revision_id === requestedRevision)) return;
    if (!showForm) {
      setShowForm(true);
      return;
    }
    form.setFieldValue('template_version_id', requestedRevision);
  }, [form, searchParams, showForm, templates]);

  const selectBusinessLine = async (businessLineId: string) => {
    const line = businessLines.find((item) => item.id === businessLineId);
    form.setFieldsValue({ work_group_id: undefined as unknown as string, office_location_ids: [] });
    setWorkGroups([]);
    setOffices([]);
    if (!line) return;
    const sequence = ++loadSequence.current;
    dependentController.current?.abort();
    const controller = new AbortController();
    dependentController.current = controller;
    setDependentLoading(true);
    try {
      const [groups, locations] = await Promise.all([
        workspaceCreationApi.taxonomy('work-groups', line.id, controller.signal),
        workspaceCreationApi.taxonomy('office-locations', line.parent_id, controller.signal),
      ]);
      if (controller.signal.aborted || sequence !== loadSequence.current) return;
      setWorkGroups(groups);
      setOffices(locations);
    } catch (loadError: unknown) {
      if (!isAbortError(loadError) && sequence === loadSequence.current) message.error(errorDescription(loadError));
    } finally {
      if (!controller.signal.aborted && sequence === loadSequence.current) setDependentLoading(false);
      if (dependentController.current === controller) dependentController.current = null;
    }
  };

  const submit = async (values: WorkspaceCreationSubmission) => {
    if (submitting || !confirmed) return;
    const controller = new AbortController();
    submitController.current = controller;
    setSubmitting(true);
    try {
      const request = await workspaceCreationApi.submit({
        ...values,
        name: values.name.trim(),
        code: values.code.trim().toLowerCase(),
        purpose: values.purpose.trim(),
        visibility: values.join_policy === 'global' ? 'organization' : 'private',
        join_code: values.join_code?.trim() || undefined,
        template_version_id: values.template_version_id || null,
      }, controller.signal);
      if (controller.signal.aborted) return;
      setRequests((current) => [request, ...current.filter((item) => item.request_id !== request.request_id)]);
      form.resetFields();
      setConfirmed(false);
      setShowForm(false);
      message.success('申请已提交。审批完成前不会创建或切换工作区。');
    } catch (submitError: unknown) {
      if (!isAbortError(submitError)) message.error(errorDescription(submitError));
    } finally {
      if (!controller.signal.aborted) setSubmitting(false);
      if (submitController.current === controller) submitController.current = null;
    }
  };

  const cancel = async (request: WorkspaceCreationRequest) => {
    try {
      const updated = await workspaceCreationApi.cancel(request);
      setRequests((current) => current.map((item) => item.request_id === request.request_id ? updated : item));
      message.success('申请已取消。');
    } catch (cancelError: unknown) {
      message.error(errorDescription(cancelError));
    }
  };

  const templateOptions = useMemo(() => templates
    .filter((template) => template.current_revision_id)
    .map((template) => ({
      value: template.current_revision_id!,
      label: `${template.name} · v${template.current_revision_version ?? template.latest_version}`,
    })), [templates]);

  if (loading) {
    return <div className="kp-creation-page"><Skeleton active paragraph={{ rows: 8 }} /></div>;
  }

  return (
    <div className="kp-creation-page">
      <header className="kp-creation-hero">
        <Link to="/chat" className="kp-creation-back"><ArrowLeftOutlined /> 返回工作区</Link>
        <div className="kp-creation-kicker">INTERNAL BETA · GOVERNED CREATION</div>
        <Title level={1}>申请一个新的知识工作区</Title>
        <Paragraph>
          先定义用途和组织归属，再交由平台审批。申请获批前不会创建空间，也不会改变你当前的工作区。
        </Paragraph>
      </header>

      {error && <Alert type="error" showIcon message="创建服务暂时不可用" description={error} action={<Button onClick={() => void load()}>重新加载</Button>} />}
      {!creationEnabled && (
        <Alert type="warning" showIcon message="创建审批功能当前未开放" description="当前环境未启用工作区创建审批。你仍可查看已有申请。" />
      )}
      {creationEnabled && businessLines.length === 0 && (
        <Alert type="info" showIcon message="暂时没有可申请的业务线" description="平台需要先启用至少一条适用于内测用户的创建策略。" />
      )}

      <div className="kp-creation-toolbar">
        <div>
          <Title level={3}>我的申请</Title>
          <Text type="secondary">状态变化以服务端记录为准。</Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          disabled={!creationEnabled || businessLines.length === 0}
          onClick={() => setShowForm((value) => !value)}
        >
          {showForm ? '收起表单' : '新建申请'}
        </Button>
      </div>

      {showForm && (
        <Card className="kp-creation-form-card" bordered={false}>
          <Form<WorkspaceCreationSubmission>
            form={form}
            layout="vertical"
            initialValues={{ visibility: 'private', join_policy: 'access_code', office_location_ids: [], template_version_id: null }}
            onFinish={(values) => void submit(values)}
            requiredMark="optional"
          >
            <div className="kp-creation-form-grid">
              <Form.Item name="name" label="工作区名称" rules={[{ required: true }, { max: 200 }]}>
                <Input placeholder="例如：审计方法论知识库" autoComplete="off" />
              </Form.Item>
              <Form.Item name="code" label="短代码" extra="仅使用小写字母、数字和连字符。" rules={[{ required: true }, { pattern: /^[a-z0-9]+(?:-[a-z0-9]+)*$/ }]}>
                <Input placeholder="audit-methodology" autoComplete="off" />
              </Form.Item>
              <Form.Item name="business_line_id" label="业务线" rules={[{ required: true }]}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="选择业务线"
                  options={businessLines.map((item) => ({ value: item.id, label: item.display_name }))}
                  onChange={(value) => void selectBusinessLine(value)}
                />
              </Form.Item>
              <Form.Item name="work_group_id" label="工作组" rules={[{ required: true }]}>
                <Select loading={dependentLoading} disabled={!workGroups.length} placeholder="先选择业务线" options={workGroups.map((item) => ({ value: item.id, label: item.display_name }))} />
              </Form.Item>
              <Form.Item name="office_location_ids" label="办公地点" rules={[{ required: true, type: 'array', min: 1, message: '至少选择一个办公地点' }]}>
                <Select mode="multiple" loading={dependentLoading} disabled={!offices.length} placeholder="至少选择一个地点" options={offices.map((item) => ({ value: item.id, label: item.display_name }))} />
              </Form.Item>
              <Form.Item className="kp-creation-span" name="join_policy" label="加入策略" rules={[{ required: true }]} tooltip="选择空间的加入方式。邀请码模式下空间不可被发现，成员需凭码加入；全局可见模式下空间在发现页展示，用户可直接加入。">
                <Radio.Group>
                  <Space direction="vertical">
                    <Radio value="access_code">邀请码加入 — 空间隐藏，凭加入码加入</Radio>
                    <Radio value="global">全局可见 — 在发现页展示，用户可直接加入</Radio>
                  </Space>
                </Radio.Group>
              </Form.Item>
              <Form.Item className="kp-creation-span" shouldUpdate={(prev, curr) => prev.join_policy !== curr.join_policy}>
                {({ getFieldValue }) => (
                  getFieldValue('join_policy') === 'access_code' ? (
                    <Form.Item name="join_code" label="加入码" extra="留空则系统自动生成。可自定义 4-20 位字母、数字和连字符的加入码。" rules={[{ max: 24 }]}>
                      <Input placeholder="留空自动生成，如 KP-AB12CD" autoComplete="off" />
                    </Form.Item>
                  ) : (
                    <Alert type="info" showIcon message="全局可见空间将出现在发现页，任何已认证用户均可直接加入。" style={{ marginBottom: 24 }} />
                  )
                )}
              </Form.Item>
              <Form.Item className="kp-creation-span" name="purpose" label="用途说明" rules={[{ required: true }, { min: 8 }, { max: 2000 }]}>
                <Input.TextArea rows={4} showCount maxLength={2000} placeholder="说明知识边界、目标使用者和预期价值。" />
              </Form.Item>
              <Form.Item className="kp-creation-span" name="template_version_id" label="初始模板版本">
                <Select allowClear placeholder="不使用模板" options={templateOptions} />
              </Form.Item>
            </div>
            <div className="kp-creation-confirmation">
              <Checkbox checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}>
                我确认提交后将进入平台审批，获批时申请人将成为该工作区的唯一初始 Owner。
              </Checkbox>
            </div>
            <Space>
              <Button type="primary" htmlType="submit" loading={submitting} disabled={!confirmed}>提交审批</Button>
              <Button onClick={() => { form.resetFields(); setConfirmed(false); setShowForm(false); }}>取消填写</Button>
            </Space>
          </Form>
        </Card>
      )}

      <section className="kp-creation-list" aria-label="我的工作区创建申请">
        {requests.length === 0 ? (
          <Empty description="还没有创建申请" />
        ) : requests.map((request) => {
          const status = requestStatus(request.status);
          return (
            <Card key={request.request_id} className="kp-creation-request" bordered={false}>
              <div>
                <Space wrap>
                  <Title level={4}>{request.submitted?.name ?? '工作区创建申请'}</Title>
                  <Tag color={status.color}>{status.label}</Tag>
                </Space>
                <Paragraph>{request.submitted?.purpose ?? '申请详情已记录。'}</Paragraph>
                <Text type="secondary">
                  {request.submitted?.code ? `代码 ${request.submitted.code} · ` : ''}
                  版本 {request.request_version}
                  {request.expires_at ? ` · 有效期至 ${new Date(request.expires_at).toLocaleString()}` : ''}
                </Text>
              </div>
              {request.status === 'pending' && !TERMINAL.has(request.status) && (
                <Button danger onClick={() => void cancel(request)}>取消申请</Button>
              )}
            </Card>
          );
        })}
      </section>
    </div>
  );
}
