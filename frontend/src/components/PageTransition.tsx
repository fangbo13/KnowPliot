/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { designTokens } from '../design/tokens';

const DURATION = designTokens.motion.duration.base / 1000; // 180ms

/**
 * C2: Route-level page transition wrapper.
 * Wraps <Outlet/> with framer-motion AnimatePresence for smooth 180ms fade+slide.
 * Respects prefers-reduced-motion (animation disabled when user opts in).
 */
export default function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation();
  const reduceMotion = useReducedMotion();

  const variants = reduceMotion
    ? {
        initial: { opacity: 1 },
        animate: { opacity: 1 },
        exit: { opacity: 1 },
      }
    : {
        initial: { opacity: 0, y: 8 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: -8 },
      };

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        initial={variants.initial}
        animate={variants.animate}
        exit={variants.exit}
        transition={{ duration: DURATION, ease: [0.25, 0.8, 0.25, 1] }}
        style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
