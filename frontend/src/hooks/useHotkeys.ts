import { useEffect, useRef } from 'react';

export interface Hotkey {
  /** single key, case-insensitive, e.g. 'k', 'b', 'o' */
  key: string;
  /** require Cmd (mac) or Ctrl (win/linux) */
  meta?: boolean;
  shift?: boolean;
  handler: (e: KeyboardEvent) => void;
  /** allow the shortcut to fire while an input/textarea is focused (default false) */
  allowInInput?: boolean;
}

function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable;
}

/**
 * Global keyboard shortcuts. Binds a single window listener and reads the latest
 * bindings via a ref, so passing a fresh array each render does not re-bind.
 */
export function useHotkeys(hotkeys: Hotkey[]) {
  const ref = useRef(hotkeys);
  ref.current = hotkeys;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      for (const hk of ref.current) {
        const metaMatch = hk.meta ? (e.metaKey || e.ctrlKey) : (!e.metaKey && !e.ctrlKey);
        const shiftMatch = hk.shift ? e.shiftKey : !e.shiftKey;
        if (e.key.toLowerCase() === hk.key.toLowerCase() && metaMatch && shiftMatch) {
          if (!hk.allowInInput && isEditable(e.target)) continue;
          e.preventDefault();
          hk.handler(e);
          return;
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}
