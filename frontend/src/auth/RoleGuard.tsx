import { Navigate } from 'react-router-dom';
import { ReactNode } from 'react';
import { useAuth } from './AuthProvider';

/**
 * ProtectedRoute — guards routes requiring authentication only.
 * (Same as V3.8, but with cleaner API)
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

/**
 * RoleGuard — V4.0 RBAC component that gates routes by role or permission.
 *
 * Phase 2 dual-authorization: checks RBAC roles/permissions AND
 * falls back to is_hr_admin for backward compatibility.
 *
 * P1-1: Also checks role_level field — some backend responses return
 * role_level='admin' but roles=[], which would incorrectly deny access.
 * RoleGuard now matches via roles array OR role_level string.
 *
 * Usage:
 *   <RoleGuard requiredRole="hr"><KnowledgeBasePage /></RoleGuard>
 *   <RoleGuard requiredRole="admin"><AdminDashboardPage /></RoleGuard>
 *   <RoleGuard requiredPermission="user.read"><UserList /></RoleGuard>
 */
interface RoleGuardProps {
  requiredRole?: 'hr' | 'admin';
  requiredPermission?: string;
  children: ReactNode;
  fallback?: ReactNode;
}

export function RoleGuard({
  requiredRole,
  requiredPermission,
  children,
  fallback,
}: RoleGuardProps) {
  const { user } = useAuth();

  // Not authenticated — redirect to login
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Superuser bypasses all role/permission checks
  const hasAccess = checkAccess(user, requiredRole, requiredPermission);

  if (!hasAccess) {
    // If fallback provided, show it; otherwise redirect to chat (not crash)
    return fallback ? <>{fallback}</> : <Navigate to="/chat" replace />;
  }

  return <>{children}</>;
}

/**
 * Check if user has access based on role/permission requirements.
 * Phase 2 dual-authorization: RBAC OR is_hr_admin fallback.
 * P1-1: Also checks role_level field for admin/superadmin matching.
 */
function checkAccess(
  user: { roles: string[]; permissions: string[]; is_hr_admin: boolean; role_level?: string },
  requiredRole?: string,
  requiredPermission?: string,
): boolean {
  // Check role requirement
  if (requiredRole) {
    if (user.roles.includes(requiredRole)) return true;
    // P1-1: Also match via role_level field (admin/superadmin → admin access)
    if (requiredRole === 'admin' && (user.role_level === 'admin' || user.role_level === 'superadmin')) return true;
    // Phase 2 fallback: is_hr_admin = hr equivalent
    if (requiredRole === 'hr' && user.is_hr_admin) return true;
    // admin includes all hr permissions, so admin users can access hr-only pages
    if (requiredRole === 'hr' && user.roles.includes('admin')) return true;
    // P1-1: superadmin also includes hr access
    if (requiredRole === 'hr' && (user.role_level === 'admin' || user.role_level === 'superadmin')) return true;
  }

  // Check permission requirement
  if (requiredPermission) {
    if (user.permissions.includes(requiredPermission)) return true;
    // Phase 2 fallback: is_hr_admin grants content-domain permissions
    if (user.is_hr_admin) {
      const contentResources = ['document', 'category', 'template', 'workflow', 'audit'];
      const resource = requiredPermission.split('.')[0];
      if (contentResources.includes(resource)) return true;
    }
    // P1-1: admin/superadmin role_level grants all permissions
    if (user.role_level === 'admin' || user.role_level === 'superadmin') {
      return true;
    }
  }

  // If no specific requirement, just check authentication
  if (!requiredRole && !requiredPermission) return true;

  return false;
}
