// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { ProtectedRoute } from './ProtectedRoute';

vi.mock('./AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: false }),
}));

function LoginLocation() {
  const location = useLocation();
  return <span data-testid="login-location">{`${location.pathname}${location.search}`}</span>;
}

describe('ProtectedRoute', () => {
  it('preserves the exact same-origin route as an encoded next target', () => {
    render(
      <MemoryRouter initialEntries={['/workspace/space-1/manage/members?state=pending']}>
        <Routes>
          <Route path="/login" element={<LoginLocation />} />
          <Route
            path="*"
            element={(
              <ProtectedRoute>
                <div>Secret</div>
              </ProtectedRoute>
            )}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId('login-location').textContent).toBe(
      '/login?next=%2Fworkspace%2Fspace-1%2Fmanage%2Fmembers%3Fstate%3Dpending',
    );
  });
});
