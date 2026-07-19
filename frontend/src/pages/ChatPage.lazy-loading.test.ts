import { describe, expect, it } from 'vitest';

import chatPageSource from './ChatPage.tsx?raw';

describe('ChatPage interaction-owned lazy boundaries', () => {
  it.each([
    '../components/chat/VirtualizedMessageList',
    '../components/chat/ProcessingPanel',
  ])('loads %s only behind a literal dynamic import', (modulePath) => {
    expect(chatPageSource).toContain(`lazy(() => import('${modulePath}'))`);
    expect(chatPageSource).not.toContain(`from '${modulePath}'`);
  });

  it('keeps the composer and welcome surface available without a lazy round trip', () => {
    expect(chatPageSource).toContain("import WelcomeScreen from '../components/chat/WelcomeScreen'");
    expect(chatPageSource).toContain("import ChatComposer from '../components/chat/ChatComposer'");
  });
});
