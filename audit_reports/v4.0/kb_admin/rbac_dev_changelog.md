# V4.0 RBAC 双轨权限系统 — 开发变更日志

> [来源: V4.0/kb_admin/权限架构与功能规划.md §权限矩阵]
> [来源: V4.0/kb_admin/v4.0_rbac_综合审计报告.md §架构方案]

## 变更概要

V3.8 的 `is_hr_admin: boolean` 单一标志 → V4.0 的 Role-Permission-UserRole 三层 RBAC 模型。
HR（内容域）和 Admin（系统域）双轨权限，35 个 codename，9 个新增审计动作。

---

## 后端变更

### 1. 新增 Django App: `apps/rbac/`

| 文件 | 说明 |
|------|------|
| `apps/rbac/models.py` | 4 个 RBAC 模型: Role, Permission, RolePermission, UserRole |
| `apps/rbac/serializers.py` | Role/Permission/UserRole/RolePermission serializers |
| `apps/rbac/views.py` | 10 个 API endpoints (RBAC 管理 + 用户管理) |
| `apps/rbac/urls.py` | `/api/v1/rbac/` 路由注册 |
| `apps/rbac/admin.py` | Django admin 注册 |
| `apps/rbac/management/commands/seed_rbac.py` | Seed 命令 (2 Role + 35 Permission + RolePermission 映射) |
| `apps/rbac/migrations/0001_initial.py` | 数据库迁移 |

### 2. 扩展 User 模型 (`apps/users/models.py`)

新增方法：
- `has_role(role_name)` — 检查用户是否拥有指定角色，Phase 2 双授权窗口回退到 `is_hr_admin`
- `has_permission(codename)` — 检查用户是否拥有指定权限 codename
- `get_permissions()` — 返回用户所有活跃权限 codename 的 set

### 3. 权限类重构 (`apps/core/permissions.py`)

- `IsHROrAdmin` — Phase 2: RBAC role OR `is_hr_admin` OR `is_superuser`
- `HasPermission(codename)` — 新增，检查指定 codename
- `HasRole(role_name)` — 新增，检查指定角色

### 4. 修复 CategoryListView (`apps/knowledge/views.py`)

**安全漏洞**: POST 只用 `IsAuthenticated`，任何登录用户可创建分类
**修复**: `get_permissions()` 分离 GET/POST — POST 需要 `IsHROrAdmin`

### 5. AuditLog 扩展 (`apps/audit/models.py`)

新增 9 个 ACTION_CHOICES: `role_assign`, `role_revoke`, `user_create`, `user_update`, `user_deactivate`, `config_change`, `system_health_view`, `audit_export`, `role_change_log`
新增字段: `role_used` CharField(max_length=20) — 双角色审计追踪

### 6. JWT Token 增强 (`apps/users/views.py`)

`CustomTokenObtainPairSerializer` — 登录响应增加:
- `user.roles`: ["admin", "hr"] / ["hr"] / []
- `user.permissions`: [全部 codename 列表]

### 7. UserSerializer 扩展 (`apps/users/serializers.py`)

新增字段: `roles` (SerializerMethodField), `permissions` (SerializerMethodField)
新增 serializer: `UserManageSerializer` (Admin 用户管理专用)

### 8. URL 路由更新 (`config/urls.py`)

新增: `path("api/v1/rbac/", include("apps.rbac.urls"))`

### 9. Settings 注册 (`config/settings/base.py`)

LOCAL_APPS 增加 `"apps.rbac"`

---

## 前端变更

### 1. AuthProvider 重构 (`frontend/src/auth/AuthProvider.tsx`)

V3.8: `{ is_hr_admin: boolean }`
V4.0: `{ roles: string[]; permissions: string[]; is_hr_admin: boolean }`
Phase 2 回退: 旧格式 localStorage 自动迁移

### 2. RoleGuard 组件 (`frontend/src/auth/RoleGuard.tsx`)

新增组件:
- `RoleGuard requiredRole="hr"` — 需要 HR 或 Admin 角色
- `RoleGuard requiredRole="admin"` — 需要 Admin 角色
- `RoleGuard requiredPermission="user.read"` — 需要指定权限
- Phase 2 回退: `is_hr_admin` 等价于 hr 角色

### 3. 双轨侧边栏 (`frontend/src/layout/AppLayout.tsx`)

userMenu 重构:
- HR/Admin: 显示 "知识库" 入口 (`/admin/knowledge`)
- Admin only: 显示 "Admin Dashboard" 入口 (`/admin/dashboard`)
- Employee: 只显示设置 + 退出

### 4. AdminDashboardPage (`frontend/src/pages/admin/AdminDashboardPage.tsx`)

新增页面:
- 左侧: 用户列表表格 (email, username, **Role**, service_line, active status)
- 右侧: System Health panel (backend/celery/db status + 用户统计)

### 5. App.tsx 路由 (`frontend/src/App.tsx`)

新增路由:
- `/admin/knowledge` — `<RoleGuard requiredRole="hr">`
- `/admin/dashboard` — `<RoleGuard requiredRole="admin">`

---

## 测试用户

| 用户 | 邮箱 | 密码 | 角色 | 权限数 |
|------|------|------|------|---------|
| admin | admin@test.ey.com | Admin123! | admin + hr | 35 |
| hr_user | hr@test.ey.com | Hr123! | hr | 21 |
| employee | employee@test.ey.com | Emp123! | none | 0 |

---

## API 端点验证

| 端点 | Admin | HR | Employee |
|------|-------|----|---------|
| `/api/v1/rbac/roles/` | ✓ 200 | ✗ 403 | ✗ 403 |
| `/api/v1/rbac/permissions/` | ✓ 200 | ✗ 403 | ✗ 403 |
| `/api/v1/rbac/users/` | ✓ 200 (3 users) | ✗ 403 | ✗ 403 |
| `/api/v1/auth/token/` | ✓ roles+perms | ✓ roles+perms | ✓ empty |
