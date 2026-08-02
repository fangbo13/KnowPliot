/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { antDesignDirectImports } from './scripts/vite-direct-imports.mjs';

export default defineConfig(({ mode }) => {
  // Allow configuring proxy target via environment variable
  // Host machine defaults to local Django.
  // Docker overrides this with VITE_PROXY_TARGET=http://backend:8000.
  const env = loadEnv(mode, process.cwd(), '');
  const proxyTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000';
  const base = env.VITE_BASE_PATH || (env.GITHUB_ACTIONS === 'true' ? '/KnowPliot/' : '/');
  const apiProxy = {
    '/api': {
      target: proxyTarget,
      changeOrigin: true,
    },
  };

  return {
    base,
    plugins: [antDesignDirectImports(), react()],
    build: {
      manifest: true,
      chunkSizeWarningLimit: 1300,
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      proxy: apiProxy,
      allowedHosts: true,
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
      proxy: apiProxy,
    },
  };
});
