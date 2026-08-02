import { describe, expect, it } from 'vitest';

import messageBubbleSource from '../components/chat/MessageBubble.tsx?raw';
import chatPageSource from '../pages/ChatPage.tsx?raw';
import adminLayoutSource from '../layout/AdminLayout.tsx?raw';
import appLayoutSource from '../layout/AppLayout.tsx?raw';
import loginSource from '../auth/LoginPage.tsx?raw';
import scopedConsoleSource from '../layout/ScopedConsoleLayout.tsx?raw';
import responsiveWorkbenchSource from '../layout/ResponsiveWorkbenchShell.tsx?raw';
import historySource from '../pages/HistoryPage.tsx?raw';
import adminQualitySource from '../pages/admin/AdminQualityPage.tsx?raw';
import adminTemplatesSource from '../pages/admin/AdminTemplatesPage.tsx?raw';
import scopedQualitySource from '../pages/console/ScopedQualityPage.tsx?raw';
import legacyTokens from '../styles/tokens.css?raw';

describe('design-system convergence', () => {
  it('keeps the legacy token stylesheet from becoming a second palette', () => {
    expect(legacyTokens).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(legacyTokens).not.toContain('--accent:');
  });

  it('makes login a token-led static surface', () => {
    expect(loginSource).not.toMatch(/whileHover|whileTap|linear-gradient|radial-gradient|ambientGlow/);
    expect(loginSource).not.toContain("from 'framer-motion'");
    expect(loginSource).toContain('kp-login');
  });

  it('uses the shared management workbench shell', () => {
    expect(scopedConsoleSource).toContain('ResponsiveWorkbenchShell');
    expect(adminLayoutSource).toContain('ResponsiveWorkbenchShell');
    expect(responsiveWorkbenchSource).toContain('useBreakpoint');
    expect(appLayoutSource).toContain('useBreakpoint');
    expect(responsiveWorkbenchSource).toContain("variant: WorkbenchVariant");
  });

  it('keeps application transitions inside the 120/180/240ms motion scale', () => {
    const transitionSources = [appLayoutSource, adminLayoutSource, chatPageSource, messageBubbleSource];

    for (const source of transitionSources) {
      expect(source).not.toMatch(/duration:\s*0\.(?:3|4|6)/);
      expect(source).not.toMatch(/scale:\s*0\.98|scale:\s*1\b/);
      expect(source).not.toContain('transition: \'all');
    }
  });

  it('migrates the primary history, quality, and template surfaces to shared primitives', () => {
    expect(historySource).toContain('EmptyState');
    expect(scopedQualitySource).toContain('PageHeader');
    expect(adminQualitySource).toContain('PageHeader');
    expect(adminTemplatesSource).toContain('PageHeader');
  });
});
