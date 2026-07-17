// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Capability } from '../../api/capabilities';
import { documentApi } from '../../api/documents';
import { useAuthorization } from '../../auth/CapabilityProvider';
import KnowledgeBasePage from './KnowledgeBasePage';

const granted = new Set<Capability>();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../auth/CapabilityProvider', () => ({ useAuthorization: vi.fn() }));

vi.mock('../../api/documents', async () => {
  const actual = await vi.importActual<typeof import('../../api/documents')>('../../api/documents');
  return {
    ...actual,
    documentApi: {
      getDocuments: vi.fn(),
      uploadDocument: vi.fn(),
      downloadDocument: vi.fn(),
      reindexDocument: vi.fn(),
      archiveDocument: vi.fn(),
    },
  };
});

const documentRecord = {
  id: 'doc-1',
  title: 'Employee handbook',
  file_type: 'pdf',
  status: 'active',
  chunk_count: 4,
  category_name: 'People',
  created_at: '2026-07-17',
};

function setCapabilities(capabilities: Capability[]) {
  granted.clear();
  capabilities.forEach((capability) => granted.add(capability));
}

describe('KnowledgeBasePage capability actions', () => {
  beforeAll(() => {
    const getComputedStyle = window.getComputedStyle;
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element) => getComputedStyle(element));
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockReturnValue({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    });
  });

  beforeEach(() => {
    setCapabilities([]);
    vi.mocked(useAuthorization).mockReturnValue({
      enabled: true,
      status: 'ready',
      snapshot: null,
      has: (capability) => granted.has(capability),
      hasAny: (capabilities) => capabilities.some((capability) => granted.has(capability)),
      hasAll: (capabilities) => capabilities.every((capability) => granted.has(capability)),
      defaultConsole: '/chat',
    });
    vi.mocked(documentApi.getDocuments).mockReset().mockResolvedValue({ results: [documentRecord] });
    vi.mocked(documentApi.uploadDocument).mockReset();
    vi.mocked(documentApi.downloadDocument).mockReset();
    vi.mocked(documentApi.reindexDocument).mockReset();
    vi.mocked(documentApi.archiveDocument).mockReset();
  });

  afterEach(cleanup);

  it('does not load or expose knowledge data without knowledge.read', () => {
    render(<KnowledgeBasePage />);

    expect(documentApi.getDocuments).not.toHaveBeenCalled();
    expect(screen.queryByText('Employee handbook')).toBeNull();
    expect(screen.queryByRole('button', { name: 'upload' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'download' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'reindex' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'archive' })).toBeNull();
  });

  it('keeps a knowledge.read-only view free of mutation, indexing, and download actions', async () => {
    setCapabilities(['knowledge.read']);

    render(<KnowledgeBasePage />);

    await waitFor(() => expect(screen.getByText('Employee handbook')).toBeTruthy());
    expect(screen.getByRole('button', { name: 'refresh' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'upload' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'download' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'reindex' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'archive' })).toBeNull();
  });

  it.each([
    ['knowledge.download', 'download', ['upload', 'reindex', 'archive']],
    ['knowledge.index', 'reindex', ['upload', 'download', 'archive']],
    ['knowledge.manage', 'upload', ['download', 'reindex']],
  ] as const)(
    'exposes only the action family granted by %s',
    async (capability, visibleAction, hiddenActions) => {
      setCapabilities(['knowledge.read', capability]);

      render(<KnowledgeBasePage />);

      await waitFor(() => expect(screen.getByText('Employee handbook')).toBeTruthy());
      expect(screen.getByRole('button', { name: visibleAction })).toBeTruthy();
      hiddenActions.forEach((action) => {
        expect(screen.queryByRole('button', { name: action })).toBeNull();
      });
      if (capability === 'knowledge.manage') {
        expect(screen.getByRole('button', { name: 'archive' })).toBeTruthy();
      }
    },
  );
});
