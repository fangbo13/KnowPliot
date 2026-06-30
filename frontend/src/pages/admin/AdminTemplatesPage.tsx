/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card, Table, Button, Tag, Modal, Select, Input, Space, Form, Switch, Tooltip,
  message as antdMessage,
} from 'antd';
import { PlusOutlined, ReloadOutlined, BuildOutlined, FileTextOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  templatesApi,
  type ScenarioTemplate,
  type ScenarioTemplateApplication,
  type ScenarioTemplateRevision,
} from '../../api/templates';
import { adminApi, type Organization, type BusinessLine } from '../../api/admin';

export default function AdminTemplatesPage() {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<ScenarioTemplate[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [lines, setLines] = useState<BusinessLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [scenarioFilter, setScenarioFilter] = useState<ScenarioTemplate['scenario_type'] | undefined>();
  const [statusFilter, setStatusFilter] = useState<'active' | 'inactive' | undefined>();
  const [scopeFilter, setScopeFilter] = useState<'global' | 'organization' | 'business_line' | undefined>();
  const [orgFilter, setOrgFilter] = useState<string | undefined>();
  const [lineFilter, setLineFilter] = useState<string | undefined>();

  // Modal / Form state for space instantiation
  const [open, setOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<ScenarioTemplate | null>(null);
  const [form] = Form.useForm();
  const [instantiating, setInstantiating] = useState(false);
  const [selectedOrgId, setSelectedOrgId] = useState<string>('');

  // Modal / Form state for creating/editing templates
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<ScenarioTemplate | null>(null);
  const [templateForm] = Form.useForm();
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [templateOrgId, setTemplateOrgId] = useState<string | null>(null);

  // Modal / Form state for application history
  const [appsModalOpen, setAppsModalOpen] = useState(false);
  const [appsLoading, setAppsLoading] = useState(false);
  const [applications, setApplications] = useState<ScenarioTemplateApplication[]>([]);
  const [selectedAppTemplate, setSelectedAppTemplate] = useState<ScenarioTemplate | null>(null);

  // Modal / Form state for revision history
  const [revisionsModalOpen, setRevisionsModalOpen] = useState(false);
  const [revisionsLoading, setRevisionsLoading] = useState(false);
  const [revisions, setRevisions] = useState<ScenarioTemplateRevision[]>([]);
  const [selectedRevTemplate, setSelectedRevTemplate] = useState<ScenarioTemplate | null>(null);

  // Snapshot detail modal state
  const [snapshotModalOpen, setSnapshotModalOpen] = useState(false);
  const [selectedRevision, setSelectedRevision] = useState<ScenarioTemplateRevision | null>(null);

  // Modal / Form state for cloning templates
  const [cloneModalOpen, setCloneModalOpen] = useState(false);
  const [cloneForm] = Form.useForm();
  const [cloning, setCloning] = useState(false);
  const [selectedCloneTemplate, setSelectedCloneTemplate] = useState<ScenarioTemplate | null>(null);
  const [cloneOrgId, setCloneOrgId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [tpls, o, b] = await Promise.all([
        templatesApi.list({
          q: searchText.trim() || undefined,
          scenario_type: scenarioFilter,
          is_active: statusFilter === undefined ? undefined : statusFilter === 'active',
          scope: scopeFilter,
          organization: orgFilter,
          business_line: lineFilter,
        }).catch(() => []),
        adminApi.organizations().catch(() => []),
        adminApi.businessLines().catch(() => []),
      ]);
      setTemplates(tpls);
      setOrgs(o);
      setLines(b);
      if (o.length > 0) {
        setSelectedOrgId(o[0].id);
      }
    } finally {
      setLoading(false);
    }
  }, [lineFilter, orgFilter, scenarioFilter, scopeFilter, searchText, statusFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Space creation trigger
  const openCreateModal = (tpl: ScenarioTemplate) => {
    setSelectedTemplate(tpl);
    setSelectedOrgId(orgs.length > 0 ? orgs[0].id : '');
    form.setFieldsValue({
      name: `${tpl.name} Space`,
      code: `${tpl.code}-space`,
      organization: orgs.length > 0 ? orgs[0].id : undefined,
      business_line: undefined,
      visibility: tpl.default_visibility,
    });
    setOpen(true);
  };

  const handleCreateSpace = async () => {
    if (!selectedTemplate) return;
    try {
      const values = await form.validateFields();
      setInstantiating(true);
      await templatesApi.createSpace(selectedTemplate.id, {
        name: values.name,
        code: values.code,
        organization: values.organization || null,
        business_line: values.business_line || null,
        visibility: values.visibility || undefined,
      });

      antdMessage.success(t('space_create_success') || 'Space created successfully');
      setOpen(false);
      navigate('/spaces/manage');
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === 'object') {
          const fields = Object.keys(detail).map(k => ({
            name: k,
            errors: Array.isArray(detail[k]) ? detail[k] : [detail[k]],
          }));
          form.setFields(fields);
        } else {
          antdMessage.error(detail);
        }
      } else {
        antdMessage.error(t('space_create_failed') || 'Failed to instantiate space');
      }
    } finally {
      setInstantiating(false);
    }
  };

  // Template Create/Edit handlers
  const openCreateTemplateModal = () => {
    setEditingTemplate(null);
    setTemplateOrgId(null);
    templateForm.resetFields();
    templateForm.setFieldsValue({
      default_language: 'en',
      default_visibility: 'private',
      is_active: true,
      quick_questions: '',
    });
    setTemplateModalOpen(true);
  };

  const openEditTemplateModal = (tpl: ScenarioTemplate) => {
    setEditingTemplate(tpl);
    setTemplateOrgId(tpl.organization || null);
    templateForm.resetFields();
    templateForm.setFieldsValue({
      name: tpl.name,
      code: tpl.code,
      description: tpl.description,
      scenario_type: tpl.scenario_type,
      default_language: tpl.default_language,
      icon: tpl.icon,
      default_visibility: tpl.default_visibility,
      is_active: tpl.is_active,
      organization: tpl.organization || undefined,
      business_line: tpl.business_line || undefined,
      quick_questions: tpl.quick_questions ? tpl.quick_questions.join('\n') : '',
    });
    setTemplateModalOpen(true);
  };

  const handleSaveTemplate = async () => {
    try {
      const values = await templateForm.validateFields();
      setSavingTemplate(true);

      const q_text: string = values.quick_questions || '';
      const quick_questions = q_text
        .split('\n')
        .map((q) => q.trim())
        .filter(Boolean);

      const payload = {
        name: values.name,
        code: values.code,
        description: values.description || '',
        scenario_type: values.scenario_type,
        default_language: values.default_language,
        icon: values.icon || '',
        default_visibility: values.default_visibility,
        is_active: values.is_active,
        organization: values.organization || null,
        business_line: values.business_line || null,
        quick_questions,
      };

      if (editingTemplate) {
        await templatesApi.update(editingTemplate.id, payload);
        antdMessage.success(t('save_success') || 'Template updated successfully');
      } else {
        await templatesApi.create(payload);
        antdMessage.success(t('create_success') || 'Template created successfully');
      }

      setTemplateModalOpen(false);
      await refresh();
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === 'object') {
          const fields = Object.keys(detail).map((k) => ({
            name: k,
            errors: Array.isArray(detail[k]) ? detail[k] : [detail[k]],
          }));
          templateForm.setFields(fields);
        } else {
          antdMessage.error(detail);
        }
      } else if (err?.response?.data) {
        const data = err.response.data;
        if (typeof data === 'object') {
          const fields = Object.keys(data).map((k) => ({
            name: k,
            errors: Array.isArray(data[k]) ? data[k] : [data[k]],
          }));
          templateForm.setFields(fields);
        } else {
          antdMessage.error(String(data));
        }
      } else {
        antdMessage.error(t('save_failed') || 'Failed to save template');
      }
    } finally {
      setSavingTemplate(false);
    }
  };

  const openApplicationsModal = async (tpl: ScenarioTemplate) => {
    setSelectedAppTemplate(tpl);
    setAppsLoading(true);
    setAppsModalOpen(true);
    try {
      const data = await templatesApi.applications(tpl.id);
      setApplications(data);
    } catch (err) {
      antdMessage.error('Failed to load applications history');
    } finally {
      setAppsLoading(false);
    }
  };

  const openRevisionsModal = async (tpl: ScenarioTemplate) => {
    setSelectedRevTemplate(tpl);
    setRevisionsLoading(true);
    setRevisionsModalOpen(true);
    try {
      const data = await templatesApi.revisions(tpl.id);
      setRevisions(data);
    } catch (err) {
      antdMessage.error('Failed to load revisions history');
    } finally {
      setRevisionsLoading(false);
    }
  };

  const openSnapshotModal = (rev: ScenarioTemplateRevision) => {
    setSelectedRevision(rev);
    setSnapshotModalOpen(true);
  };

  const openCloneModal = (tpl: ScenarioTemplate) => {
    setSelectedCloneTemplate(tpl);
    setCloneOrgId(tpl.organization || null);
    cloneForm.resetFields();
    cloneForm.setFieldsValue({
      name: `${tpl.name} Copy`,
      code: `${tpl.code}-copy`,
      is_active: true,
      organization: tpl.organization || undefined,
      business_line: tpl.business_line || undefined,
    });
    setCloneModalOpen(true);
  };

  const handleCloneTemplate = async () => {
    if (!selectedCloneTemplate) return;
    try {
      const values = await cloneForm.validateFields();
      setCloning(true);
      await templatesApi.clone(selectedCloneTemplate.id, {
        name: values.name,
        code: values.code,
        organization: values.organization || null,
        business_line: values.business_line || null,
        is_active: values.is_active,
      });

      antdMessage.success(t('clone_success') || 'Template cloned successfully');
      setCloneModalOpen(false);
      await refresh();
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === 'object') {
          const fields = Object.keys(detail).map((k) => ({
            name: k,
            errors: Array.isArray(detail[k]) ? detail[k] : [detail[k]],
          }));
          cloneForm.setFields(fields);
        } else {
          antdMessage.error(detail);
        }
      } else if (err?.response?.data) {
        const data = err.response.data;
        if (typeof data === 'object') {
          const fields = Object.keys(data).map((k) => ({
            name: k,
            errors: Array.isArray(data[k]) ? data[k] : [data[k]],
          }));
          cloneForm.setFields(fields);
        } else {
          antdMessage.error(String(data));
        }
      } else {
        antdMessage.error(t('clone_failed') || 'Failed to clone template');
      }
    } finally {
      setCloning(false);
    }
  };

  const handleArchive = (tpl: ScenarioTemplate) => {
    Modal.confirm({
      title: t('archive_template_confirm') || 'Are you sure you want to archive this template?',
      content: tpl.name,
      okText: t('confirm') || 'Confirm',
      cancelText: t('cancel') || 'Cancel',
      okType: 'danger',
      onOk: async () => {
        try {
          await templatesApi.archive(tpl.id);
          antdMessage.success(t('archive_success') || 'Template archived successfully');
          await refresh();
        } catch (err: any) {
          antdMessage.error(err?.response?.data?.detail || t('archive_failed') || 'Failed to archive template');
        }
      }
    });
  };

  const handleRestore = (tpl: ScenarioTemplate) => {
    Modal.confirm({
      title: t('restore_template_confirm') || 'Are you sure you want to restore this template?',
      content: tpl.name,
      okText: t('confirm') || 'Confirm',
      cancelText: t('cancel') || 'Cancel',
      onOk: async () => {
        try {
          await templatesApi.restore(tpl.id);
          antdMessage.success(t('restore_success') || 'Template restored successfully');
          await refresh();
        } catch (err: any) {
          antdMessage.error(err?.response?.data?.detail || t('restore_failed') || 'Failed to restore template');
        }
      }
    });
  };

  const columns = [
    {
      title: t('space_name') || 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, r: ScenarioTemplate) => (
        <Space>
          {r.icon ? (
            <BuildOutlined style={{ color: '#1890ff', fontSize: 16 }} />
          ) : (
            <FileTextOutlined style={{ color: '#8c8c8c', fontSize: 16 }} />
          )}
          <span style={{ fontWeight: 600 }}>{name}</span>
        </Space>
      ),
    },
    {
      title: t('space_code') || 'Code',
      dataIndex: 'code',
      key: 'code',
      render: (code: string) => <code style={{ fontSize: 13 }}>{code}</code>,
    },
    {
      title: t('kb_type') || 'Type',
      dataIndex: 'scenario_type',
      key: 'scenario_type',
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: t('admin_template_scope') || 'Scope',
      key: 'scope',
      render: (_: any, r: ScenarioTemplate) => {
        if (r.business_line_name) {
          return <Tag color="blue">BL: {r.business_line_name}</Tag>;
        }
        if (r.organization_name) {
          return <Tag color="gold">Org: {r.organization_name}</Tag>;
        }
        return <Tag color="green">{t('admin_template_global') || 'Global'}</Tag>;
      },
    },
    {
      title: t('language') || 'Language',
      dataIndex: 'default_language',
      key: 'default_language',
      render: (lang: string) => <Tag>{lang.toUpperCase()}</Tag>,
    },
    {
      title: t('space_visibility') || 'Visibility',
      dataIndex: 'default_visibility',
      key: 'default_visibility',
      render: (v: string) => <Tag color="orange">{t(`visibility_${v}`) || v}</Tag>,
    },
    {
      title: t('member_status') || 'Status',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active: boolean) => (
        <Tag color={active ? 'green' : 'red'}>
          {active ? t('admin_active') || 'Active' : t('admin_inactive') || 'Inactive'}
        </Tag>
      ),
    },
    {
      title: t('admin_template_version') || 'Version',
      dataIndex: 'latest_version',
      key: 'latest_version',
      render: (val: number) => (val ? `v${val}` : '-'),
    },
    {
      title: t('quick_questions_count') || 'Quick Questions',
      dataIndex: 'quick_questions',
      key: 'quick_questions',
      render: (questions: string[]) => (
        <span>{questions ? questions.length : 0}</span>
      ),
    },
    {
      title: t('admin_template_usage') || 'Usage',
      dataIndex: 'usage_count',
      key: 'usage_count',
      render: (val: number) => <span style={{ fontWeight: 600 }}>{val ?? 0}</span>,
    },
    {
      title: t('admin_template_last_applied') || 'Last Applied',
      dataIndex: 'last_applied_at',
      key: 'last_applied_at',
      render: (val: string | null) => (val ? new Date(val).toLocaleString() : '-'),
    },
    {
      title: '',
      key: 'actions',
      render: (_: any, r: ScenarioTemplate) => (
        <Space size="middle">
          {r.can_manage ? (
            <Button
              type="link"
              size="small"
              onClick={() => openEditTemplateModal(r)}
              style={{ padding: 0 }}
            >
              {t('edit') || 'Edit'}
            </Button>
          ) : (
            <Tooltip
              title={
                t('admin_template_edit_disabled_global') ||
                'Global templates can only be edited by platform admins.'
              }
            >
              <span
                style={{
                  cursor: 'not-allowed',
                  color: 'var(--color-text-placeholder, rgba(0, 0, 0, 0.25))',
                  fontSize: 14,
                }}
              >
                {t('edit') || 'Edit'}
              </span>
            </Tooltip>
          )}
          <Button
            type="link"
            size="small"
            onClick={() => openCloneModal(r)}
            style={{ padding: 0 }}
          >
            {t('clone') || 'Clone'}
          </Button>
          {r.can_manage ? (
            r.is_active ? (
              <Button
                type="link"
                danger
                size="small"
                onClick={() => handleArchive(r)}
                style={{ padding: 0 }}
              >
                {t('archive') || 'Archive'}
              </Button>
            ) : (
              <Button
                type="link"
                size="small"
                onClick={() => handleRestore(r)}
                style={{ padding: 0 }}
              >
                {t('restore') || 'Restore'}
              </Button>
            )
          ) : (
            <Tooltip title={t('admin_template_action_disabled') || 'You do not have permission to manage this template.'}>
              <span
                style={{
                  cursor: 'not-allowed',
                  color: 'var(--color-text-placeholder, rgba(0, 0, 0, 0.25))',
                  fontSize: 14,
                }}
              >
                {r.is_active ? (t('archive') || 'Archive') : (t('restore') || 'Restore')}
              </span>
            </Tooltip>
          )}
          <Button
            type="link"
            size="small"
            onClick={() => openApplicationsModal(r)}
            style={{ padding: 0 }}
          >
            {t('admin_template_applications') || 'Applications'}
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => openRevisionsModal(r)}
            style={{ padding: 0 }}
          >
            {t('admin_template_revisions') || 'Revisions'}
          </Button>
          <Button
            type="primary"
            size="small"
            disabled={!r.is_active}
            onClick={() => openCreateModal(r)}
            style={{ borderRadius: 6 }}
          >
            {t('create_space') || 'Create Space'}
          </Button>
        </Space>
      ),
    },
  ];

  const scopedLines = lines.filter((l) => l.organization === selectedOrgId);
  const templateScopedLines = lines.filter((l) => l.organization === templateOrgId);
  const cloneScopedLines = lines.filter((l) => l.organization === cloneOrgId);
  const filterScopedLines = orgFilter ? lines.filter((l) => l.organization === orgFilter) : lines;

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">{t('admin_nav_templates') || 'Scenario Templates'}</h1>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openCreateTemplateModal}
            style={{ borderRadius: 8 }}
          >
            {t('admin_create_template') || 'Create Template'}
          </Button>
        </Space>
      </div>

      <Card styles={{ body: { padding: 16 } }} style={{ marginBottom: 16, borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
        <Space wrap size="middle">
          <Input.Search
            allowClear
            value={searchText}
            placeholder={t('admin_template_search_placeholder') || 'Search templates'}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={(value) => setSearchText(value)}
            style={{ width: 260 }}
          />
          <Select
            allowClear
            value={scenarioFilter}
            placeholder={t('admin_template_filter_type') || 'Scenario type'}
            onChange={(value) => setScenarioFilter(value)}
            options={[
              { value: 'onboarding', label: 'Onboarding' },
              { value: 'audit', label: 'Audit' },
              { value: 'tax', label: 'Tax' },
              { value: 'consulting', label: 'Consulting' },
              { value: 'core_services', label: 'Core Business Services' },
              { value: 'standards_qa', label: 'Standards QA' },
              { value: 'project_ai', label: 'Project AI' },
            ]}
            style={{ width: 190 }}
          />
          <Select
            allowClear
            value={statusFilter}
            placeholder={t('admin_template_filter_status') || 'Status'}
            onChange={(value) => setStatusFilter(value)}
            options={[
              { value: 'active', label: t('admin_active') || 'Active' },
              { value: 'inactive', label: t('admin_inactive') || 'Inactive' },
            ]}
            style={{ width: 150 }}
          />
          <Select
            allowClear
            value={scopeFilter}
            placeholder={t('admin_template_filter_scope') || 'Scope'}
            onChange={(value) => setScopeFilter(value)}
            options={[
              { value: 'global', label: t('admin_template_global') || 'Global' },
              { value: 'organization', label: t('visibility_organization') || 'Organization' },
              { value: 'business_line', label: t('visibility_business_line') || 'Business Line' },
            ]}
            style={{ width: 180 }}
          />
          <Select
            allowClear
            showSearch
            value={orgFilter}
            placeholder={t('admin_template_filter_org') || 'Organization'}
            optionFilterProp="label"
            onChange={(value) => {
              setOrgFilter(value);
              setLineFilter(undefined);
            }}
            options={orgs.map((o) => ({ value: o.id, label: o.name }))}
            style={{ width: 200 }}
          />
          <Select
            allowClear
            showSearch
            value={lineFilter}
            placeholder={t('admin_template_filter_line') || 'Business line'}
            optionFilterProp="label"
            onChange={(value) => setLineFilter(value)}
            options={filterScopedLines.map((l) => ({ value: l.id, label: l.name }))}
            style={{ width: 200 }}
          />
          <Button
            onClick={() => {
              setSearchText('');
              setScenarioFilter(undefined);
              setStatusFilter(undefined);
              setScopeFilter(undefined);
              setOrgFilter(undefined);
              setLineFilter(undefined);
            }}
          >
            {t('clear_filters') || 'Clear filters'}
          </Button>
        </Space>
      </Card>

      <Card styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
        <Table rowKey="id" loading={loading} dataSource={templates} columns={columns} pagination={false} size="middle" />
      </Card>

      {/* 1. Modal for space instantiation */}
      <Modal
        title={t('create_space_from_template') || 'Create Space from Template'}
        open={open}
        onOk={handleCreateSpace}
        confirmLoading={instantiating}
        onCancel={() => setOpen(false)}
        okText={t('confirm') || 'Confirm'}
        cancelText={t('cancel') || 'Cancel'}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ paddingTop: 12 }}>
          <Form.Item
            name="name"
            label={t('space_name') || 'Space Name'}
            rules={[{ required: true, message: t('validation_name_required') || 'Please enter space name' }]}
          >
            <Input placeholder={t('space_name_placeholder') || 'Enter space name'} style={{ borderRadius: 8 }} />
          </Form.Item>

          <Form.Item
            name="code"
            label={t('space_code') || 'Space Code'}
            rules={[
              { required: true, message: t('validation_code_required') || 'Please enter space code' },
              { pattern: /^[a-z0-9-]+$/, message: t('validation_code_slug') || 'Slug format: lowercase, digits, and hyphens only' }
            ]}
            extra={t('space_code_hint') || 'Unique identifier used in URLs'}
          >
            <Input placeholder="e.g. audit-tax-season" style={{ borderRadius: 8 }} />
          </Form.Item>

          <Form.Item
            name="organization"
            label={t('service_line_placeholder') || 'Organization'}
          >
            <Select
              onChange={(val) => {
                setSelectedOrgId(val);
                form.setFieldValue('business_line', undefined);
              }}
              options={orgs.map((o) => ({ value: o.id, label: o.name }))}
              style={{ borderRadius: 8 }}
            />
          </Form.Item>

          <Form.Item
            name="business_line"
            label={t('scope_business_line') || 'Business Line'}
          >
            <Select
              allowClear
              placeholder={t('select_business_line_optional') || 'Select Business Line (optional)'}
              options={scopedLines.map((l) => ({ value: l.id, label: l.name }))}
              style={{ borderRadius: 8 }}
            />
          </Form.Item>

          <Form.Item
            name="visibility"
            label={t('space_visibility') || 'Visibility'}
          >
            <Select
              options={[
                { value: 'private', label: t('visibility_private') || 'Private' },
                { value: 'business_line', label: t('visibility_business_line') || 'Business Line' },
                { value: 'organization', label: t('visibility_organization') || 'Organization' },
                { value: 'public_demo', label: t('visibility_public_demo') || 'Public Demo' },
              ]}
              style={{ borderRadius: 8 }}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 2. Modal for creating/editing templates */}
      <Modal
        title={editingTemplate ? (t('admin_edit_template') || 'Edit Template') : (t('admin_create_template') || 'Create Template')}
        open={templateModalOpen}
        onOk={handleSaveTemplate}
        confirmLoading={savingTemplate}
        onCancel={() => setTemplateModalOpen(false)}
        okText={t('confirm') || 'Confirm'}
        cancelText={t('cancel') || 'Cancel'}
        destroyOnClose
        width={620}
      >
        <Form form={templateForm} layout="vertical" style={{ paddingTop: 12 }}>
          <Form.Item
            name="name"
            label={t('space_name') || 'Name'}
            rules={[{ required: true, message: t('validation_name_required') || 'Please enter template name' }]}
          >
            <Input placeholder={t('template_name_placeholder') || 'e.g. Audit Methodology Guide'} style={{ borderRadius: 8 }} />
          </Form.Item>

          <Form.Item
            name="code"
            label={t('space_code') || 'Code'}
            rules={[
              { required: true, message: t('validation_code_required') || 'Please enter template code' },
              { pattern: /^[a-z0-9-]+$/, message: t('validation_code_slug') || 'Slug format: lowercase, digits, and hyphens only' }
            ]}
          >
            <Input placeholder={t('template_code_placeholder') || 'e.g. audit-methodology-guide'} style={{ borderRadius: 8 }} />
          </Form.Item>

          <Form.Item
            name="description"
            label={t('description') || 'Description'}
          >
            <Input.TextArea placeholder={t('enter_description') || 'Enter description'} rows={3} style={{ borderRadius: 8 }} />
          </Form.Item>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Form.Item
              name="scenario_type"
              label={t('kb_type') || 'Type'}
              rules={[{ required: true }]}
            >
              <Select
                options={[
                  { value: 'onboarding', label: 'Onboarding' },
                  { value: 'audit', label: 'Audit' },
                  { value: 'tax', label: 'Tax' },
                  { value: 'consulting', label: 'Consulting' },
                  { value: 'core_services', label: 'Core Business Services' },
                  { value: 'standards_qa', label: 'Standards QA' },
                  { value: 'project_ai', label: 'Project AI' },
                ]}
                style={{ borderRadius: 8 }}
              />
            </Form.Item>

            <Form.Item
              name="default_language"
              label={t('language') || 'Default Language'}
              rules={[{ required: true }]}
            >
              <Select
                options={[
                  { value: 'en', label: 'English' },
                  { value: 'zh', label: 'Chinese' },
                ]}
                style={{ borderRadius: 8 }}
              />
            </Form.Item>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Form.Item
              name="icon"
              label="Icon"
            >
              <Input placeholder="e.g. book, project, user" style={{ borderRadius: 8 }} />
            </Form.Item>

            <Form.Item
              name="default_visibility"
              label={t('space_visibility') || 'Default Visibility'}
              rules={[{ required: true }]}
            >
              <Select
                options={[
                  { value: 'private', label: t('visibility_private') || 'Private' },
                  { value: 'business_line', label: t('visibility_business_line') || 'Business Line' },
                  { value: 'organization', label: t('visibility_organization') || 'Organization' },
                  { value: 'public_demo', label: t('visibility_public_demo') || 'Public Demo' },
                ]}
                style={{ borderRadius: 8 }}
              />
            </Form.Item>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Form.Item
              name="organization"
              label={t('scope_organization') || 'Scope Organization'}
            >
              <Select
                allowClear
                placeholder={t('global_leave_blank') || 'Global (Leave blank)'}
                onChange={(val) => {
                  setTemplateOrgId(val || null);
                  templateForm.setFieldValue('business_line', undefined);
                }}
                options={orgs.map((o) => ({ value: o.id, label: o.name }))}
                style={{ borderRadius: 8 }}
              />
            </Form.Item>

            <Form.Item
              name="business_line"
              label={t('scope_business_line') || 'Scope Business Line'}
            >
              <Select
                allowClear
                placeholder={t('org_shared_leave_blank') || 'Organization Shared (Leave blank)'}
                options={templateScopedLines.map((l) => ({ value: l.id, label: l.name }))}
                style={{ borderRadius: 8 }}
              />
            </Form.Item>
          </div>

          <Form.Item
            name="quick_questions"
            label={t('quick_questions_label') || 'Quick Questions'}
            extra={t('quick_questions_placeholder') || 'Enter one question per line'}
          >
            <Input.TextArea rows={4} placeholder="e.g. How do I get access?&#10;Where is the guide?" style={{ borderRadius: 8 }} />
          </Form.Item>

          <Form.Item
            name="is_active"
            label={t('member_status') || 'Active'}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 3. Modal for application history */}
      <Modal
        title={`${t('admin_template_applications') || 'Template Applications'} - ${selectedAppTemplate?.name || ''}`}
        open={appsModalOpen}
        onCancel={() => setAppsModalOpen(false)}
        footer={null}
        width={750}
        destroyOnClose
      >
        <Table
          rowKey="id"
          loading={appsLoading}
          dataSource={applications}
          pagination={{ pageSize: 8, hideOnSinglePage: true }}
          locale={{ emptyText: t('admin_template_applications_empty') || 'No applications recorded' }}
          size="middle"
          columns={[
            {
              title: t('space') || 'Space',
              key: 'space',
              render: (_: any, app: ScenarioTemplateApplication) => (
                <span>
                  <strong>{app.space_name}</strong> <code style={{ fontSize: 12 }}>({app.space_code})</code>
                </span>
              ),
            },
            {
              title: t('service_line_placeholder') || 'Organization',
              dataIndex: 'organization_name',
              key: 'organization_name',
              render: (val: string | null) => val || '-',
            },
            {
              title: t('scope_business_line') || 'Business Line',
              dataIndex: 'business_line_name',
              key: 'business_line_name',
              render: (val: string | null) => val || '-',
            },
            {
              title: t('created_by') || 'Created By',
              dataIndex: 'created_by_email',
              key: 'created_by_email',
              render: (val: string | null) => val || '-',
            },
            {
              title: t('created_at') || 'Created At',
              dataIndex: 'created_at',
              key: 'created_at',
              render: (val: string) => new Date(val).toLocaleString(),
            },
          ]}
        />
      </Modal>

      {/* 4. Modal for revision history */}
      <Modal
        title={`${t('admin_template_revisions') || 'Template Revisions'} - ${selectedRevTemplate?.name || ''}`}
        open={revisionsModalOpen}
        onCancel={() => setRevisionsModalOpen(false)}
        footer={null}
        width={850}
        destroyOnClose
      >
        <Table
          rowKey="id"
          loading={revisionsLoading}
          dataSource={revisions}
          pagination={{ pageSize: 8, hideOnSinglePage: true }}
          locale={{ emptyText: t('admin_template_revisions_empty') || 'No revisions recorded' }}
          size="middle"
          columns={[
            {
              title: t('admin_template_version') || 'Version',
              dataIndex: 'version',
              key: 'version',
              render: (val: number) => <Tag color="purple">v{val}</Tag>,
            },
            {
              title: t('change_note') || 'Change Note',
              dataIndex: 'change_note',
              key: 'change_note',
              render: (val: string | null) => val || '-',
            },
            {
              title: t('created_by') || 'Created By',
              dataIndex: 'created_by_email',
              key: 'created_by_email',
              render: (val: string | null) => val || '-',
            },
            {
              title: t('created_at') || 'Created At',
              dataIndex: 'created_at',
              key: 'created_at',
              render: (val: string) => new Date(val).toLocaleString(),
            },
            {
              title: t('summary') || 'Summary',
              key: 'summary',
              render: (_: any, rev: ScenarioTemplateRevision) => {
                const snap = rev.snapshot || {};
                const q_count = snap.quick_questions ? snap.quick_questions.length : 0;
                return (
                  <span style={{ fontSize: 13 }}>
                    {snap.name || '-'} / {snap.scenario_type || '-'} (Q: {q_count})
                  </span>
                );
              },
            },
            {
              title: '',
              key: 'actions',
              render: (_: any, rev: ScenarioTemplateRevision) => (
                <Button type="link" size="small" onClick={() => openSnapshotModal(rev)}>
                  {t('view') || 'View'}
                </Button>
              ),
            },
          ]}
        />
      </Modal>

      {/* 5. Sub-modal for Revision Snapshot JSON */}
      <Modal
        title={`${t('admin_template_revision_snapshot') || 'Revision Snapshot'} - v${selectedRevision?.version ?? ''}`}
        open={snapshotModalOpen}
        onCancel={() => setSnapshotModalOpen(false)}
        footer={null}
        width={600}
        destroyOnClose
      >
        <pre style={{
          maxHeight: '400px',
          overflow: 'auto',
          backgroundColor: 'var(--color-bg-container-secondary, #f5f5f5)',
          border: '1px solid var(--color-border-secondary, #e8e8e8)',
          padding: '12px',
          borderRadius: '6px',
          fontSize: 13,
          fontFamily: 'monospace',
        }}>
          {JSON.stringify(selectedRevision?.snapshot, null, 2)}
        </pre>
      </Modal>

      {/* 6. Modal for cloning templates */}
      <Modal
        title={t('admin_clone_template') || 'Clone Template'}
        open={cloneModalOpen}
        onOk={handleCloneTemplate}
        confirmLoading={cloning}
        onCancel={() => setCloneModalOpen(false)}
        okText={t('confirm') || 'Confirm'}
        cancelText={t('cancel') || 'Cancel'}
        destroyOnClose
      >
        <Form form={cloneForm} layout="vertical" style={{ paddingTop: 12 }}>
          <Form.Item
            name="name"
            label={t('space_name') || 'Name'}
            rules={[{ required: true, message: t('validation_name_required') || 'Please enter template name' }]}
          >
            <Input placeholder={t('template_name_placeholder') || 'e.g. Audit Methodology Guide Copy'} style={{ borderRadius: 8 }} />
          </Form.Item>

          <Form.Item
            name="code"
            label={t('space_code') || 'Code'}
            rules={[
              { required: true, message: t('validation_code_required') || 'Please enter template code' },
              { pattern: /^[a-z0-9-]+$/, message: t('validation_code_slug') || 'Slug format: lowercase, digits, and hyphens only' }
            ]}
          >
            <Input placeholder={t('template_code_placeholder') || 'e.g. audit-methodology-guide-copy'} style={{ borderRadius: 8 }} />
          </Form.Item>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Form.Item
              name="organization"
              label={t('scope_organization') || 'Scope Organization'}
            >
              <Select
                allowClear
                placeholder={t('global_leave_blank') || 'Global (Leave blank)'}
                onChange={(val) => {
                  setCloneOrgId(val || null);
                  cloneForm.setFieldValue('business_line', undefined);
                }}
                options={orgs.map((o) => ({ value: o.id, label: o.name }))}
                style={{ borderRadius: 8 }}
              />
            </Form.Item>

            <Form.Item
              name="business_line"
              label={t('scope_business_line') || 'Scope Business Line'}
            >
              <Select
                allowClear
                placeholder={t('org_shared_leave_blank') || 'Organization Shared (Leave blank)'}
                options={cloneScopedLines.map((l) => ({ value: l.id, label: l.name }))}
                style={{ borderRadius: 8 }}
              />
            </Form.Item>
          </div>

          <Form.Item
            name="is_active"
            label={t('member_status') || 'Active'}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
