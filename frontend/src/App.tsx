import { Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import AppLayout from './layout/AppLayout';
import ChatPage from './pages/ChatPage';
import ProfilePage from './pages/ProfilePage';
import SpaceManagementPage from './pages/SpaceManagementPage';
import KnowledgeBasePage from './pages/admin/KnowledgeBasePage';
import AdminDashboardPage from './pages/admin/AdminDashboardPage';
import LoginPage from './auth/LoginPage';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { RoleGuard } from './auth/RoleGuard';
import { useAuth } from './auth/AuthProvider';
import ErrorBoundary from './components/ErrorBoundary';

function App() {
  const { isAuthenticated } = useAuth();

  // Sync i18n language on mount from stored auth preference
  useEffect(() => {
    const syncLanguage = async () => {
      try {
        const authStr = localStorage.getItem('ey-auth');
        if (authStr) {
          const auth = JSON.parse(authStr);
          const { default: i18n } = await import('./i18n');
          if (auth?.user?.language_preference && auth.user.language_preference !== i18n.language) {
            i18n.changeLanguage(auth.user.language_preference);
          }
        }
      } catch {
        // ignore
      }
    };
    syncLanguage();

    // Dynamic html lang sync with i18n language changes
    import('./i18n').then(({ default: i18nModule }) => {
      const langHandler = () => {
        const lang = i18nModule.language || 'en';
        document.documentElement.lang = lang.startsWith('zh') ? 'zh' : 'en';
      };
      i18nModule.on('languageChanged', langHandler);
      langHandler();
      return () => { i18nModule.off('languageChanged', langHandler); };
    });
  }, []);

  // V4.1 BUG-004: Top-level ErrorBoundary wrapping entire Routes.
  // Without this, a crash in LoginPage or route transitions causes a white screen.
  // The existing ErrorBoundary inside AppLayout (L853) catches content-area crashes,
  // giving a two-tier error recovery: top → layout/auth, inner → content.
  // ErrorBoundary is outside i18n context, so we use static English strings.
  // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-004]
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
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="profile" element={<ProfilePage />} />
        {/* V6.0: space management (members, access codes, settings) */}
        <Route path="spaces/manage" element={<SpaceManagementPage />} />
        {/* V4.0 RBAC: HR knowledge base — requires hr or admin role */}
        <Route
          path="admin/knowledge"
          element={
            <RoleGuard requiredRole="hr">
              <KnowledgeBasePage />
            </RoleGuard>
          }
        />
        {/* V4.0 RBAC: Admin dashboard — requires admin role */}
        <Route
          path="admin/dashboard"
          element={
            <RoleGuard requiredRole="admin">
              <AdminDashboardPage />
            </RoleGuard>
          }
        />
        {/* V6.0: Web crawler admin route removed (feature retired). */}
      </Route>
    </Routes>
    </ErrorBoundary>
  );
}

export default App;
