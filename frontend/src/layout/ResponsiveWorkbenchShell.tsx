import { CloseOutlined, MenuOutlined } from '@ant-design/icons';
import type { ReactNode } from 'react';
import { useEffect, useId, useRef, useState } from 'react';

import { useBreakpoint } from '../hooks/useBreakpoint';

type WorkbenchVariant = 'admin' | 'console';

interface ResponsiveWorkbenchShellProps {
  variant: WorkbenchVariant;
  routeKey: string;
  navigationLabel: string;
  menuLabel: string;
  closeLabel: string;
  sidebar: ReactNode;
  topbar: ReactNode;
  children: ReactNode;
}

export default function ResponsiveWorkbenchShell({
  variant,
  routeKey,
  navigationLabel,
  menuLabel,
  closeLabel,
  sidebar,
  topbar,
  children,
}: ResponsiveWorkbenchShellProps) {
  const { sm: isMobile } = useBreakpoint();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const navigationId = useId();
  const navigationRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const wasNavigationOpen = useRef(false);

  useEffect(() => {
    setNavigationOpen(false);
  }, [routeKey]);

  useEffect(() => {
    if (!isMobile || !navigationOpen) return undefined;

    const handleDrawerKeyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setNavigationOpen(false);
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = Array.from(navigationRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary',
      ) ?? []);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleDrawerKeyboard);
    return () => document.removeEventListener('keydown', handleDrawerKeyboard);
  }, [isMobile, navigationOpen]);

  useEffect(() => {
    if (isMobile && navigationOpen) {
      closeButtonRef.current?.focus();
    } else if (wasNavigationOpen.current) {
      menuButtonRef.current?.focus();
    }
    wasNavigationOpen.current = isMobile && navigationOpen;
  }, [isMobile, navigationOpen]);

  const sidebarClassName = `kp-workbench-sidebar kp-${variant}-sidebar`;
  const sidebarNode = (
    <aside
      ref={navigationRef}
      id={navigationId}
      className={sidebarClassName}
      {...(isMobile ? {
        role: 'dialog',
        'aria-modal': true,
        'aria-label': navigationLabel,
      } : {})}
    >
      {isMobile && (
        <button
          ref={closeButtonRef}
          type="button"
          className="icon-btn kp-workbench-drawer__close"
          aria-label={closeLabel}
          onClick={() => setNavigationOpen(false)}
        >
          <CloseOutlined />
        </button>
      )}
      {sidebar}
    </aside>
  );

  return (
    <div className={`kp-workbench-layout kp-${variant}-layout`}>
      {isMobile ? (
        navigationOpen && (
          <div className="kp-workbench-drawer-layer">
            <button
              type="button"
              className="kp-workbench-drawer__backdrop"
              aria-hidden="true"
              tabIndex={-1}
              onClick={() => setNavigationOpen(false)}
            />
            {sidebarNode}
          </div>
        )
      ) : sidebarNode}

      <div className={`kp-workbench-main kp-${variant}-main`}>
        <header className={`kp-workbench-topbar kp-${variant}-topbar`}>
          {isMobile && (
            <button
              ref={menuButtonRef}
              type="button"
              className="icon-btn kp-workbench-menu-toggle"
              aria-label={menuLabel}
              aria-controls={navigationId}
              aria-expanded={navigationOpen}
              onClick={() => setNavigationOpen(true)}
            >
              <MenuOutlined />
            </button>
          )}
          {topbar}
        </header>
        <main className={`kp-workbench-content kp-${variant}-content`}>
          {children}
        </main>
      </div>
    </div>
  );
}
