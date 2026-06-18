import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import App from './App';
import { AuthProvider } from './auth/AuthProvider';
import { useTheme, eyTheme } from './hooks/useTheme';
import './i18n';
import './styles/globals.css';

function ThemedApp() {
  const { effective } = useTheme();
  const themeConfig = effective === 'dark' ? eyTheme.dark : eyTheme.light;

  return (
    <ConfigProvider theme={themeConfig}>
      <App />
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ThemedApp />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
