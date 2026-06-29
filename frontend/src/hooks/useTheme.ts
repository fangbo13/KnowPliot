import { useState, useEffect, useCallback } from 'react';
import { theme as antTheme } from 'antd';

export type ThemeMode = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'ey-theme';

function getSystemTheme(): 'light' | 'dark' {
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

// Singleton: shared state across all hooks
let sharedMode: ThemeMode = 'light';
let sharedEffective: 'light' | 'dark' = 'light';
let themeReady = false; // first application is synchronous (avoid initial flash)
const listeners = new Set<(mode: ThemeMode, effective: 'light' | 'dark') => void>();

try {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    sharedMode = stored;
  }
} catch {}

function computeEffective(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') return getSystemTheme();
  return mode;
}

function applyThemeNow() {
  sharedEffective = computeEffective(sharedMode);
  document.documentElement.setAttribute('data-theme', sharedEffective);
  listeners.forEach(fn => fn(sharedMode, sharedEffective));
}

function notifyAll() {
  // Progressive enhancement: cross-fade theme switches via the View Transitions
  // API when available. First application (module load) and reduced-motion users
  // apply synchronously. State logic is unchanged — only HOW the swap is painted.
  const prefersReduced =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const startVT = (document as any).startViewTransition?.bind(document);
  if (themeReady && startVT && !prefersReduced) {
    startVT(applyThemeNow);
  } else {
    applyThemeNow();
  }
}

// Initial theme application (synchronous)
notifyAll();
themeReady = true;

// System theme listener (singleton)
if (typeof window !== 'undefined') {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  mq.addEventListener('change', () => {
    if (sharedMode === 'system') notifyAll();
  });
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(sharedMode);
  const [effective, setEffective] = useState<'light' | 'dark'>(sharedEffective);

  useEffect(() => {
    const handler = (newMode: ThemeMode, newEffective: 'light' | 'dark') => {
      setMode(newMode);
      setEffective(newEffective);
    };
    listeners.add(handler);
    return () => { listeners.delete(handler); };
  }, []);

  const setThemeMode = useCallback((newMode: ThemeMode) => {
    sharedMode = newMode;
    localStorage.setItem(STORAGE_KEY, newMode);
    notifyAll();
  }, []);

  return { mode, effective, setThemeMode };
}

/* ----------------------------------------------------------------------------
   Ant Design theme — Claude warm "paper" palette.
   Only token VALUES changed; consumed by ConfigProvider in main.tsx so the
   admin/form pages (AntD) reskin in lockstep with the CSS-variable layer.
   ---------------------------------------------------------------------------- */
const sharedFont = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif";
const sharedComponents = {
  Button: { fontWeight: 500, controlHeight: 40, borderRadius: 12, borderRadiusLG: 14, primaryShadow: 'none' },
  Card: { borderRadiusLG: 16, headerFontSize: 16 },
  Input: { borderRadius: 12, controlHeight: 40 },
  Select: { borderRadius: 12, controlHeight: 40 },
  Menu: { itemBorderRadius: 10, subMenuItemBg: 'transparent', iconSize: 16, collapsedIconSize: 16 },
  Typography: { titleMarginBottom: 12 },
  Table: { borderRadiusLG: 12, headerBorderRadius: 12 },
  Modal: { borderRadiusLG: 18 },
  Drawer: {},
  Alert: { borderRadiusLG: 12 },
  Tag: { borderRadiusSM: 8 },
  Segmented: { trackPadding: 3, borderRadius: 12 },
  Spin: { dotSize: 10, dotSizeSM: 8, dotSizeLG: 16 },
  Tooltip: { borderRadius: 8 },
  Popover: { borderRadiusLG: 14 },
};

export const eyTheme = {
  light: {
    token: {
      colorPrimary: '#C2693F',
      colorInfo: '#C2693F',
      colorText: '#29251F',
      colorTextSecondary: '#6E675C',
      colorTextTertiary: '#9A9384',
      colorBgLayout: '#F5F4EE',
      colorBgContainer: '#FCFBF7',
      colorBgElevated: '#FFFFFF',
      colorBorder: '#E4E0D5',
      colorBorderSecondary: '#ECE9DF',
      colorError: '#B23B30',
      colorSuccess: '#4F7A4A',
      colorWarning: '#B8801F',
      borderRadius: 12,
      fontSize: 15,
      lineHeight: 1.65,
      controlHeight: 40,
      wireframe: false,
      fontFamily: sharedFont,
      fontFamilyCode: "'JetBrains Mono', monospace",
    },
    components: {
      ...sharedComponents,
      Menu: { ...sharedComponents.Menu, itemSelectedBg: 'rgba(194,105,63,0.10)', itemSelectedColor: '#29251F', itemActiveBg: 'rgba(194,105,63,0.14)', itemHoverBg: 'rgba(64,52,40,0.05)', itemHoverColor: '#29251F' },
      Layout: { siderBg: '#FCFBF7', headerBg: '#FCFBF7', bodyBg: '#F5F4EE' },
      Table: { ...sharedComponents.Table, headerBg: '#F0EEE6', headerColor: '#6E675C' },
      Segmented: { ...sharedComponents.Segmented, itemSelectedBg: '#C2693F', itemSelectedColor: '#FFFFFF' },
    },
  },
  dark: {
    token: {
      colorPrimary: '#D9805C',
      colorInfo: '#D9805C',
      colorText: '#ECE7DC',
      colorTextSecondary: '#B0A998',
      colorTextTertiary: '#847D6E',
      colorBgLayout: '#1C1A17',
      colorBgContainer: '#24221E',
      colorBgElevated: '#2B2925',
      colorBorder: '#38352F',
      colorBorderSecondary: '#302D28',
      colorError: '#E07B6B',
      colorSuccess: '#7FB069',
      colorWarning: '#E0B05C',
      borderRadius: 12,
      fontSize: 15,
      lineHeight: 1.65,
      controlHeight: 40,
      wireframe: false,
      fontFamily: sharedFont,
      fontFamilyCode: "'JetBrains Mono', monospace",
    },
    algorithm: antTheme.darkAlgorithm,
    components: {
      ...sharedComponents,
      Menu: { ...sharedComponents.Menu, itemSelectedBg: 'rgba(217,128,92,0.18)', itemSelectedColor: '#ECE7DC', itemActiveBg: 'rgba(217,128,92,0.24)', itemHoverBg: 'rgba(236,231,220,0.06)', itemHoverColor: '#ECE7DC' },
      Layout: { siderBg: '#24221E', headerBg: '#24221E', bodyBg: '#1C1A17' },
      Table: { ...sharedComponents.Table, headerBg: '#2B2925', headerColor: '#B0A998' },
      Segmented: { ...sharedComponents.Segmented, itemSelectedBg: '#D9805C', itemSelectedColor: '#1C140E' },
    },
  },
};
