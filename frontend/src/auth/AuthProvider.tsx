/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import apiClient from '../api/client';

interface AdminScope {
  org_ids: string[];
  business_line_ids: string[];
}

interface User {
  id: string;
  email: string;
  username: string;
  is_hr_admin: boolean;       // Phase 2 dual-authorization: kept for backward compat
  is_superuser?: boolean;     // V4.0: Admin system domain check in AppLayout
  roles: string[];             // V4.0: ['hr'] or ['admin'] or []
  permissions: string[];       // V4.0: ['document.create', 'category.read', ...]
  language_preference: string;
  service_line?: string;
  office_location?: string;
  role_level?: string;
  // V7.0 platform/organization admin scope (axis one — who you are in the org).
  is_super_admin?: boolean;
  is_org_admin?: boolean;
  is_business_admin?: boolean;
  admin_scope?: AdminScope;
}

/** V7.0: is this user any kind of admin (platform / org / business line)? */
export function isAnyAdmin(user?: User | null): boolean {
  if (!user) return false;
  return Boolean(
    user.is_super_admin || user.is_org_admin || user.is_business_admin ||
    user.is_superuser || user.roles?.includes('admin')
  );
}

interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  token: string | null;
}

interface AuthContextType extends AuthState {
  // Login accepts Partial<User> because auth responses may omit optional profile fields.
  // V7.0 authorization comes from backend roles/permissions and admin-scope flags only.
  login: (data: { token: string; user: Partial<User> & { id: string; email: string } }) => void;
  logout: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    // Try to restore from localStorage
    try {
      const saved = localStorage.getItem('ey-auth');
      if (saved) {
        const parsed = JSON.parse(saved);
        // V4.0 migration: if old format lacks roles/permissions, derive from is_hr_admin
        // V7.0: role_level is display metadata only and must not grant access.
        if (parsed.user && !parsed.user.roles) {
          parsed.user.roles = parsed.user.is_hr_admin ? ['hr'] : [];
          parsed.user.permissions = []; // Will be populated on next login
        }
        if (parsed.user && parsed.user.roles?.length === 0 && parsed.user.is_hr_admin) {
          parsed.user.roles = ['hr'];
        }
        return parsed;
      }
    } catch {
      // ignore
    }
    return { isAuthenticated: false, user: null, token: null };
  });

  const login = useCallback(({ token, user }: { token: string; user: Partial<User> & { id: string; email: string } }) => {
    // V4.0: Ensure roles/permissions are present (backend now provides them)
    // V7.0: Never derive authorization from role_level; it is only org metadata.
    let derivedRoles = user.roles || [];
    // If still empty but is_hr_admin, add 'hr' role
    if (derivedRoles.length === 0 && user.is_hr_admin) {
      derivedRoles = ['hr'];
    }

    const enrichedUser: User = {
      id: user.id,
      email: user.email,
      username: user.username ?? '',
      is_hr_admin: user.is_hr_admin ?? false,
      is_superuser: user.is_superuser ?? false,
      roles: derivedRoles,
      permissions: user.permissions || [],
      language_preference: user.language_preference ?? 'zh',
      service_line: user.service_line,
      office_location: user.office_location,
      role_level: user.role_level,
      // V7.0 admin scope flags (carried through for the admin console gate)
      is_super_admin: user.is_super_admin ?? false,
      is_org_admin: user.is_org_admin ?? false,
      is_business_admin: user.is_business_admin ?? false,
      admin_scope: user.admin_scope ?? { org_ids: [], business_line_ids: [] },
    };
    const newState: AuthState = { isAuthenticated: true, user: enrichedUser, token };
    setState(newState);
    localStorage.setItem('ey-auth', JSON.stringify(newState));
  }, []);

  // V4.1 BUG-014: logout now only clears local state on successful API response.
  // Previously, logout always cleared isAuthenticated + navigated to /login, even on API failure.
  // If the /login page has a rendering issue, the user is stuck. Now:
  // - API success → clear state + return true (caller navigates to /login)
  // - API failure → don't clear isAuthenticated, return false (caller shows error toast)
  // ProtectedRoute only redirects when isAuthenticated=false, which only happens on success.
  // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-014]
  const logout = useCallback(async (): Promise<boolean> => {
    try {
      await apiClient.post('/auth/logout/');
      // Success: clear local state
      setState({ isAuthenticated: false, user: null, token: null });
      localStorage.removeItem('ey-auth');
      return true;
    } catch {
      // Failure: do NOT clear local state — user stays on current page
      // They can try logging out again. ProtectedRoute stays engaged.
      return false;
    }
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
