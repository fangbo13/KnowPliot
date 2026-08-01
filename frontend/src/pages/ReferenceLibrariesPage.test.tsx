// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { libraryApi } from '../api/knowledge';
import ReferenceLibrariesPage from './ReferenceLibrariesPage';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../api/knowledge', () => ({
  libraryApi: {
    catalog: vi.fn(),
    favorite: vi.fn(),
    unfavorite: vi.fn(),
  },
}));

describe('ReferenceLibrariesPage', () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.mocked(libraryApi.catalog).mockResolvedValue([
      { id: 'lib-1', name: 'IFRS', description: 'Standards', category: 'ifrs', is_official: true, is_favorite: true, favorite_position: 1 },
      { id: 'lib-2', name: 'Tax', description: 'Tax rules', category: 'tax', is_official: true, is_favorite: true, favorite_position: 2 },
      { id: 'lib-3', name: 'Audit', description: 'Audit guide', category: 'audit', is_official: true, is_favorite: true, favorite_position: 3 },
      { id: 'lib-4', name: 'Legal', description: 'Legal guide', category: 'legal', is_official: true, is_favorite: true, favorite_position: 4 },
      { id: 'lib-5', name: 'ESG', description: 'ESG guide', category: 'esg', is_official: true, is_favorite: true, favorite_position: 5 },
      { id: 'lib-6', name: 'Industry', description: 'Industry guide', category: 'industry', is_official: true, is_favorite: false, favorite_position: null },
    ] as never);
    vi.mocked(libraryApi.favorite).mockResolvedValue({} as never);
  });

  it('shows every official library while exposing the five-library favorite boundary', async () => {
    render(<ReferenceLibrariesPage />);

    expect(await screen.findByRole('heading', { name: 'IFRS' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Industry' })).toBeTruthy();
    expect(screen.getByText('reference_libraries_favorite_count')).toBeTruthy();
    expect((screen.getByRole('button', {
      name: 'reference_libraries_replace_required',
    }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('lets the user remove a favorite before adding its replacement', async () => {
    vi.mocked(libraryApi.catalog)
      .mockResolvedValueOnce([
        { id: 'lib-1', name: 'IFRS', description: 'Standards', category: 'ifrs', is_official: true, is_favorite: true, favorite_position: 1 },
        { id: 'lib-2', name: 'Tax', description: 'Tax rules', category: 'tax', is_official: true, is_favorite: false, favorite_position: null },
      ] as never)
      .mockResolvedValueOnce([] as never);
    vi.mocked(libraryApi.unfavorite).mockResolvedValue(undefined);

    render(<ReferenceLibrariesPage />);
    expect(await screen.findByRole('heading', { name: 'IFRS' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'reference_libraries_unfavorite' }));
    await waitFor(() => expect(libraryApi.unfavorite).toHaveBeenCalledWith('lib-1'));
  });
});
