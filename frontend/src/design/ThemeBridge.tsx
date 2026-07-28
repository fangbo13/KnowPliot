/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// UI Claude-style optimization spec §3: mount the (previously unused) antd
// theme so components get darkAlgorithm-derived colors instead of relying on
// CSS overrides — the systemic fix for dark-mode contrast issues.

import { useMemo, type ReactNode } from 'react';
import { ConfigProvider } from 'antd';

import { useTheme } from '../hooks/useTheme';
import { getAntTheme } from './theme';

export function ThemeBridge({ children }: { children: ReactNode }) {
  const { effective } = useTheme();
  const antTheme = useMemo(() => getAntTheme(effective), [effective]);
  return <ConfigProvider theme={antTheme}>{children}</ConfigProvider>;
}
