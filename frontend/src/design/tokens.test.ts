// @vitest-environment jsdom

import { describe, expect, it } from 'vitest';

import {
  applyDesignTokens,
  designTokens,
  getCssVariables,
} from './tokens';
import { getAntTheme } from './theme';

describe('design token bridge', () => {
  it('locks the approved spacing, width, radius, and motion contracts', () => {
    expect(designTokens.spacing.base).toBe(8);
    expect(designTokens.width.reading).toBe(760);
    expect(designTokens.width.management).toBe(1200);
    expect(designTokens.radius.control).toBe(8);
    expect(designTokens.motion.duration).toEqual({ fast: 120, base: 180, slow: 240 });
  });

  it('derives CSS variables and Ant tokens from the same semantic palette', () => {
    const variables = getCssVariables('light');
    const ant = getAntTheme('light');

    expect(variables['--color-primary']).toBe(designTokens.color.light.accent);
    expect(variables['--content-max']).toBe('760px');
    expect(variables['--management-max']).toBe('1200px');
    expect(variables['--radius-control']).toBe('8px');
    expect(variables['--motion-fast']).toBe('120ms');
    expect(ant.token?.colorPrimary).toBe(designTokens.color.light.accent);
    expect(ant.token?.colorBgLayout).toBe(designTokens.color.light.background);
  });

  it('applies a complete theme to the document root without a second palette', () => {
    applyDesignTokens('dark');

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.style.getPropertyValue('--accent')).toBe(
      designTokens.color.dark.accent,
    );
    expect(document.documentElement.style.getPropertyValue('--dur')).toBe(
      'var(--motion-base)',
    );
  });
});
