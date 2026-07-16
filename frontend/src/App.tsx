/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect } from 'react';
import { Navigate, Route, Routes, useParams } from 'react-router-dom';

import { CapabilityGate, LegacyAdminRedirect } from './auth/CapabilityGate';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { useAuth } from './auth/AuthProvider';
import { WorkspaceCapabilityBoundary } from './auth/WorkspaceCapabilityBoundary';
import { CAPABILITY_NAV_ENABLED } from './auth/authorization';
import ErrorBoundary from './components/ErrorBoundary';
import i18n from './i18n';
import AdminLayout from './layout/AdminLayout';
import AppLayout from './layout/AppLayout';
import ScopedConsoleLayout from './layout/ScopedConsoleLayout';
import LoginPage from './auth/LoginPage';
import ResetPasswordPage from './auth/ResetPasswordPage';
import ChatPage from './pages/ChatPage';
import HistoryPage from './pages/HistoryPage';
import ProfilePage from './pages/ProfilePage';
import SpaceManagementPage from './pages/SpaceManagementPage';
import AdminAnnouncementsPage from './pages/admin/AdminAnnouncementsPage';
import AdminAuditPage from './pages/admin/AdminAuditPage';
import AdminBusinessLinesPage from './pages/admin/AdminBusinessLinesPage';
import AdminCodesPage from './pages/admin/AdminCodesPage';
import AdminDashboardPage from './pages/admin/AdminDashboardPage';
import AdminQualityPage from './pages/admin/AdminQualityPage';
import AdminTemplatesPage from './pages/admin/AdminTemplatesPage';
import AdminUsersPage from './pages/admin/AdminUsersPage';
import KnowledgeBasePage from './pages/admin/KnowledgeBasePage';
import AccessRequestsPage from './pages/console/AccessRequestsPage';
import ConsoleOverviewPage from './pages/console/ConsoleOverviewPage';
import ConsolePlaceholderPage from './pages/console/ConsolePlaceholderPage';
import ScopedAuditPage from './pages/console/ScopedAuditPage';
import ScopedMetricsPage from './pages/console/ScopedMetricsPage';
import ScopedQualityPage from './pages/console/ScopedQualityPage';
import ScopedUsersPage from './pages/console/ScopedUsersPage';

function WorkspaceAuditRoute() {
  const { spaceId } = useParams<{ spaceId: string }>();
  return <ScopedAuditPage spaceId={spaceId} />;
}

function App({
  capabilityNavigationEnabled = CAPABILITY_NAV_ENABLED,
}: {
  capabilityNavigationEnabled?: boolean;
}) {
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    const syncLanguage = () => {
      try {
        const authStr = localStorage.getItem('ey-auth');
        if (authStr) {
          const auth = JSON.parse(authStr);
          if (auth?.user?.language_preference && auth.user.language_preference !== i18n.language) {
            i18n.changeLanguage(auth.user.language_preference);
          }
        }
      } catch {
        // Ignore corrupt compatibility state.
      }
    };
    syncLanguage();

    const langHandler = () => {
      const lang = i18n.language || 'en';
      document.documentElement.lang = lang.startsWith('zh') ? 'zh' : 'en';
    };
    i18n.on('languageChanged', langHandler);
    langHandler();
    return () => { i18n.off('languageChanged', langHandler); };
  }, []);

  return (
    <ErrorBoundary
      title="Something went wrong"
      description="An unexpected error occurred. Please try reloading the page."
      retryText="Reload"
    >
      <Routes>
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate to="/chat" /> : <LoginPage />}
        />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route
          path="/"
          element={(
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          )}
        >
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="chat" element={<CapabilityGate required="chat.ask"><ChatPage /></CapabilityGate>} />
          <Route path="history" element={<CapabilityGate required="chat.history"><HistoryPage /></CapabilityGate>} />
          <Route path="profile" element={<ProfilePage />} />
          <Route
            path="spaces/manage"
            element={capabilityNavigationEnabled ? (
              <CapabilityGate required="workspace.manage">
                <SpaceManagementPage />
              </CapabilityGate>
            ) : <SpaceManagementPage />}
          />
        </Route>

        {capabilityNavigationEnabled ? (
          <Route
            path="/admin/*"
            element={(
              <ProtectedRoute>
                <LegacyAdminRedirect />
              </ProtectedRoute>
            )}
          />
        ) : (
          <Route
            path="/admin"
            element={(
              <ProtectedRoute>
                <AdminLayout />
              </ProtectedRoute>
            )}
          >
            <Route index element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="dashboard" element={<AdminDashboardPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="codes" element={<AdminCodesPage />} />
            <Route path="announcements" element={<AdminAnnouncementsPage />} />
            <Route path="business-lines" element={<AdminBusinessLinesPage />} />
            <Route path="audit" element={<AdminAuditPage />} />
            <Route path="templates" element={<AdminTemplatesPage />} />
            <Route path="quality" element={<AdminQualityPage />} />
            <Route path="knowledge" element={<KnowledgeBasePage />} />
          </Route>
        )}

        <Route
          path="/platform-admin"
          element={capabilityNavigationEnabled ? (
            <ProtectedRoute>
              <CapabilityGate required="platform.access">
                <ScopedConsoleLayout kind="platform" />
              </CapabilityGate>
            </ProtectedRoute>
          ) : <Navigate to="/admin" replace />}
        >
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<CapabilityGate required="platform.access"><AdminDashboardPage /></CapabilityGate>} />
          <Route path="users" element={<CapabilityGate required="platform.users.manage"><AdminUsersPage /></CapabilityGate>} />
          <Route path="business-lines" element={<CapabilityGate required="platform.organizations.manage"><AdminBusinessLinesPage /></CapabilityGate>} />
          <Route path="templates" element={<CapabilityGate required="platform.organizations.manage"><AdminTemplatesPage /></CapabilityGate>} />
          <Route path="metrics" element={<CapabilityGate required="platform.metrics.read"><ScopedMetricsPage /></CapabilityGate>} />
          <Route path="audit" element={<CapabilityGate required="platform.audit.read"><ScopedAuditPage /></CapabilityGate>} />
          <Route path="model" element={<CapabilityGate required="platform.models.manage"><ConsolePlaceholderPage title="Model profiles" /></CapabilityGate>} />
        </Route>

        <Route
          path="/governance"
          element={capabilityNavigationEnabled ? (
            <ProtectedRoute>
              <CapabilityGate required="governance.access">
                <ScopedConsoleLayout kind="governance" />
              </CapabilityGate>
            </ProtectedRoute>
          ) : <Navigate to="/admin" replace />}
        >
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<CapabilityGate required="governance.access"><ConsoleOverviewPage title="Governance" description="Organization and business-line work is limited to your assigned scope." /></CapabilityGate>} />
          <Route path="users" element={<CapabilityGate required="governance.users.manage"><ScopedUsersPage /></CapabilityGate>} />
          <Route path="business-lines" element={<CapabilityGate required="governance.business_lines.manage"><AdminBusinessLinesPage /></CapabilityGate>} />
          <Route path="templates" element={<CapabilityGate required="governance.templates.manage"><AdminTemplatesPage /></CapabilityGate>} />
          <Route path="metrics" element={<CapabilityGate required="governance.metrics.read"><ScopedMetricsPage /></CapabilityGate>} />
          <Route path="audit" element={<CapabilityGate required="governance.audit.read"><ScopedAuditPage /></CapabilityGate>} />
          <Route path="model" element={<CapabilityGate required="governance.models.bind"><ConsolePlaceholderPage title="Model binding" /></CapabilityGate>} />
        </Route>

        <Route
          path="/workspace/:spaceId/manage"
          element={capabilityNavigationEnabled ? (
            <ProtectedRoute>
              <WorkspaceCapabilityBoundary>
                <ScopedConsoleLayout kind="workspace" />
              </WorkspaceCapabilityBoundary>
            </ProtectedRoute>
          ) : <Navigate to="/spaces/manage" replace />}
        >
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<CapabilityGate required="workspace.manage"><ConsoleOverviewPage title="Workspace" description="Manage only the selected workspace and its governed resources." /></CapabilityGate>} />
          <Route path="members" element={<CapabilityGate required="workspace.members.manage"><SpaceManagementPage /></CapabilityGate>} />
          <Route path="invites" element={<CapabilityGate required="workspace.invites.manage"><SpaceManagementPage /></CapabilityGate>} />
          <Route path="access" element={<CapabilityGate required="workspace.access_requests.manage"><AccessRequestsPage /></CapabilityGate>} />
          <Route path="knowledge" element={<CapabilityGate required="knowledge.read"><KnowledgeBasePage /></CapabilityGate>} />
          <Route path="quality" element={<CapabilityGate required="quality.read"><ScopedQualityPage /></CapabilityGate>} />
          <Route path="audit" element={<CapabilityGate required="audit.read"><WorkspaceAuditRoute /></CapabilityGate>} />
          <Route path="settings" element={<CapabilityGate required="workspace.settings.manage"><SpaceManagementPage /></CapabilityGate>} />
          <Route path="lifecycle" element={<CapabilityGate required="workspace.lifecycle.manage"><ConsolePlaceholderPage title="Workspace lifecycle" /></CapabilityGate>} />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}

export default App;
