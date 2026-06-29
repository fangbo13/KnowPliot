import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import apiClient from '../api/client';

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
}

interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  token: string | null;
}

interface AuthContextType extends AuthState {
  // P1-1: login accepts Partial<User> for roles/permissions because the login
  // function enriches the user object by deriving roles from role_level if needed.
  // LoginPage.tsx may not always include roles/permissions from the profile API,
  // but the enrichment logic in login() fills in the gaps.
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
        // P1-1: Also derive from role_level if roles are empty (admin role_level → roles=['admin'])
        if (parsed.user && !parsed.user.roles) {
          parsed.user.roles = parsed.user.is_hr_admin ? ['hr'] : [];
          parsed.user.permissions = []; // Will be populated on next login
        }
        // P1-1: If roles array is empty but role_level exists, derive roles from it
        if (parsed.user && parsed.user.roles?.length === 0 && parsed.user.role_level) {
          const roleLevelMap: Record<string, string[]> = {
            'admin': ['admin'],
            'superadmin': ['admin', 'superadmin'],
            'hr': ['hr'],
            'employee': [],
          };
          parsed.user.roles = roleLevelMap[parsed.user.role_level] || [parsed.user.role_level];
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
    // P1-1: Also derive roles from role_level if roles array is empty.
    // Some backend responses return role_level='admin' but roles=[], which
    // causes RoleGuard to deny access. Map role_level to roles as fallback.
    let derivedRoles = user.roles || [];
    if (derivedRoles.length === 0 && user.role_level) {
      // Map role_level to roles array for RoleGuard compatibility
      const roleLevelMap: Record<string, string[]> = {
        'admin': ['admin'],
        'superadmin': ['admin', 'superadmin'],
        'hr': ['hr'],
        'employee': [],
      };
      derivedRoles = roleLevelMap[user.role_level] || [user.role_level];
    }
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
