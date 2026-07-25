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
  Form,
  Input,
  Modal,
  Radio,
  Segmented,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';
import { ArrowLeftOutlined, PlusOutlined } from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { getApiErrorCode, getRateLimitDetails, isAbortError } from '../api/client';
import { templatesApi, type ScenarioTemplate } from '../api/templates';
import {
  workspaceCreationApi,
  type TaxonomyOption,
  type WorkspaceCreationRequest,
  type WorkspaceCreationSubmission,
} from '../api/workspaceCreation';
import { useCapabilities } from '../auth/CapabilityProvider';
import { useAuth } from '../auth/AuthProvider';
import './WorkspaceCreationPage.css';

const { Text, Title, Paragraph } = Typography;
const TERMINAL = new Set(['completed', 'rejected', 'cancelled', 'expired', 'invalidated', 'failed']);

/** Service-line codes — mirror User.SERVICE_LINE_CHOICES on the backend. */
const SERVICE_LINES = ['assurance', 'consulting', 'tax', 'strategy_transactions', 'core'] as const;

/** EY China major office locations — mirror ProfilePage registration options. */
const EY_OFFICE_LOCATIONS = [
  '北京', '上海', '广州', '深圳', '成都', '武汉', '杭州', '南京',
  '青岛', '大连', '厦门', '天津', '苏州', '西安', '重庆', '济南',
  '沈阳', '长沙', '郑州', '合肥', '昆明', '海口', '香港', '澳门',
];

/**
 * Resolve a business-line taxonomy option to the same label shown during
 * registration (service-line i18n key).  Falls back to the taxonomy
 * display_name when the code does not match a known service line.
 */
function serviceLineLabel(item: TaxonomyOption, t: (key: string) => string): string {
  const code = item.normalized_code;
  return (SERVICE_LINES as readonly string[]).includes(code) ? t(`sl_${code}`) : item.display_name;
}

/**
 * Filter office-location taxonomy options to only those that match the
 * registration-time EY_OFFICE_LOCATIONS list.  Falls back to the full
 * taxonomy list when no overlap exists (e.g. seed data mismatch).
 */
function registrationOffices(locations: TaxonomyOption[]): TaxonomyOption[] {
  const filtered = locations.filter((loc) => EY_OFFICE_LOCATIONS.includes(loc.display_name));
  return filtered.length > 0 ? filtered : locations;
}

/**
 * Pick office location IDs to auto-select based on user profile.
 * If only one location exists, select it. Otherwise try matching the
 * user's office_location against display_name or normalized_code.
 */
function pickAutoOffices(locations: TaxonomyOption[], userOffice?: string): string[] {
  if (locations.length === 0) return [];
  if (locations.length === 1) return [locations[0].id];
  if (userOffice) {
    const matched = locations.find(
      (loc) => loc.display_name === userOffice || loc.normalized_code === userOffice,
    );
    if (matched) return [matched.id];
  }
  return [];
}

function errorDescription(error: unknown): string {
  const rateLimit = getRateLimitDetails(error);
  if (rateLimit) {
    return rateLimit.retryAfterSeconds == null
      ? '请求过于频繁，请稍后再试。'
      : `请求过于频繁，请在 ${rateLimit.retryAfterSeconds} 秒后再试。`;
  }
  const code = getApiErrorCode(error);
  if (code === 'workspace_creation_disabled') return '创建申请当前不可用，请联系平台管理员检查内测策略。';
  if (code === 'space_locator_conflict') return '工作区标识冲突，请重新提交申请。';
  if (code === 'request_already_pending') return '已有同标识的待审批申请，请重新提交。';
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
  const { user } = useAuth();
  const { t } = useTranslation('common');
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
  const [filterStatus, setFilterStatus] = useState<'pending' | 'processed' | 'all'>('pending');
  const loadSequence = useRef(0);
  const loadController = useRef<AbortController | null>(null);
  const dependentController = useRef<AbortController | null>(null);
  const submitController = useRef<AbortController | null>(null);

  const creationEnabled = capabilities.snapshot?.feature_availability.workspace_creation_approval ?? false;

  const filteredRequests = useMemo(() => {
    if (filterStatus === 'all') return requests;
    if (filterStatus === 'pending') return requests.filter((r) => r.status === 'pending');
    return requests.filter((r) => r.status !== 'pending');
  }, [requests, filterStatus]);

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
      // Auto-select business line — prefer the user's service_line, fall back to
      // single-option auto-select.  Reuses the registration profile.
      const matchedLine = user?.service_line
        ? lines.find((line) => line.normalized_code === user.service_line)
        : undefined;
      const autoLine = matchedLine ?? (lines.length === 1 ? lines[0] : undefined);
      if (autoLine) {
        form.setFieldValue('business_line_id', autoLine.id);
        try {
          const [groups, locations] = await Promise.all([
            workspaceCreationApi.taxonomy('work-groups', autoLine.id, controller.signal),
            workspaceCreationApi.taxonomy('office-locations', autoLine.parent_id, controller.signal),
          ]);
          if (controller.signal.aborted || sequence !== loadSequence.current) return;
          setWorkGroups(groups);
          setOffices(locations);
          if (groups.length === 1) {
            form.setFieldValue('work_group_id', groups[0].id);
          }
          const autoOfficeIds = pickAutoOffices(locations, user?.office_location);
          if (autoOfficeIds.length > 0) {
            form.setFieldValue('office_location_ids', autoOfficeIds);
          }
        } catch (depError: unknown) {
          if (!isAbortError(depError) && sequence === loadSequence.current) message.error(errorDescription(depError));
        }
      }
    } catch (loadError: unknown) {
      if (!isAbortError(loadError) && sequence === loadSequence.current) setError(errorDescription(loadError));
    } finally {
      if (!controller.signal.aborted && sequence === loadSequence.current) setLoading(false);
      if (loadController.current === controller) loadController.current = null;
    }
  }, [form, user]);

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
      if (groups.length === 1) {
        form.setFieldValue('work_group_id', groups[0].id);
      }
      const autoOfficeIds = pickAutoOffices(locations, user?.office_location);
      if (autoOfficeIds.length > 0) {
        form.setFieldValue('office_location_ids', autoOfficeIds);
      }
    } catch (loadError: unknown) {
      if (!isAbortError(loadError) && sequence === loadSequence.current) message.error(errorDescription(loadError));
    } finally {
      if (!controller.signal.aborted && sequence === loadSequence.current) setDependentLoading(false);
      if (dependentController.current === controller) dependentController.current = null;
    }
  };

  const confirmSubmit = () => {
    if (submitting || !confirmed) return;
    Modal.confirm({
      title: '确认提交审批申请',
      content: '提交后申请将进入平台审批流程，提交后不可修改。是否确定提交？',
      okText: '确认提交',
      cancelText: '取消',
      onOk: () => {
        form.submit();
      },
    });
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

  const confirmCancel = (request: WorkspaceCreationRequest) => {
    Modal.confirm({
      title: '确认取消审批申请',
      content: '取消后该申请将被撤销且不可恢复。是否确定取消？',
      okText: '确认取消',
      cancelText: '返回',
      okButtonProps: { danger: true },
      onOk: () => void cancel(request),
    });
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
              <Form.Item name="business_line_id" label="业务线" rules={[{ required: true }]}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="选择业务线"
                  options={businessLines.map((item) => ({ value: item.id, label: serviceLineLabel(item, t) }))}
                  onChange={(value) => void selectBusinessLine(value)}
                />
              </Form.Item>
              <Form.Item name="work_group_id" label="工作组" rules={[{ required: true }]}>
                <Select loading={dependentLoading} disabled={!workGroups.length} placeholder="先选择业务线" options={workGroups.map((item) => ({ value: item.id, label: item.display_name }))} />
              </Form.Item>
              <Form.Item name="office_location_ids" label="办公地点" rules={[{ required: true, type: 'array', min: 1, message: '至少选择一个办公地点' }]}>
                <Select mode="multiple" loading={dependentLoading} disabled={!offices.length} placeholder="至少选择一个地点" options={registrationOffices(offices).map((item) => ({ value: item.id, label: item.display_name }))} />
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
              <Button type="primary" htmlType="button" loading={submitting} disabled={!confirmed} onClick={confirmSubmit}>提交审批</Button>
              <Button onClick={() => { form.resetFields(); setConfirmed(false); setShowForm(false); }}>取消填写</Button>
            </Space>
          </Form>
        </Card>
      )}

      {!showForm && (
        <>
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
          {filteredRequests.length > 0 ? (
            <section className="kp-creation-list" aria-label="我的工作区创建申请">
              {filteredRequests.map((request) => {
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
                      <Button danger onClick={() => confirmCancel(request)}>取消申请</Button>
                    )}
                  </Card>
                );
              })}
            </section>
          ) : (
            <div className="kp-creation-empty">
              <Text type="secondary">
                {filterStatus === 'pending' ? '当前没有待审批的申请。' : filterStatus === 'processed' ? '当前没有已处理的申请。' : '还没有创建申请。'}
              </Text>
            </div>
          )}
        </>
      )}
    </div>
  );
}
