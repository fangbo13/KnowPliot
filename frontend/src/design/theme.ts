import { theme as antTheme, type ThemeConfig } from 'antd';

import { designTokens, type DesignTheme } from './tokens';

export function getAntTheme(theme: DesignTheme): ThemeConfig {
  const color = designTokens.color[theme];
  const sharedComponents: ThemeConfig['components'] = {
    Button: { fontWeight: 500, controlHeight: 40, borderRadius: 8, borderRadiusLG: 8, primaryShadow: 'none' },
    Card: { borderRadiusLG: 12, headerFontSize: 16 },
    Input: { borderRadius: 8, controlHeight: 40 },
    Select: { borderRadius: 8, controlHeight: 40 },
    Menu: { itemBorderRadius: 8, subMenuItemBg: 'transparent', iconSize: 16, collapsedIconSize: 16 },
    Typography: { titleMarginBottom: 8 },
    Table: { borderRadiusLG: 8, headerBorderRadius: 8, headerBg: color.sunken, headerColor: color.textSecondary },
    Modal: { borderRadiusLG: 12 },
    Alert: { borderRadiusLG: 8 },
    Tag: { borderRadiusSM: 8 },
    Segmented: { trackPadding: 3, borderRadius: 8, itemSelectedBg: color.accent, itemSelectedColor: color.onAccent },
    Tooltip: { borderRadius: 8 },
    Popover: { borderRadiusLG: 8 },
    Layout: { siderBg: color.surface, headerBg: color.surface, bodyBg: color.background },
  };

  return {
    algorithm: theme === 'dark' ? antTheme.darkAlgorithm : undefined,
    token: {
      colorPrimary: color.accent,
      colorInfo: color.accent,
      colorText: color.text,
      colorTextSecondary: color.textSecondary,
      colorTextTertiary: color.textTertiary,
      colorBgLayout: color.background,
      colorBgContainer: color.surface,
      colorBgElevated: color.elevated,
      colorBorder: color.border,
      colorBorderSecondary: color.borderSecondary,
      colorError: color.error,
      colorSuccess: color.success,
      colorWarning: color.warning,
      borderRadius: designTokens.radius.control,
      fontSize: designTokens.typography.baseSize,
      lineHeight: designTokens.typography.lineHeight,
      controlHeight: 40,
      wireframe: false,
      fontFamily: designTokens.typography.body,
      fontFamilyCode: designTokens.typography.mono,
      motionDurationFast: `${designTokens.motion.duration.fast / 1000}s`,
      motionDurationMid: `${designTokens.motion.duration.base / 1000}s`,
      motionDurationSlow: `${designTokens.motion.duration.slow / 1000}s`,
    },
    components: sharedComponents,
  };
}
