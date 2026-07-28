/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin console — users & global roles (reuses rbac endpoints).
import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { Alert, Card, Divider, Modal, Table, Button, Tag, Select, Space, Popconfirm, Input, message as antdMessage } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { adminApi, type AdminUser, type OffboardingImpact } from '../../api/admin';
import { spacesApi, type OwnershipCandidate } from '../../api/spaces';
import { useAuthorization } from '../../auth/CapabilityProvider';
import { getRateLimitDetails, isAbortError, withRequestSignal } from '../../api/client';

type AdminScope = { organization_id: string; business_line_id: string | null; role: string };
const adminScopeKey = (scope: AdminScope) => `${scope.organization_id}:${scope.business_line_id ?? 'organization'}:${scope.role}`;
const platformAdminScopeKey = 'platform:admin';

export default function AdminUsersPage() {
  const { t } = useTranslation('common');
  const access = useAuthorization();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [offboardingUser, setOffboardingUser] = useState<AdminUser | null>(null);
  const [impact, setImpact] = useState<OffboardingImpact | null>(null);
  const [candidates, setCandidates] = useState<Record<string, OwnershipCandidate[]>>({});
  const [successors, setSuccessors] = useState<Record<string, string>>({});
  const [adminCandidates, setAdminCandidates] = useState<Record<string, Array<{ id: string; display_name: string }>>>({});
  const [adminSuccessors, setAdminSuccessors] = useState<Record<string, string>>({});
  const [impactLoading, setImpactLoading] = useState(false);
  const [offboarding, setOffboarding] = useState(false);
  const [loadError, setLoadError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);

  // Filter state
  const [roleFilter, setRoleFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [emailSearch, setEmailSearch] = useState('');
  const sequenceRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const canOffboard = access.has('platform.users.offboard');

  const refresh = useCallback(async () => {
    const sequence = ++sequenceRef.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    setLoading(true);
    controllerRef.current = controller;
    setLoadError(null);
    try {
      const nextUsers = await withRequestSignal(controller.signal, () => adminApi.users());
      if (controller.signal.aborted || sequence !== sequenceRef.current) return;
      setUsers(nextUsers);
    } catch (error: unknown) {
      if (isAbortError(error) || controller.signal.aborted || sequence !== sequenceRef.current) return;
      const rateLimit = getRateLimitDetails(error);
      setLoadError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    } finally {
      if (sequence === sequenceRef.current && !controller.signal.aborted) setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
    return () => {
      sequenceRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [refresh]);

  const assignRole = async (userId: string, roleName: string) => {
    try { await adminApi.assignRole(userId, roleName); await refresh(); antdMessage.success(t('member_role_updated') || 'Role assigned'); }
    catch { antdMessage.error(t('member_update_failed') || 'Failed'); }
  };

  const deactivate = async (userId: string) => {
    try { await adminApi.deactivateUser(userId); await refresh(); antdMessage.success(t('admin_deactivate_success') || 'User deactivated'); }
    catch { antdMessage.error(t('member_update_failed') || 'Failed'); }
  };

  const openOffboarding = async (user: AdminUser) => {
    setOffboardingUser(user);
    setImpact(null);
    setCandidates({});
    setSuccessors({});
    setAdminCandidates({});
    setAdminSuccessors({});
    setImpactLoading(true);
    try {
      const nextImpact = await adminApi.offboardingImpact(user.id);
      const candidateRows = await Promise.all(
        nextImpact.blockers.owned_space_details.map(async (space) => [
          space.id,
          await spacesApi.ownershipCandidates(space.id, '', 'forced'),
        ] as const),
      );
      const adminScopes = [
        ...nextImpact.blockers.last_organization_admin_scopes,
        ...nextImpact.blockers.last_business_admin_scopes,
      ];
      const adminCandidateRows = await Promise.all(
        adminScopes.map(async (scope) => [
          adminScopeKey(scope),
          await adminApi.offboardingAdminSuccessorCandidates(user.id, scope),
        ] as const),
      );
      if (nextImpact.blockers.last_platform_admin) {
        adminCandidateRows.push([
          platformAdminScopeKey,
          await adminApi.offboardingAdminSuccessorCandidates(user.id, { scope_type: 'platform', role: 'admin' }),
        ]);
      }
      setImpact(nextImpact);
      setCandidates(Object.fromEntries(candidateRows));
      setAdminCandidates(Object.fromEntries(adminCandidateRows));
    } catch {
      antdMessage.error(t('offboarding_impact_failed'));
    } finally {
      setImpactLoading(false);
    }
  };

  const refreshImpact = async () => {
    if (!offboardingUser) return;
    const previousSuccessors = successors;
    const previousAdminSuccessors = adminSuccessors;
    setImpactLoading(true);
    try {
      const nextImpact = await adminApi.offboardingImpact(offboardingUser.id);
      setImpact(nextImpact);
      setSuccessors(Object.fromEntries(
        Object.entries(previousSuccessors).filter(([spaceId]) =>
          nextImpact.blockers.owned_spaces.includes(spaceId),
        ),
      ));
      const nextScopes = [
        ...nextImpact.blockers.last_organization_admin_scopes,
        ...nextImpact.blockers.last_business_admin_scopes,
      ];
      setAdminSuccessors(Object.fromEntries(
        Object.entries(previousAdminSuccessors).filter(([scopeKey]) =>
          nextScopes.some((scope) => adminScopeKey(scope) === scopeKey),
        ),
      ));
    } finally {
      setImpactLoading(false);
    }
  };

  const submitOffboarding = async () => {
    if (!offboardingUser || !impact) return;
    setOffboarding(true);
    try {
      await adminApi.offboardUser(offboardingUser.id, {
        impact_version: impact.impact_version,
        reason_code: 'employment_ended',
        space_transfers: impact.blockers.owned_space_details.map((space) => ({
          space_id: space.id,
          successor_user_id: successors[space.id],
          expected_ownership_version: space.ownership_version,
        })),
        admin_successions: [
          ...impact.blockers.last_organization_admin_scopes,
          ...impact.blockers.last_business_admin_scopes,
        ].map((scope) => ({
          ...scope,
          successor_user_id: adminSuccessors[adminScopeKey(scope)],
        })),
        ...(impact.blockers.last_platform_admin ? [{
          scope_type: 'platform' as const,
          role: 'admin',
          successor_user_id: adminSuccessors[platformAdminScopeKey],
        }] : []),
      });
      antdMessage.success(t('offboarding_success'));
      setOffboardingUser(null);
      await refresh();
    } catch (error: any) {
      if (error?.response?.data?.error_code === 'offboarding_impact_changed') {
        antdMessage.warning(t('offboarding_impact_changed'));
        await refreshImpact();
      } else {
        antdMessage.error(t('offboarding_failed'));
      }
    } finally {
      setOffboarding(false);
    }
  };

  const adminScopes = impact ? [
    ...impact.blockers.last_organization_admin_scopes,
    ...impact.blockers.last_business_admin_scopes,
  ] : [];
  const hasAdminBlocker = Boolean(impact?.blockers.last_platform_admin || adminScopes.length);
  const hasUnmappedAdmin = Boolean(
    (impact?.blockers.last_platform_admin && !adminSuccessors[platformAdminScopeKey]) ||
    adminScopes.some((scope) => !adminSuccessors[adminScopeKey(scope)]),
  );
  const hasUnmappedOwner = Boolean(
    impact?.blockers.owned_spaces.some((spaceId) => !successors[spaceId]),
  );

  const activate = async (userId: string) => {
    try { await adminApi.activateUser(userId); await refresh(); antdMessage.success(t('admin_activate_success') || 'User activated'); }
    catch { antdMessage.error(t('member_update_failed') || 'Failed'); }
  };

  const roleOptions = useMemo(() => {
    const roles = new Set<string>();
    users.forEach((u) => { u.roles.forEach((r) => roles.add(r)); if (u.is_hr_admin) roles.add('hr'); });
    if (!roles.has('employee')) roles.add('employee');
    return [...roles].sort().map((r) => ({ value: r, label: r }));
  }, [users]);

  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      if (roleFilter) {
        const effectiveRoles = [...user.roles];
        if (user.is_hr_admin && !effectiveRoles.includes('hr')) effectiveRoles.push('hr');
        if (roleFilter === 'employee') {
          if (effectiveRoles.length > 0) return false;
        } else {
          if (!effectiveRoles.includes(roleFilter)) return false;
        }
      }
      if (statusFilter && (user.is_active ? 'active' : 'inactive') !== statusFilter) return false;
      if (emailSearch && !user.email.toLowerCase().includes(emailSearch.toLowerCase())) return false;
      return true;
    });
  }, [users, roleFilter, statusFilter, emailSearch]);

  const columns = [
    { title: t('email_label') || 'Email', dataIndex: 'email', key: 'email', ellipsis: true },
    { title: t('service_line_label'), dataIndex: 'service_line', key: 'service_line', render: (v: string | null) => v || '-' },
    {
      title: t('member_role') || 'Roles', dataIndex: 'roles', key: 'roles',
      render: (roles: string[], rec: AdminUser) => {
        const all = [...roles];
        if (rec.is_hr_admin && !all.includes('hr')) all.push('hr');
        return all.length ? all.map((r) => <Tag key={r} color={r === 'admin' ? 'red' : r === 'hr' ? 'blue' : 'default'}>{r}</Tag>) : <Tag>employee</Tag>;
      },
    },
    {
      title: t('kb_status') || 'Status', dataIndex: 'is_active', key: 'is_active',
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? t('admin_active') : t('admin_inactive')}</Tag>,
    },
    {
      title: t('admin_role_assign'), key: 'assign',
      render: (_: any, rec: AdminUser) => (
        <Space>
          <Select<string>
            size="small" placeholder={t('admin_role_assign')} style={{ width: 120 }}
            value={undefined}
            onChange={(v) => assignRole(rec.id, v)}
            options={[{ value: 'admin', label: 'admin' }, { value: 'hr', label: 'hr' }]}
          />
          {!rec.is_active && (
            <Button type="link" size="small" onClick={() => activate(rec.id)}>{t('admin_activate')}</Button>
          )}
          {rec.is_active && (
            canOffboard ? (
              <Button type="link" danger size="small" onClick={() => void openOffboarding(rec)}>{t('offboard')}</Button>
            ) : (
              <Popconfirm title={`${t('admin_deactivate')}?`} onConfirm={() => deactivate(rec.id)}>
                <Button type="link" danger size="small">{t('admin_deactivate')}</Button>
              </Popconfirm>
            )
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className="page">
      <div className="page-inner">
        <div className="page-head" style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 className="page-title">{t('admin_users_title')}</h1>
            <p className="page-sub">{t('admin_users_subtitle')}</p>
          </div>
          <Button icon={<ReloadOutlined />} onClick={refresh} style={{ borderRadius: 8 }} />
        </div>
        <Card className="glass-panel section-enter" styles={{ body: { padding: 20 } }} style={{ borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border-secondary)', boxShadow: 'var(--shadow-sm)' }}>
          {loadError && (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 16 }}
              message={loadError.code === 'rate_limited'
                ? `${t('rate_limited') || 'Too many requests'}${loadError.retryAfterSeconds == null ? '' : ` — ${t('retry_after_seconds', { seconds: loadError.retryAfterSeconds })}`}`
                : t('load_error')}
              action={<Button onClick={() => void refresh()}>{t('error_retry')}</Button>}
            />
          )}
          <Space wrap style={{ marginBottom: 16 }}>
            <Input.Search
              placeholder={t('email_label') || 'Search email'}
              value={emailSearch}
              onChange={(e) => setEmailSearch(e.target.value)}
              allowClear
              style={{ width: 200 }}
            />
            <Select
              showSearch
              allowClear
              placeholder={t('filter_role')}
              value={roleFilter}
              onChange={(value) => setRoleFilter(value ?? undefined)}
              options={roleOptions}
              optionFilterProp="label"
              style={{ width: 160 }}
            />
            <Select
              allowClear
              placeholder={t('filter_status')}
              value={statusFilter}
              onChange={(value) => setStatusFilter(value ?? undefined)}
              options={[
                { value: 'active', label: t('status_active') },
                { value: 'inactive', label: t('status_inactive') },
              ]}
              style={{ width: 120 }}
            />
          </Space>
          <Table rowKey="id" loading={loading} dataSource={filteredUsers} columns={columns} pagination={{ pageSize: 12 }} size="middle" scroll={{ x: 'max-content' }} />
        </Card>
        <Modal
          title={offboardingUser ? `${t('offboard')} ${offboardingUser.email}` : t('offboard_account')}
          open={Boolean(offboardingUser)}
          onCancel={() => setOffboardingUser(null)}
          confirmLoading={offboarding}
          okText={t('offboarding_confirm')}
          okButtonProps={{ danger: true, disabled: !impact || impactLoading || hasUnmappedAdmin || hasUnmappedOwner }}
          onOk={() => void submitOffboarding()}
          width={680}
          destroyOnClose
        >
          {impactLoading && <Alert type="info" showIcon message={t('offboarding_impact_loading')} />}
          {impact && (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              {hasAdminBlocker && (
                <Alert
                  type={hasUnmappedAdmin ? 'error' : 'info'}
                  showIcon
                  message={t('offboarding_admin_blocker')}
                />
              )}
              {impact.blockers.last_platform_admin && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <strong>{`admin - ${t('offboarding_platform_scope')}`}</strong>
                  <Select
                    aria-label={t('admin_successor_aria')}
                    value={adminSuccessors[platformAdminScopeKey]}
                    placeholder={t('offboarding_select_successor')}
                    options={(adminCandidates[platformAdminScopeKey] ?? []).map((candidate) => ({ value: candidate.id, label: candidate.display_name }))}
                    onChange={(userId) => setAdminSuccessors((current) => ({ ...current, [platformAdminScopeKey]: userId }))}
                  />
                </div>
              )}
              {adminScopes.map((scope) => {
                const key = adminScopeKey(scope);
                const scopeLabel = scope.business_line_id
                  ? `${scope.role} - ${t('offboarding_business_scope')}`
                  : `${scope.role} - ${t('offboarding_organization_scope')}`;
                return (
                  <div key={key} style={{ display: 'grid', gap: 8 }}>
                    <strong>{scopeLabel}</strong>
                    <Select
                      aria-label={`Administrator successor for ${scopeLabel}`}
                      value={adminSuccessors[key]}
                      placeholder={t('offboarding_select_successor')}
                      options={(adminCandidates[key] ?? []).map((candidate) => ({ value: candidate.id, label: candidate.display_name }))}
                      onChange={(userId) => setAdminSuccessors((current) => ({ ...current, [key]: userId }))}
                    />
                  </div>
                );
              })}
              {adminScopes.length > 0 && <Divider style={{ margin: '4px 0' }} />}
              {impact.blockers.owned_space_details.map((space) => (
                <div key={space.id} style={{ display: 'grid', gap: 8 }}>
                  <strong>{space.display_name}</strong>
                  <Select
                    aria-label={`Successor for ${space.display_name}`}
                    value={successors[space.id]}
                    placeholder={t('offboarding_select_successor')}
                    options={(candidates[space.id] ?? []).map((candidate) => ({ value: candidate.id, label: candidate.display_name }))}
                    onChange={(userId) => setSuccessors((current) => ({ ...current, [space.id]: userId }))}
                  />
                </div>
              ))}
              {impact.blockers.owned_space_details.length > 0 && <Divider style={{ margin: '4px 0' }} />}
              <Alert
                type="warning"
                showIcon
                message={t('offboarding_retention_notice')}
              />
            </Space>
          )}
        </Modal>
      </div>
    </div>
  );
}
