import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

interface User {
  id: string;
  email: string;
  username: string;
  is_hr_admin: boolean;
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
  login: (data: { token: string; user: User }) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    // Try to restore from localStorage
    try {
      const saved = localStorage.getItem('ey-auth');
      if (saved) {
        return JSON.parse(saved);
      }
    } catch {
      // ignore
    }
    return { isAuthenticated: false, user: null, token: null };
  });

  const login = useCallback(({ token, user }: { token: string; user: User }) => {
    const newState: AuthState = { isAuthenticated: true, user, token };
    setState(newState);
    localStorage.setItem('ey-auth', JSON.stringify(newState));
  }, []);

  const logout = useCallback(() => {
    setState({ isAuthenticated: false, user: null, token: null });
    localStorage.removeItem('ey-auth');
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
