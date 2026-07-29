/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Console Entry Hub spec §2.2: single management entry point. Renders a
// Claude settings-hub style card grid whose cards and quick links are
// resolved purely from the capability snapshot — no new backend contract.

import {
  ApartmentOutlined, AppstoreOutlined, BookOutlined, RightOutlined, TeamOutlined,
} from '@ant-design/icons';
import { useMemo, useState } from 'react';
import { Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { Capability } from '../../api/capabilities';
import type { SpaceRole } from '../../api/spaces';
import { ForbiddenPage } from '../../auth/CapabilityGate';
import { useAuthorization } from '../../auth/CapabilityProvider';
import { PageHeader, Surface } from '../../design/primitives';
import { useSpaceStore } from '../../store/spaceStore';

interface QuickLink {
  labelKey: string;
  to: string;
  capability: Capability;
}

const VISIBLE_SPACES_COLLAPSED = 5;

// Roles that carry workspace-management responsibility (final access is still
// gated by WorkspaceCapabilityBoundary + CapabilityGate on the target route).
const MANAGING_ROLES: ReadonlySet<SpaceRole> = new Set([
  'super_admin', 'org_admin', 'business_admin', 'owner', 'knowledge_admin',
]);

export default function ConsoleHubPage() {
  const { t } = useTranslation('common');
  const access = useAuthorization();
  const spaces = useSpaceStore((state) => state.spaces);
  const activeSpaceId = useSpaceStore((state) => state.activeSpaceId);
  const [showAllSpaces, setShowAllSpaces] = useState(false);

  // Spec §2.3: spaces I can manage — managing role, plus the capability
  // scope check as a belt-and-braces filter.
  const manageableSpaces = useMemo(() => {
    const scopedIds = access.snapshot?.scopes.space_ids ?? [];
    return spaces.filter(
      (space) => space.my_role != null
        && MANAGING_ROLES.has(space.my_role)
        && scopedIds.includes(space.id),
    );
  }, [access.snapshot, spaces]);

  const showPlatform = access.has('platform.access');
  const showGovernance = access.has('governance.access');
  const showWorkspace = manageableSpaces.length > 0;
  const showKnowledge = Boolean(activeSpaceId) && access.has('knowledge.manage');

  if (access.status === 'loading') {
    return (
      <div className="page section-enter" role="status" style={{ color: 'var(--color-text-secondary)' }}>
        {t('loading')}
      </div>
    );
  }
  if (!showPlatform && !showGovernance && !showWorkspace && !showKnowledge) {
    return <ForbiddenPage />;
  }

  const renderQuickLinks = (links: QuickLink[]) => {
    const visible = links.filter((link) => access.has(link.capability));
    if (!visible.length) return null;
    return (
      <div className="kp-hub-card__links">
        {visible.map((link) => (
          <Link key={link.to} className="kp-hub-chip" to={link.to}>
            {t(link.labelKey)}
          </Link>
        ))}
      </div>
    );
  };

  const renderCardHeader = (icon: React.ReactNode, titleKey: string, to?: string) => (
    <div className="kp-hub-card__head">
      <span className="kp-hub-card__badge" aria-hidden="true">{icon}</span>
      <h2 className="kp-hub-card__title">{t(titleKey)}</h2>
      {to && (
        <Link className="kp-hub-card__enter" to={to}>
          {t('console_hub_enter')} <RightOutlined />
        </Link>
      )}
    </div>
  );

  const visibleSpaces = showAllSpaces
    ? manageableSpaces
    : manageableSpaces.slice(0, VISIBLE_SPACES_COLLAPSED);

  return (
    <div className="page section-enter">
      <PageHeader title={t('console_hub_title')} description={t('console_hub_subtitle')} />
      <div className="kp-hub-grid">
        {showPlatform && (
          <Surface as="section" className="kp-hub-card">
            {renderCardHeader(<AppstoreOutlined />, 'console_title_platform', '/platform-admin')}
            <p className="kp-hub-card__desc">{t('console_hub_card_platform_desc')}</p>
            {renderQuickLinks([
              { labelKey: 'console_nav_users', to: '/platform-admin/users', capability: 'platform.users.manage' },
              { labelKey: 'console_nav_workspaces', to: '/platform-admin/spaces', capability: 'platform.access' },
              { labelKey: 'console_nav_audit', to: '/platform-admin/audit', capability: 'platform.audit.read' },
              { labelKey: 'console_nav_models', to: '/platform-admin/model', capability: 'platform.models.manage' },
            ])}
          </Surface>
        )}

        {showGovernance && (
          <Surface as="section" className="kp-hub-card">
            {renderCardHeader(<ApartmentOutlined />, 'console_title_governance', '/governance')}
            <p className="kp-hub-card__desc">{t('console_hub_card_governance_desc')}</p>
            {renderQuickLinks([
              { labelKey: 'console_nav_users', to: '/governance/users', capability: 'governance.users.manage' },
              { labelKey: 'console_nav_business_lines', to: '/governance/business-lines', capability: 'governance.business_lines.manage' },
              { labelKey: 'console_nav_templates', to: '/governance/templates', capability: 'governance.templates.manage' },
              { labelKey: 'console_nav_audit', to: '/governance/audit', capability: 'governance.audit.read' },
            ])}
          </Surface>
        )}

        {showWorkspace && (
          <Surface as="section" className="kp-hub-card">
            {renderCardHeader(<TeamOutlined />, 'console_title_workspace')}
            <p className="kp-hub-card__desc">{t('console_hub_card_workspace_desc')}</p>
            <div className="kp-hub-card__spaces" aria-label={t('console_hub_my_spaces')}>
              {visibleSpaces.map((space) => (
                <div key={space.id} className="kp-hub-space-row">
                  <span className="kp-hub-space-row__name">{space.name}</span>
                  <Tag>{space.my_role}</Tag>
                  <Link className="kp-hub-space-row__manage" to={`/workspace/${space.id}/manage`}>
                    {t('console_hub_manage')} <RightOutlined />
                  </Link>
                </div>
              ))}
              {manageableSpaces.length > VISIBLE_SPACES_COLLAPSED && !showAllSpaces && (
                <button type="button" className="kp-hub-chip" onClick={() => setShowAllSpaces(true)}>
                  {t('console_hub_view_all')} ({manageableSpaces.length})
                </button>
              )}
            </div>
          </Surface>
        )}

        {showKnowledge && (
          <Surface as="section" className="kp-hub-card">
            {renderCardHeader(<BookOutlined />, 'knowledge_base', `/workspace/${activeSpaceId}/knowledge`)}
            <p className="kp-hub-card__desc">{t('console_hub_card_knowledge_desc')}</p>
          </Surface>
        )}
      </div>
    </div>
  );
}
