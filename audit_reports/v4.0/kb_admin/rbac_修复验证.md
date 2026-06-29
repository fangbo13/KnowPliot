# V4.0 RBAC 双轨权限 — 修复验证报告

> [来源: V4.0/kb_admin/权限安全_gap_list.md §P0漏洞]
> [来源: V4.0/kb_admin/v4.0_rbac_综合审计报告.md §验证计划]

## 服务环境

| 服务 | 地址 | 状态 |
|------|------|------|
| PostgreSQL + pgvector | localhost:5432 | ✓ Healthy |
| Redis | localhost:6379 | ✓ Healthy |
| Django Backend | http://127.0.0.1:8000 | ✓ Running |
| Celery Worker | (内部) | ✓ Running |
| React Frontend | http://127.0.0.1:3003 | ✓ Running |

---

## 一、RBAC Seed 数据验证

### 执行命令
```bash
docker compose exec backend python manage.py seed_rbac
```

### 结果
```
✓ RBAC seed complete: 35 permissions, HR=21 perms, Admin=35 perms
```

- Role `hr` = 21 codenames (content domain)
- Role `admin` = 35 codenames (system domain, includes all HR)
- Permission `action` field: max_length=30 (修复了 varchar(20) 越界)

---

## 二、JWT Token 登录验证

### Admin 用户登录
```powershell
POST /api/v1/auth/token/ {email: "admin@test.ey.com", password: "Admin123!"}
```

**响应包含**:
```json
{
  "user": {
    "roles": ["admin", "hr"],
    "permissions": ["document.create", "document.read", ..., "health.view"]  // 35个
  }
}
```
✓ **验证通过**: Admin 获得 admin+hr 双角色，35 个权限 codename

### HR 用户登录
```powershell
POST /api/v1/auth/token/ {email: "hr@test.ey.com", password: "Hr123!"}
```

**响应包含**:
```json
{
  "user": {
    "roles": ["hr"],
    "permissions": ["document.create", "category.read", ..., "audit.view_content"]  // 21个
  }
}
```
✓ **验证通过**: HR 获得 hr 单角色，21 个权限 codename

### Employee 用户登录
```powershell
POST /api/v1/auth/token/ {email: "employee@test.ey.com", password: "Emp123!"}
```

**响应包含**:
```json
{
  "user": {
    "roles": [],
    "permissions": []  // 0个
  }
}
```
✓ **验证通过**: Employee 无管理角色和权限

---

## 三、权限越权验证 (403 Forbidden)

### 测试: Employee 尝试访问 Admin API

```powershell
# Login as employee → get token
GET /api/v1/rbac/users/ Authorization: Bearer <employee_token>
```

**结果**: `403 Forbidden`
✓ **验证通过**: 普通用户被正确拒绝 Admin API 访问

### 对照: Admin 正常访问

```powershell
GET /api/v1/rbac/users/ Authorization: Bearer <admin_token>
```

**结果**: `200 OK` — 返回 3 行用户数据:
| Email | Username | Roles | is_active |
|-------|----------|-------|-----------|
| admin@test.ey.com | admin | ["admin"] | true |
| employee@test.ey.com | employee | [] | true |
| hr@test.ey.com | hr_user | ["hr"] | true |

✓ **验证通过**: Admin 可正常获取用户列表，表格包含 **Role 列**

---

## 四、安全漏洞修复验证

### CategoryListView POST 权限 (P0 CRITICAL)

**V3.8 问题**: `IsAuthenticated` — 任何登录用户可创建分类
**V4.0 修复**: POST 需要 `IsHROrAdmin`

```python
def get_permissions(self):
    if self.request.method == "POST":
        return [permissions.IsAuthenticated(), IsHROrAdmin()]
    return [permissions.IsAuthenticated()]
```

✓ **验证通过**: Employee 无法 POST 创建分类，HR/Admin 可以

---

## 五、AuditLog 扩展验证

- 新增 9 个 ACTION_CHOICES (role_assign, role_revoke, user_create, ...)
- 新增 `role_used` 字段用于双角色审计追踪
- `create_audit_log()` 函数新增 `role_used` 参数

✓ **迁移通过**: `audit.0003_auditlog_role_used_alter_auditlog_action... OK`

---

## 六、前端验证

### AuthProvider (V4.0)
- `User` 接口新增 `roles: string[]` 和 `permissions: string[]`
- Phase 2 回退: 旧格式 localStorage 自动迁移补充 roles/permissions

### RoleGuard (V4.0)
- `requiredRole="hr"` → HR + Admin 可通过
- `requiredRole="admin"` → Admin only
- Phase 2 回退: `is_hr_admin` 等价于 hr 角色
- 无权限 → 回退到 `/chat` (不崩溃)

### AppLayout 双轨侧边栏
- HR/Admin → 显示 "知识库" 入口
- Admin only → 显示 "Admin Dashboard" 入口
- Employee → 只显示设置 + 退出

✓ **前端代码验证通过** (需浏览器截图验证视觉效果)

---

## 截图验证清单（待执行）

| 截图前缀 | 操作 | 验证要点 |
|----------|------|----------|
| `fixed_v4_kb_hr_ui_` | HR 登录，上传文档 | 列表出现文件名 |
| `fixed_v4_kb_hr_ui_` | 聊天引用 | AI 回复引用上传文件 |
| `fixed_v4_kb_admin_ui_` | Admin 登录，进入后台 | 用户表格 2+ 行 + Role 列 |
| `fixed_v4_kb_sec_` | Employee 访问 Admin API | Network 403 红字 |
