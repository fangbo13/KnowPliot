/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { lazy, Suspense, type ReactNode, useEffect } from 'react';
import { Navigate, Route, Routes, useParams } from 'react-router-dom';

import { CapabilityGate, LegacyAdminRedirect } from './auth/CapabilityGate';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { useAuth } from './auth/AuthProvider';
import { WorkspaceCapabilityBoundary } from './auth/WorkspaceCapabilityBoundary';
import { CAPABILITY_NAV_ENABLED } from './auth/authorization';
import {
  AuthenticatedEntryRedirect,
  NavigationModeBoundary,
} from './auth/NavigationRouting';
import ErrorBoundary from './components/ErrorBoundary';
import i18n from './i18n';

const AppLayout = lazy(() => import('./layout/AppLayout'));
const LoginPage = lazy(() => import('./auth/LoginPage'));
const ResetPasswordPage = lazy(() => import('./auth/ResetPasswordPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const AdminLayout = lazy(() => import('./layout/AdminLayout'));
const ScopedConsoleLayout = lazy(() => import('./layout/ScopedConsoleLayout'));
const HistoryPage = lazy(() => import('./pages/HistoryPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const SpaceManagementPage = lazy(() => import('./pages/SpaceManagementPage'));
const SharedConversationPage = lazy(() => import('./pages/SharedConversationPage'));
const SpaceDiscoveryPage = lazy(() => import('./pages/SpaceDiscoveryPage'));
const OwnershipTransfersPage = lazy(() => import('./pages/OwnershipTransfersPage'));
const AdminAnnouncementsPage = lazy(() => import('./pages/admin/AdminAnnouncementsPage'));
const AdminAuditPage = lazy(() => import('./pages/admin/AdminAuditPage'));
const AdminBusinessLinesPage = lazy(() => import('./pages/admin/AdminBusinessLinesPage'));
const AdminCodesPage = lazy(() => import('./pages/admin/AdminCodesPage'));
const AdminDashboardPage = lazy(() => import('./pages/admin/AdminDashboardPage'));
const AdminQualityPage = lazy(() => import('./pages/admin/AdminQualityPage'));
const AdminTemplatesPage = lazy(() => import('./pages/admin/AdminTemplatesPage'));
const AdminUsersPage = lazy(() => import('./pages/admin/AdminUsersPage'));
const KnowledgeBasePage = lazy(() => import('./pages/admin/KnowledgeBasePage'));
const AccessRequestsPage = lazy(() => import('./pages/console/AccessRequestsPage'));
const ConsoleOverviewPage = lazy(() => import('./pages/console/ConsoleOverviewPage'));
const ScopedAuditPage = lazy(() => import('./pages/console/ScopedAuditPage'));
const ScopedMetricsPage = lazy(() => import('./pages/console/ScopedMetricsPage'));
const ScopedQualityPage = lazy(() => import('./pages/console/ScopedQualityPage'));
const ScopedUsersPage = lazy(() => import('./pages/console/ScopedUsersPage'));
const GovernancePoliciesPage = lazy(() => import('./pages/console/GovernancePoliciesPage'));
const ModelProfilesPage = lazy(() => import('./pages/console/ModelProfilesPage'));
const WorkspaceLifecyclePage = lazy(() => import('./pages/console/WorkspaceLifecyclePage'));
const WorkspaceCreationPage = lazy(() => import('./pages/WorkspaceCreationPage'));
const WorkspaceCreationReviewPage = lazy(() => import('./pages/console/WorkspaceCreationReviewPage'));
const PlatformKnowledgePage = lazy(() => import('./pages/console/PlatformKnowledgePage'));

function RouteLoading() {
  return (
    <div
      role="status"
      style={{ display: 'grid', minHeight: '40vh', placeItems: 'center', color: 'var(--color-text-secondary)' }}
    >
      Loading page…
    </div>
  );
}

function SuspendedRoute({ children }: { children: ReactNode }) {
  return <Suspense fallback={<RouteLoading />}>{children}</Suspense>;
}

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
  const expectedNavigationMode = capabilityNavigationEnabled ? 'capability' : 'legacy';

  useEffect(() => {
    // F-01 fix: language persistence is now handled by AuthProvider's useEffect,
    // which syncs user.language_preference to i18n + ey-language localStorage on
    // login / profile update.  On page reload, i18n initialises from ey-language
    // (set in i18n/index.ts getInitialLanguage).  We no longer override it here.

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
          element={isAuthenticated ? <AuthenticatedEntryRedirect /> : <SuspendedRoute><LoginPage /></SuspendedRoute>}
        />
        <Route path="/reset-password" element={<SuspendedRoute><ResetPasswordPage /></SuspendedRoute>} />
        <Route
          path="/"
          element={(
            <ProtectedRoute>
              <SuspendedRoute><AppLayout /></SuspendedRoute>
            </ProtectedRoute>
          )}
        >
          <Route index element={<AuthenticatedEntryRedirect />} />
          <Route path="chat" element={<CapabilityGate required="chat.ask"><SuspendedRoute><ChatPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="history" element={<CapabilityGate required="chat.history"><SuspendedRoute><HistoryPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="shared/:token" element={<SuspendedRoute><SharedConversationPage /></SuspendedRoute>} />
          <Route path="spaces/discover" element={<SuspendedRoute><SpaceDiscoveryPage /></SuspendedRoute>} />
          <Route path="spaces/create" element={<CapabilityGate required="workspace.creation.request"><SuspendedRoute><WorkspaceCreationPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="profile" element={<SuspendedRoute><ProfilePage /></SuspendedRoute>} />
          <Route path="ownership-transfers" element={<SuspendedRoute><OwnershipTransfersPage /></SuspendedRoute>} />
          <Route
            path="spaces/manage"
            element={(
              <NavigationModeBoundary expected={expectedNavigationMode}>
                {capabilityNavigationEnabled
                  ? <LegacyAdminRedirect />
                  : <SuspendedRoute><SpaceManagementPage /></SuspendedRoute>}
              </NavigationModeBoundary>
            )}
          />
        </Route>

        {capabilityNavigationEnabled ? (
          <Route
            path="/admin/*"
            element={(
              <ProtectedRoute>
                <NavigationModeBoundary expected="capability">
                  <LegacyAdminRedirect />
                </NavigationModeBoundary>
              </ProtectedRoute>
            )}
          />
        ) : (
          <Route
            path="/admin"
            element={(
              <ProtectedRoute>
                <NavigationModeBoundary expected="legacy">
                  <SuspendedRoute><AdminLayout /></SuspendedRoute>
                </NavigationModeBoundary>
              </ProtectedRoute>
            )}
          >
            <Route index element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="dashboard" element={<SuspendedRoute><AdminDashboardPage /></SuspendedRoute>} />
            <Route path="users" element={<SuspendedRoute><AdminUsersPage /></SuspendedRoute>} />
            <Route path="codes" element={<SuspendedRoute><AdminCodesPage /></SuspendedRoute>} />
            <Route path="announcements" element={<SuspendedRoute><AdminAnnouncementsPage /></SuspendedRoute>} />
            <Route path="business-lines" element={<SuspendedRoute><AdminBusinessLinesPage /></SuspendedRoute>} />
            <Route path="audit" element={<SuspendedRoute><AdminAuditPage /></SuspendedRoute>} />
            <Route path="templates" element={<SuspendedRoute><AdminTemplatesPage /></SuspendedRoute>} />
            <Route path="quality" element={<SuspendedRoute><AdminQualityPage /></SuspendedRoute>} />
            <Route path="knowledge" element={<SuspendedRoute><KnowledgeBasePage /></SuspendedRoute>} />
          </Route>
        )}

        <Route
          path="/platform-admin"
          element={(
            <ProtectedRoute>
              <NavigationModeBoundary expected={expectedNavigationMode}>
                {capabilityNavigationEnabled ? (
                  <CapabilityGate required="platform.access">
                    <SuspendedRoute><ScopedConsoleLayout kind="platform" /></SuspendedRoute>
                  </CapabilityGate>
                ) : <Navigate to="/admin" replace />}
              </NavigationModeBoundary>
            </ProtectedRoute>
          )}
        >
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<CapabilityGate required="platform.access"><SuspendedRoute><AdminDashboardPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="users" element={<CapabilityGate required="platform.users.manage"><SuspendedRoute><AdminUsersPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="business-lines" element={<CapabilityGate required="platform.organizations.manage"><SuspendedRoute><AdminBusinessLinesPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="templates" element={<CapabilityGate required="platform.templates.manage"><SuspendedRoute><AdminTemplatesPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="creation-requests" element={<CapabilityGate required="platform.workspace_creation_requests.manage"><SuspendedRoute><WorkspaceCreationReviewPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="knowledge" element={<CapabilityGate required="platform.knowledge.read"><SuspendedRoute><PlatformKnowledgePage /></SuspendedRoute></CapabilityGate>} />
          <Route path="metrics" element={<CapabilityGate required="platform.metrics.read"><SuspendedRoute><ScopedMetricsPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="audit" element={<CapabilityGate required="platform.audit.read"><SuspendedRoute><ScopedAuditPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="model" element={<CapabilityGate required="platform.models.manage"><SuspendedRoute><ModelProfilesPage /></SuspendedRoute></CapabilityGate>} />
        </Route>

        <Route
          path="/governance"
          element={(
            <ProtectedRoute>
              <NavigationModeBoundary expected={expectedNavigationMode}>
                {capabilityNavigationEnabled ? (
                  <CapabilityGate required="governance.access">
                    <SuspendedRoute><ScopedConsoleLayout kind="governance" /></SuspendedRoute>
                  </CapabilityGate>
                ) : <Navigate to="/admin" replace />}
              </NavigationModeBoundary>
            </ProtectedRoute>
          )}
        >
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<CapabilityGate required="governance.access"><SuspendedRoute><ConsoleOverviewPage title="Governance" description="Organization and business-line work is limited to your assigned scope." /></SuspendedRoute></CapabilityGate>} />
          <Route path="users" element={<CapabilityGate required="governance.users.manage"><SuspendedRoute><ScopedUsersPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="business-lines" element={<CapabilityGate required="governance.business_lines.manage"><SuspendedRoute><AdminBusinessLinesPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="templates" element={<CapabilityGate required="governance.templates.manage"><SuspendedRoute><AdminTemplatesPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="metrics" element={<CapabilityGate required="governance.metrics.read"><SuspendedRoute><ScopedMetricsPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="audit" element={<CapabilityGate required="governance.audit.read"><SuspendedRoute><ScopedAuditPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="model" element={<CapabilityGate required="governance.models.bind"><SuspendedRoute><GovernancePoliciesPage /></SuspendedRoute></CapabilityGate>} />
        </Route>

        <Route
          path="/workspace/:spaceId/manage"
          element={(
            <ProtectedRoute>
              <NavigationModeBoundary expected={expectedNavigationMode}>
                {capabilityNavigationEnabled ? (
                  <WorkspaceCapabilityBoundary>
                    <SuspendedRoute><ScopedConsoleLayout kind="workspace" /></SuspendedRoute>
                  </WorkspaceCapabilityBoundary>
                ) : <Navigate to="/spaces/manage" replace />}
              </NavigationModeBoundary>
            </ProtectedRoute>
          )}
        >
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<CapabilityGate required="workspace.manage"><SuspendedRoute><ConsoleOverviewPage title="Workspace" description="Manage only the selected workspace and its governed resources." /></SuspendedRoute></CapabilityGate>} />
          <Route path="members" element={<CapabilityGate required="workspace.members.manage"><SuspendedRoute><SpaceManagementPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="invites" element={<CapabilityGate required="workspace.invites.manage"><SuspendedRoute><SpaceManagementPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="access" element={<CapabilityGate required="workspace.access_requests.manage"><SuspendedRoute><AccessRequestsPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="knowledge" element={<CapabilityGate required="knowledge.read"><SuspendedRoute><KnowledgeBasePage /></SuspendedRoute></CapabilityGate>} />
          <Route path="quality" element={<CapabilityGate required="quality.read"><SuspendedRoute><ScopedQualityPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="audit" element={<CapabilityGate required="audit.read"><SuspendedRoute><WorkspaceAuditRoute /></SuspendedRoute></CapabilityGate>} />
          <Route path="settings" element={<CapabilityGate required="workspace.settings.manage"><SuspendedRoute><SpaceManagementPage /></SuspendedRoute></CapabilityGate>} />
          <Route path="lifecycle" element={<CapabilityGate required="workspace.lifecycle.manage"><SuspendedRoute><WorkspaceLifecyclePage /></SuspendedRoute></CapabilityGate>} />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}

export default App;
