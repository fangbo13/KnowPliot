/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

﻿import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider } from './auth/AuthProvider';
import { CapabilityProvider } from './auth/CapabilityProvider';
import './hooks/useTheme';
import './i18n';
import './styles/tokens.css';
import './styles/globals.css';
import './styles/animations.css';
import './styles/chat.css';
import './styles/design-system.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <CapabilityProvider>
          <App />
        </CapabilityProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
