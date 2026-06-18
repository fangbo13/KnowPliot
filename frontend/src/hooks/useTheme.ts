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

function getEffectiveTheme(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') return getSystemTheme();
  return mode;
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return (stored as ThemeMode) || 'light';
  });

  const effective = getEffectiveTheme(mode);

  // Apply data-theme attribute for CSS variables
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', effective);
  }, [effective]);

  // Listen for system theme changes when mode is 'system'
  useEffect(() => {
    if (mode !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => {
      document.documentElement.setAttribute('data-theme', getSystemTheme());
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [mode]);

  const setThemeMode = useCallback((newMode: ThemeMode) => {
    setMode(newMode);
    localStorage.setItem(STORAGE_KEY, newMode);
  }, []);

  return { mode, effective, setThemeMode };
}

// Ant Design theme config for EY brand (Premium)
export const eyTheme = {
  light: {
    token: {
      colorPrimary: '#FFE500',
      colorText: '#262626',
      colorTextSecondary: '#595959',
      colorTextTertiary: '#8C8C8C',
      colorBgLayout: '#FAFAFA',
      colorBgContainer: '#FFFFFF',
      colorBgElevated: '#FFFFFF',
      colorBorder: '#D9D9D9',
      colorBorderSecondary: '#F0F0F0',
      colorError: '#FF4D4F',
      colorSuccess: '#52C41A',
      borderRadius: 10,
      fontSize: 14,
      lineHeight: 1.6,
      controlHeight: 42,
      wireframe: false,
    },
    components: {
      Button: {
        fontWeight: 600,
        primaryShadow: '0 2px 6px rgba(255, 229, 0, 0.2)',
        controlHeight: 42,
        borderRadius: 10,
      },
      Card: {
        borderRadiusLG: 14,
        boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.06)',
        boxShadowHover: '0 4px 6px rgba(0,0,0,0.03), 0 2px 4px rgba(0,0,0,0.04)',
        headerFontSize: 15,
      },
      Input: {
        borderRadius: 10,
        controlHeight: 42,
        activeBorderColor: 'rgba(255, 229, 0, 0.5)',
        hoverBorderColor: 'rgba(255, 229, 0, 0.3)',
      },
      Menu: {
        itemBorderRadius: 10,
        subMenuItemBg: 'transparent',
        itemSelectedBg: 'rgba(255, 229, 0, 0.10)',
        itemSelectedColor: '#262626',
        itemActiveBg: 'rgba(255, 229, 0, 0.15)',
        itemHoverBg: 'rgba(0, 0, 0, 0.02)',
        itemHoverColor: '#262626',
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
      },
      Select: {
        borderRadius: 10,
        controlHeight: 42,
      },
      Spin: {
        dotSize: 10,
        dotSizeSM: 8,
        dotSizeLG: 16,
      },
      Empty: {
        fontSizeIcon: 48,
      },
    },
  },
  dark: {
    token: {
      colorPrimary: '#FFE500',
      colorText: '#E0E0E0',
      colorTextSecondary: '#A6A6A6',
      colorTextTertiary: '#737373',
      colorBgLayout: '#141414',
      colorBgContainer: '#1F1F1F',
      colorBgElevated: '#2A2A2A',
      colorBorder: '#434343',
      colorBorderSecondary: '#303030',
      colorError: '#FF4D4F',
      colorSuccess: '#52C41A',
      borderRadius: 10,
      fontSize: 14,
      lineHeight: 1.6,
      controlHeight: 42,
      wireframe: false,
    },
    algorithm: antTheme.darkAlgorithm,
    components: {
      Button: {
        fontWeight: 600,
        primaryShadow: '0 2px 8px rgba(0,0,0,0.3)',
        controlHeight: 42,
        borderRadius: 10,
      },
      Card: {
        borderRadiusLG: 14,
        boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
        boxShadowHover: '0 4px 6px rgba(0,0,0,0.3)',
        headerFontSize: 15,
      },
      Input: {
        borderRadius: 10,
        controlHeight: 42,
      },
      Menu: {
        itemBorderRadius: 10,
        subMenuItemBg: 'transparent',
        itemSelectedBg: 'rgba(255, 229, 0, 0.15)',
        itemSelectedColor: '#E0E0E0',
        itemActiveBg: 'rgba(255, 229, 0, 0.2)',
        itemHoverBg: 'rgba(255, 255, 255, 0.04)',
        itemHoverColor: '#E0E0E0',
        iconSize: 16,
        collapsedIconSize: 16,
      },
      Layout: {
        siderBg: '#1F1F1F',
        headerBg: '#1F1F1F',
        bodyBg: '#141414',
      },
      Typography: {
        titleMarginBottom: 12,
      },
      Table: {
        borderRadiusLG: 10,
        headerBorderRadius: 10,
      },
      Select: {
        borderRadius: 10,
        controlHeight: 42,
      },
      Spin: {
        dotSize: 10,
        dotSizeSM: 8,
        dotSizeLG: 16,
      },
      Empty: {
        fontSizeIcon: 48,
      },
    },
  },
};
