/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useState, useEffect, useMemo } from 'react';

export interface Breakpoints {
  xs: boolean; // < 576px
  sm: boolean; // < 768px
  md: boolean; // < 1024px
  lg: boolean; // < 1280px
  xl: boolean; // >= 1280px
}

/**
 * P1-7: Unified responsive breakpoint hook.
 * Replaces scattered window.innerWidth checks across components.
 */
export function useBreakpoint(): Breakpoints {
  const [width, setWidth] = useState(() => window.innerWidth);

  useEffect(() => {
    const handler = () => setWidth(window.innerWidth);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  return useMemo(() => ({
    xs: width < 576,
    sm: width < 768,
    md: width < 1024,
    lg: width < 1280,
    xl: width >= 1280,
  }), [width]);
}
