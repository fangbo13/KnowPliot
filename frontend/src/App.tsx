import { Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import AppLayout from './layout/AppLayout';
import ChatPage from './pages/ChatPage';
import ProfilePage from './pages/ProfilePage';
import KnowledgeBasePage from './pages/admin/KnowledgeBasePage';
import LoginPage from './auth/LoginPage';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { useAuth } from './auth/AuthProvider';

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

  return (
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
        <Route path="admin/knowledge" element={<KnowledgeBasePage />} />
      </Route>
    </Routes>
  );
}

export default App;
