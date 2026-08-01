// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import KnowledgeSpacesPage from './KnowledgeSpacesPage';

const navigate = vi.fn();
const setActiveSpace = vi.fn().mockResolvedValue(undefined);

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});
vi.mock('../store/spaceStore', () => ({
  useSpaceStore: () => ({
    spaces: [
      { id: 'guest-space', name: 'Guest Space', description: 'Read only', my_role: 'guest' },
      { id: 'owner-space', name: 'Owner Space', description: 'Managed', my_role: 'owner' },
    ],
    loading: false,
    error: null,
    loadSpaces: vi.fn(),
    setActiveSpace,
  }),
}));

describe('KnowledgeSpacesPage', () => {
  afterEach(cleanup);
  beforeEach(() => {
    navigate.mockClear();
    setActiveSpace.mockClear();
    localStorage.clear();
  });

  it('requires selecting a space before entering knowledge', async () => {
    render(<MemoryRouter><KnowledgeSpacesPage /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'knowledge_spaces_title' })).toBeTruthy();
    fireEvent.click(screen.getAllByRole('button', { name: 'knowledge_spaces_enter' })[1]);

    await waitFor(() => expect(setActiveSpace).toHaveBeenCalledWith('owner-space'));
    expect(navigate).toHaveBeenCalledWith('/workspace/owner-space/knowledge');
  });

  it('shows management only for a manageable space', () => {
    render(<MemoryRouter><KnowledgeSpacesPage /></MemoryRouter>);

    expect(screen.getAllByRole('link', { name: /knowledge_spaces_manage/ })).toHaveLength(1);
  });
});
