import React, { useMemo } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import App from './App';
import { AuthProvider } from './auth/AuthProvider';
import { useTheme, eyTheme } from './hooks/useTheme';
import './i18n';
import './styles/tokens.css';
import './styles/globals.css';
import './styles/chat.css';

function ThemeRoot({ children }: { children: React.ReactNode }) {
  const { effective } = useTheme();
  const themeConfig = useMemo(
    () => (effective === 'dark' ? eyTheme.dark : eyTheme.light),
    [effective]
  );

  return (
    <ConfigProvider theme={themeConfig}>
      {children}
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ThemeRoot>
          <App />
        </ThemeRoot>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
