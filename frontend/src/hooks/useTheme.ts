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

function notifyAll() {
  sharedEffective = computeEffective(sharedMode);
  document.documentElement.setAttribute('data-theme', sharedEffective);
  listeners.forEach(fn => fn(sharedMode, sharedEffective));
}

// Initial theme application
notifyAll();

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

// Ant Design theme config — Minimalist Modern (Electric Blue)
export const eyTheme = {
  light: {
    token: {
      colorPrimary: '#0052FF',
      colorText: '#0F172A',
      colorTextSecondary: '#64748B',
      colorTextTertiary: '#8C8C8C',
      colorBgLayout: '#FAFAFA',
      colorBgContainer: '#FFFFFF',
      colorBgElevated: '#FFFFFF',
      colorBorder: '#E2E8F0',
      colorBorderSecondary: '#F1F5F9',
      colorError: '#EF4444',
      colorSuccess: '#22C55E',
      borderRadius: 12,
      fontSize: 14,
      lineHeight: 1.625,
      controlHeight: 44,
      wireframe: false,
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      fontFamilyCode: "'JetBrains Mono', monospace",
    },
    components: {
      Button: {
        fontWeight: 500,
        primaryShadow: '0 2px 6px rgba(0, 82, 255, 0.2)',
        controlHeight: 44,
        borderRadius: 12,
        borderRadiusLG: 14,
      },
      Card: {
        borderRadiusLG: 12,
        boxShadow: '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
        boxShadowHover: '0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.04)',
        headerFontSize: 15,
      },
      Input: {
        borderRadius: 10,
        controlHeight: 44,
        activeBorderColor: 'rgba(0, 82, 255, 0.5)',
        hoverBorderColor: 'rgba(0, 82, 255, 0.3)',
        activeShadow: '0 0 0 2px rgba(0, 82, 255, 0.1)',
      },
      Menu: {
        itemBorderRadius: 10,
        subMenuItemBg: 'transparent',
        itemSelectedBg: 'rgba(0, 82, 255, 0.08)',
        itemSelectedColor: '#0F172A',
        itemActiveBg: 'rgba(0, 82, 255, 0.12)',
        itemHoverBg: 'rgba(0, 0, 0, 0.02)',
        itemHoverColor: '#0F172A',
        iconSize: 16,
        collapsedIconSize: 16,
      },
      Layout: {
        siderBg: '#FFFFFF',
        headerBg: '#FFFFFF',
        bodyBg: '#FAFAFA',
      },
      Typography: {
        titleMarginBottom: 12,
      },
      Table: {
        borderRadiusLG: 10,
        headerBorderRadius: 10,
        headerBg: '#F8FAFC',
        headerColor: '#475569',
      },
      Select: {
        borderRadius: 10,
        controlHeight: 44,
        activeBorderColor: 'rgba(0, 82, 255, 0.5)',
        hoverBorderColor: 'rgba(0, 82, 255, 0.3)',
      },
      Spin: {
        dotColorPrimary: '#0052FF',
        dotSize: 10,
        dotSizeSM: 8,
        dotSizeLG: 16,
      },
      Empty: {
        fontSizeIcon: 48,
      },
      Alert: {
        borderRadiusLG: 10,
      },
      Modal: {
        borderRadiusLG: 16,
      },
      Tag: {
        borderRadiusSM: 6,
        defaultColor: '#475569',
      },
      Segmented: {
        trackPadding: 3,
        itemSelectedBg: '#0052FF',
        itemSelectedColor: '#FFFFFF',
        borderRadius: 10,
      },
    },
  },
  dark: {
    token: {
      colorPrimary: '#4D7CFF',
      colorText: '#E2E8F0',
      colorTextSecondary: '#94A3B8',
      colorTextTertiary: '#64748B',
      colorBgLayout: '#0B1120',
      colorBgContainer: '#1E293B',
      colorBgElevated: '#253042',
      colorBorder: '#334155',
      colorBorderSecondary: '#2D3A4F',
      colorError: '#F87171',
      colorSuccess: '#4ADE80',
      borderRadius: 12,
      fontSize: 14,
      lineHeight: 1.625,
      controlHeight: 44,
      wireframe: false,
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    },
    algorithm: antTheme.darkAlgorithm,
    components: {
      Button: {
        fontWeight: 500,
        primaryShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
        controlHeight: 44,
        borderRadius: 12,
        borderRadiusLG: 14,
      },
      Card: {
        borderRadiusLG: 12,
        boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
        boxShadowHover: '0 4px 6px rgba(0,0,0,0.3)',
        headerFontSize: 15,
      },
      Input: {
        borderRadius: 10,
        controlHeight: 44,
        activeBorderColor: 'rgba(77, 124, 255, 0.5)',
        hoverBorderColor: 'rgba(77, 124, 255, 0.3)',
      },
      Menu: {
        itemBorderRadius: 10,
        subMenuItemBg: 'transparent',
        itemSelectedBg: 'rgba(77, 124, 255, 0.15)',
        itemSelectedColor: '#E2E8F0',
        itemActiveBg: 'rgba(77, 124, 255, 0.2)',
        itemHoverBg: 'rgba(255, 255, 255, 0.04)',
        itemHoverColor: '#E2E8F0',
        iconSize: 16,
        collapsedIconSize: 16,
      },
      Layout: {
        siderBg: '#1E293B',
        headerBg: '#1E293B',
        bodyBg: '#0B1120',
      },
      Typography: {
        titleMarginBottom: 12,
      },
      Table: {
        borderRadiusLG: 10,
        headerBorderRadius: 10,
        headerBg: '#1A2535',
        headerColor: '#94A3B8',
      },
      Select: {
        borderRadius: 10,
        controlHeight: 44,
      },
      Spin: {
        dotColorPrimary: '#4D7CFF',
        dotSize: 10,
        dotSizeSM: 8,
        dotSizeLG: 16,
      },
      Empty: {
        fontSizeIcon: 48,
      },
      Alert: {
        borderRadiusLG: 10,
      },
      Modal: {
        borderRadiusLG: 16,
      },
      Tag: {
        borderRadiusSM: 6,
      },
      Segmented: {
        trackPadding: 3,
        itemSelectedBg: '#4D7CFF',
        itemSelectedColor: '#FFFFFF',
        borderRadius: 10,
      },
    },
  },
};
