/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useState, useEffect, useCallback } from 'react';

import { applyDesignTokens } from '../design/tokens';

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
  applyDesignTokens(sharedEffective);
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
