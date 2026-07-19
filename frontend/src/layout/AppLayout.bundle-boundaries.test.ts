import { describe, expect, it } from 'vitest';

import mainSource from '../main.tsx?raw';
import chatPageSource from '../pages/ChatPage.tsx?raw';
import appLayoutSource from './AppLayout.tsx?raw';

describe('authenticated chat bundle boundaries', () => {
  it('keeps global bootstrap independent from Ant Design and Framer Motion', () => {
    expect(mainSource).not.toContain("from 'antd'");
    expect(mainSource).not.toContain("from 'framer-motion'");
  });

  it('keeps the interactive chat route free of eager Ant Design modules', () => {
    expect(chatPageSource).not.toContain("from 'antd'");
    expect(chatPageSource).toContain("from '../utils/notifications'");
  });

  it.each([
    '../components/SpaceSwitcher',
    '../components/NotificationBell',
    '../components/chat/SessionRenameModal',
    '../components/CommandPalette',
  ])('loads shell enhancement %s through a literal lazy import', (modulePath) => {
    expect(appLayoutSource).toContain(`lazy(() => import('${modulePath}'))`);
    expect(appLayoutSource).not.toContain(`from '${modulePath}'`);
  });

  it('does not make Ant Design or Framer Motion part of the route shell', () => {
    expect(appLayoutSource).not.toContain("from 'antd'");
    expect(appLayoutSource).not.toContain("from 'framer-motion'");
  });
});
