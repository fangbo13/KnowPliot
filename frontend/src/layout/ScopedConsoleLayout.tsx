/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Dark/i18n/Layout spec §B1/§C: the console shell is now fully i18n-driven and
// carries the same Claude-style top bar as AdminLayout (notifications, theme
// toggle, language toggle, user pill) — previously the console had no way to
// switch theme or language at all.

import {
  DownOutlined, GlobalOutlined, HomeOutlined, MoonOutlined, SunOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Link, NavLink, Outlet, useParams } from 'react-router-dom';

import { useAuth } from '../auth/AuthProvider';
import { useAuthorization } from '../auth/CapabilityProvider';
import NotificationBell from '../components/NotificationBell';
import { useTheme } from '../hooks/useTheme';
import { useSpaceStore } from '../store/spaceStore';
import {
  type ConsoleKind,
  visibleConsoleNavigation,
} from './consoleNavigation';

const TITLE_KEYS: Record<ConsoleKind, string> = {
  platform: 'console_title_platform',
  governance: 'console_title_governance',
  workspace: 'console_title_workspace',
};

function initials(email?: string) {
  if (!email) return '?';
  return email.slice(0, 2).toUpperCase();
}

export default function ScopedConsoleLayout({ kind }: { kind: ConsoleKind }) {
  const { t, i18n } = useTranslation('common');
  const { user } = useAuth();
  const access = useAuthorization();
  const { effective, setThemeMode } = useTheme();
  const isDark = effective === 'dark';
  const { spaceId } = useParams<{ spaceId: string }>();
  const basePath = kind === 'workspace'
    ? `/workspace/${spaceId ?? ''}/manage`
    : kind === 'platform'
      ? '/platform-admin'
      : '/governance';
  const navigation = visibleConsoleNavigation(kind, access, basePath);
  const title = t(TITLE_KEYS[kind]);
  const activeSpaceId = useSpaceStore((state) => state.activeSpaceId);

  // Console Entry Hub spec §2.4: cross-console switcher targets, filtered by
  // capability and excluding the console currently shown.
  const switchTargets: Array<{ key: string; label: string; to: string }> = [];
  if (kind !== 'platform' && access.has('platform.access')) {
    switchTargets.push({ key: 'platform', label: t('console_title_platform'), to: '/platform-admin' });
  }
  if (kind !== 'governance' && access.has('governance.access')) {
    switchTargets.push({ key: 'governance', label: t('console_title_governance'), to: '/governance' });
  }
  if (kind !== 'workspace' && activeSpaceId && access.has('workspace.manage')) {
    switchTargets.push({ key: 'workspace', label: t('console_title_workspace'), to: `/workspace/${activeSpaceId}/manage` });
  }

  const toggleLanguage = () => {
    const next = i18n.language.startsWith('zh') ? 'en' : 'zh';
    i18n.changeLanguage(next);
    localStorage.setItem('ey-language', next);
  };

  return (
    <div className="kp-console-layout">
      <aside className="kp-console-sidebar">
        <div className="kp-console-brand">
          <details className="kp-console-switcher">
            <summary aria-label={t('console_switcher_aria')}>
              <span
                aria-hidden="true"
                style={{
                  width: 30, height: 30, borderRadius: 9, flexShrink: 0,
                  background: 'var(--gradient-accent)', color: 'var(--color-text-on-accent)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: 'var(--font-family-display)', fontWeight: 600, fontSize: 16,
                }}
              >
                K
              </span>
              <span className="kp-console-title">{title}</span>
              <DownOutlined className="kp-console-switcher__caret" />
            </summary>
            <div className="kp-console-switcher__pop">
              <Link className="kp-console-switcher__item" to="/console">
                <HomeOutlined /> {t('management_hub')}
              </Link>
              {switchTargets.map((target) => (
                <Link key={target.key} className="kp-console-switcher__item" to={target.to}>
                  {target.label}
                </Link>
              ))}
            </div>
          </details>
          <div className="kp-console-scope">
            {t('console_scope_hint')}
          </div>
        </div>

        <nav aria-label={`${title} navigation`} className="kp-console-nav">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `kp-console-nav__item${isActive ? ' is-active' : ''}`}
            >
              {t(item.labelKey, item.label)}
            </NavLink>
          ))}
        </nav>

        <div className="kp-console-sidebar__spacer" />
        <Link to="/console" className="kp-console-back">
          <HomeOutlined /> {t('management_hub')}
        </Link>
        <Link to="/chat" className="kp-console-back">
          {t('back_to_app')}
        </Link>
      </aside>

      <main className="kp-console-main">
        <header className="kp-console-topbar">
          <NotificationBell />
          <button
            className="icon-btn"
            onClick={() => setThemeMode(isDark ? 'light' : 'dark')}
            aria-label={isDark ? t('switch_to_light') : t('switch_to_dark')}
            title={isDark ? t('switch_to_light') : t('switch_to_dark')}
          >
            {isDark ? <SunOutlined /> : <MoonOutlined />}
          </button>
          <button className="icon-btn" onClick={toggleLanguage} aria-label={t('language_switch') || 'Switch language'}>
            <GlobalOutlined />
          </button>
          <button
            className="icon-btn"
            style={{ width: 'auto', gap: 8, padding: '2px 12px 2px 4px', borderRadius: 999, border: '1px solid var(--color-border-secondary)', marginLeft: 6 }}
            aria-label={t('user_menu') || 'User'}
          >
            <span className="sidebar-avatar" style={{ width: 26, height: 26, fontSize: 12, background: 'var(--gradient-accent)', color: 'var(--color-text-on-accent)' }}>{initials(user?.email)}</span>
            <span style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13, color: 'var(--color-text-secondary)' }}>{user?.email}</span>
          </button>
        </header>
        <div className="kp-console-content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
