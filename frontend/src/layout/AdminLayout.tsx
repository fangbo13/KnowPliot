/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 AdminLayout — a dedicated admin console shell, separate from the
// employee app. Only admins (super / org / business) may enter; everyone else
// is redirected back to the chat app. Server-side checks still gate every API.

import { NavLink, Outlet, useNavigate, Navigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  DashboardOutlined, TeamOutlined, SafetyCertificateOutlined, SoundOutlined,
  ApartmentOutlined, AuditOutlined, DatabaseOutlined, ArrowLeftOutlined,
  GlobalOutlined, SunOutlined, MoonOutlined, LayoutOutlined, MessageOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthProvider';
import { useAuthorization } from '../auth/CapabilityProvider';
import { useTheme } from '../hooks/useTheme';
import NotificationBell from '../components/NotificationBell';
import { designTokens } from '../design/tokens';
import ResponsiveWorkbenchShell from './ResponsiveWorkbenchShell';

const PAGE_TRANSITION_SECONDS = designTokens.motion.duration.base / 1000;

const NAV = [
  { to: '/admin/dashboard', icon: <DashboardOutlined />, key: 'admin_nav_dashboard' },
  { to: '/admin/users', icon: <TeamOutlined />, key: 'admin_nav_users' },
  { to: '/admin/codes', icon: <SafetyCertificateOutlined />, key: 'admin_nav_codes' },
  { to: '/admin/announcements', icon: <SoundOutlined />, key: 'admin_nav_announcements' },
  { to: '/admin/business-lines', icon: <ApartmentOutlined />, key: 'admin_nav_business_lines' },
  { to: '/admin/templates', icon: <LayoutOutlined />, key: 'admin_nav_templates' },
  { to: '/admin/quality', icon: <MessageOutlined />, key: 'admin_nav_quality' },
  { to: '/admin/audit', icon: <AuditOutlined />, key: 'admin_nav_audit' },
  { to: '/admin/knowledge', icon: <DatabaseOutlined />, key: 'admin_nav_knowledge' },
];

function initials(email?: string) {
  if (!email) return '?';
  return email.slice(0, 2).toUpperCase();
}

export default function AdminLayout() {
  const { t, i18n } = useTranslation('common');
  const { user } = useAuth();
  const access = useAuthorization();
  const navigate = useNavigate();
  const location = useLocation();
  const { effective, setThemeMode } = useTheme();
  const isDark = effective === 'dark';
  const activeNav = NAV.find((item) => location.pathname === item.to || location.pathname.startsWith(`${item.to}/`));
  const activeTitle = activeNav ? t(activeNav.key) : t('admin_console');

  // Gate: only admins enter the console.
  if (!access.hasAny(['platform.access', 'governance.access'])) {
    return <Navigate to="/chat" replace />;
  }

  const toggleLanguage = () => {
    const next = i18n.language.startsWith('zh') ? 'en' : 'zh';
    i18n.changeLanguage(next);
    localStorage.setItem('ey-language', next);
  };

  return (
    <ResponsiveWorkbenchShell
      variant="admin"
      routeKey={location.pathname}
      navigationLabel={`${t('admin_console')} navigation`}
      menuLabel={t('mobile_menu') || 'Open mobile menu'}
      closeLabel={t('close') || 'Close'}
      sidebar={(
        <>
        <div className="kp-admin-brand" style={{ padding: '20px 20px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            width: 34, height: 34, borderRadius: 10, background: 'var(--gradient-accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--color-text-on-accent)', fontFamily: 'var(--font-family-display)', fontWeight: 600, fontSize: 18,
          }}>K</span>
          <span style={{ fontFamily: "'Fraunces', serif", fontWeight: 500, fontSize: 16 }}>
            {t('admin_console')}
          </span>
        </div>

        <nav className="kp-admin-nav" style={{ flex: 1, padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className="admin-nav-link"
              style={({ isActive }) => ({
                position: 'relative',
                display: 'flex', alignItems: 'center', gap: 11, padding: '10px 12px',
                borderRadius: 10, fontSize: 14, textDecoration: 'none',
                fontWeight: isActive ? 600 : 500,
                color: isActive ? 'var(--accent-text)' : 'var(--color-text-secondary)',
                background: isActive ? 'var(--accent-soft)' : undefined,
                transition: 'background var(--dur) var(--ease-out), color var(--dur) var(--ease-out)',
              })}
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <div style={{
                      position: 'absolute', left: -12, top: '50%', transform: 'translateY(-50%)',
                      width: 3, height: 18, borderRadius: '0 3px 3px 0', background: 'var(--accent)'
                    }} />
                  )}
                  <span style={{ fontSize: 16, display: 'inline-flex' }}>{item.icon}</span>
                  {t(item.key)}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <button
          className="icon-btn kp-admin-back"
          onClick={() => navigate('/chat')}
          style={{
            margin: 12, width: 'auto', gap: 10, padding: '10px 12px', justifyContent: 'flex-start',
            borderRadius: 10, color: 'var(--color-text-secondary)', fontSize: 14, fontWeight: 500,
          }}
        >
          <ArrowLeftOutlined /> {t('back_to_app')}
        </button>
        </>
      )}
      topbar={(
        <>
          <div className="kp-admin-topbar__context">
            <span>{t('admin_label', { defaultValue: 'ADMIN CONSOLE' })}</span>
            <strong>{activeTitle}</strong>
          </div>
          <NotificationBell />
          <button className="icon-btn" onClick={() => setThemeMode(isDark ? 'light' : 'dark')} aria-label={isDark ? t('switch_to_light') : t('switch_to_dark')} title={isDark ? t('switch_to_light') : t('switch_to_dark')}>
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
        </>
      )}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: PAGE_TRANSITION_SECONDS, ease: [0.25, 0.8, 0.25, 1] }}
          className="kp-admin-route"
        >
          <Outlet />
        </motion.div>
      </AnimatePresence>
    </ResponsiveWorkbenchShell>
  );
}
