# V4.0 权限安全 Gap List

> **版本**: V4.0 — 双轨 RBAC 安全漏洞与越权风险清单
> **产出路径**: `audit_reports/v4.0/kb_admin/权限安全_gap_list.md`
> **日期**: 2026-06-25

---

## 1. 未鉴权 / 弱鉴权 API 端点

### 1.1 完整端点扫描

> [来源: V3.8/综合审计报告_V3.8.md §API端点] + 代码验证

| # | 端点 | 路径 | 当前权限类 | 风险级别 | 说明 | V4.0 目标权限 |
|---|------|------|-----------|---------|------|-------------|
| 1 | Token 获取 | `POST /api/v1/auth/token/` | 无需鉴权 | ✅ 可接受 | 登录流程必要，设计意图 | 保持不变 |
| 2 | Token 刷新 | `POST /api/v1/auth/token/refresh/` | 无需鉴权 | ✅ 可接受 | 刷新流程必要，设计意图 | 保持不变，但需专项限速 |
| 3 | Token 黑名单/注销 | `POST /api/v1/auth/logout/` | `IsAuthenticated` | ✅ 可接受 | 注销需登录态 | 保持不变 |
| 4 | 获取当前用户 | `GET /api/v1/auth/me/` | `IsAuthenticated` | ⚠️ 中风险 | 返回 `is_hr_admin`，暴露管理员名单 | 移除 `is_hr_admin`，改为 `roles` 字段 |
| 5 | Django Admin | `GET /admin/` | Django `is_staff` | ⚠️ 中风险 | 依赖 `is_staff` 而非 RBAC；若误设 `is_staff`，非管理员可进入 | Phase 3 后逐步关闭，改用 `/api/v1/rbac/*` |
| 6 | Media 文件(DEBUG) | `GET /media/` | 无鉴权 | 🔴 **高风险** | DEBUG 模式下上传文档 PDF 可通过猜测 URL 公开访问 | 生产环境关闭 DEBUG，改用签名 URL |
| 7 | **CategoryListView POST** | `POST /api/v1/documents/categories/` | `IsAuthenticated` 仅 | 🔴 **严重** | 任何登录用户可创建文档分类，无 `IsHROrAdmin` | `HasPermission('category.create')` |
| 8 | CategoryListView GET | `GET /api/v1/documents/categories/` | `IsAuthenticated` 仅 | ⚠️ 中风险 | 任何登录用户可浏览分类结构，信息泄露 | `HasPermission('category.read')` |
| 9 | DocumentListCreateView | `GET/POST /api/v1/documents/` | `IsAuthenticated + IsHROrAdmin` | ✅ 可接受 | 知识库文档有 HR/Admin 闸门 | `HasPermission('document.read/create')` |
| 10 | DocumentDetailView | `GET/PATCH/DELETE /api/v1/documents/<id>/` | `IsAuthenticated + IsHROrAdmin` | ✅ 可接受 | 同上 | `HasPermission('document.read/update/delete')` |
| 11 | DocumentReindexView | `POST /api/v1/documents/<id>/reindex/` | `IsAuthenticated + IsHROrAdmin` | ✅ 可接受 | 同上 | `HasPermission('document.reindex')` |
| 12 | DocumentChunksView | `GET /api/v1/documents/<id>/chunks/` | `IsAuthenticated + IsHROrAdmin` | ✅ 可接受 | 同上 | `HasPermission('document.read_chunks')` |
| 13 | AnswerTemplateListView | `GET/POST /api/v1/documents/templates/` | `IsAuthenticated + IsHROrAdmin` | ✅ 可接受 | 同上 | `HasPermission('template.read/create')` |
| 14 | AnswerTemplateDetailView | `GET/PATCH/DELETE /api/v1/documents/templates/<id>/` | `IsAuthenticated + IsHROrAdmin` | ✅ 可接受 | 同上 | `HasPermission('template.read/update/delete')` |
| 15 | AuditLogListView | `GET /api/v1/audit/logs/` | 未确认 | ⚠️ 待验证 | 审计日志端点需确认权限类 | `HasPermission('audit.view_content')` HR / `HasPermission('audit.view_system')` Admin |

### 1.2 关键漏洞详情

#### 🔴 严重：CategoryListView POST — 无权限闸门

**来源**: [backend/apps/knowledge/views.py](backend/apps/knowledge/views.py#L124)

```python
class CategoryListView(generics.ListCreateAPIView):
    """List and create document categories."""
    serializer_class = DocumentCategorySerializer
    permission_classes = [permissions.IsAuthenticated]  # ← 仅 IsAuthenticated，任何登录用户可创建
```

**影响**: 任何已登录的 Employee 都可以：
- 创建任意文档分类
- 干扰知识库分类体系
- 无审计追踪（仅记录 `category_create` 操作，但不验证权限）

**修复方案**: 替换为 `HasPermission('category.create')` + 分离 GET/POST 权限

---

## 2. 越权风险点

### 2.1 后端越权风险

| # | 风险 | 严重度 | 来源文件 | 详情 | 修复优先级 |
|---|------|--------|---------|------|-----------|
| 1 | `is_hr_admin` 在 UserSerializer 公开暴露 | **中** | [backend/apps/users/serializers.py](backend/apps/users/serializers.py#L22) | `GET /api/v1/auth/me/` 返回 `is_hr_admin: true/false`，任何登录用户可看到全管理员名单 → 信息泄露 | P0 |
| 2 | 无角色分配 API | **高** | — | `is_hr_admin` 只能通过 Django Admin (`/admin/`) 或直接数据库操作设置。无审计追踪，无权限验证流程 | P0 |
| 3 | `IsOwnerOrReadOnly` 死代码 | **低** | [backend/apps/core/permissions.py](backend/apps/core/permissions.py#L15-L21) | 定义但从未引用任何视图。表明权限实现计划未完成 | P2（清理） |
| 4 | HR 可删除任何文档（无对象级权限） | **低** | [backend/apps/knowledge/views.py](backend/apps/knowledge/views.py#L61) | `DocumentDetailView` 无 `has_object_permission` 检查。HR 可删除任何用户上传的文档 | P2（后续加 ownership） |
| 5 | Token 端点无专项限速 | **中** | SimpleJWT 默认配置 | 全局 30/分钟限速过宽。登录暴力破解需更严限速（建议 5/分钟/IP） | P1 |
| 6 | AuditLog.ACTION_CHOICES 缺系统操作 | **高** | [backend/apps/audit/models.py](backend/apps/audit/models.py#L12-L24) | 无法审计 `role_assign`、`user_create`、`config_change` 等系统级操作 | P0 |
| 7 | JWT token 无角色信息 | **中** | SimpleJWT 配置 | JWT payload 仅含 `user_id`，角色变更后旧 token 仍有效直到过期（15分钟） | P1（Phase 3 加角色缓存） |

### 2.2 前端越权风险

| # | 风险 | 严重度 | 来源文件 | 详情 | 修复优先级 |
|---|------|--------|---------|------|-----------|
| 1 | `AuthProvider` 用 `is_hr_admin: boolean` | **中** | [frontend/src/auth/AuthProvider.tsx](frontend/src/auth/AuthProvider.tsx#L8) | `User` 接口仅有 `is_hr_admin: boolean`，无法区分 HR 与 Admin 角色 | P0 |
| 2 | `AppLayout` 用 `user?.is_hr_admin` 判断 | **中** | [frontend/src/layout/AppLayout.tsx](frontend/src/layout/AppLayout.tsx#L115) | 侧边栏仅判断一个布尔值，无法实现双轨菜单（HR vs Admin） | P0 |
| 3 | `LoginPage` 硬编码 `is_hr_admin` | **中** | [frontend/src/auth/LoginPage.tsx](frontend/src/auth/LoginPage.tsx#L52) | 登录时将布尔值写入状态，需改为角色列表解析 | P0 |
| 4 | 无 RoleGuard 组件 | **中** | — | 前端无按角色过滤路由的组件。`/admin/knowledge` 路径任何登录用户手动导航即可访问 → 组件渲染（信息泄露） | P0 |
| 5 | ProtectedRoute 仅检查 `isAuthenticated` | **中** | App.tsx 路由配置 | 路由守卫不验证角色，仅验证登录状态 | P0 |

### 2.3 配置层越权风险

| # | 风险 | 严重度 | 来源 | 详情 | 修复优先级 |
|---|------|--------|------|------|-----------|
| 1 | Django Admin `/admin/` 暴露 | **中** | [backend/config/urls.py](backend/config/urls.py#L9) | Django 内置 admin 在 `/admin/` 路径暴露，使用 `is_staff` 而非 RBAC | P1（Phase 3 逐步关闭） |
| 2 | DEBUG 模式 Media 无鉴权 | **高** | [backend/config/urls.py](backend/config/urls.py#L16-L17) | `if settings.DEBUG: urlpatterns += static(...)` — 上传文档通过猜测 URL 可公开访问 | P0（生产关闭 DEBUG） |
| 3 | CORS 配置待验证 | **低** | config/settings/base.py | 需确认 CORS 允许的域名列表是否过宽 | P2 |

> [来源: V3.8/Bug清单汇总_V3.8.md §安全漏洞] — V3.8 已识别部分安全漏洞，本清单在此基础上扩展

---

## 3. 权限 Gap 汇总矩阵

按优先级排列，P0 必须在 Phase 2（双重授权窗口）前修复：

| 优先级 | Gap | 类型 | 影响范围 | 修复 Phase |
|--------|-----|------|---------|-----------|
| **P0** | CategoryListView POST 无权限闸门 | 后端越权 | 任何 Employee 可创建分类 | Phase 2 |
| **P0** | `is_hr_admin` 公开暴露管理员名单 | 信息泄露 | 全用户可看管理员 | Phase 3 |
| **P0** | 无角色分配 API | 管理缺口 | 无审计追踪的角色分配 | Phase 2 |
| **P0** | AuditLog 缺系统操作记录 | 审计缺口 | 系统行为不可追溯 | Phase 2 |
| **P0** | 前端 4 处 `is_hr_admin` 硬编码 | 前端越权 | 无法区分 HR/Admin | Phase 2 |
| **P1** | Token 端点无专项限速 | 暴力破解 | 登录 brute-force 风险 | Phase 2 |
| **P1** | JWT token 无角色信息 | Token 安全 | 角色变更后旧 token 有效 | Phase 3 |
| **P1** | Django Admin `/admin/` 暴露 | 配置风险 | `is_staff` 不等于 RBAC | Phase 3 |
| **P2** | `IsOwnerOrReadOnly` 死代码 | 代码质量 | 表明权限实现未完成 | Phase 4 清理 |
| **P2** | 无对象级权限 | 权限粒度 | HR 可删除他人文档 | 后续版本 |
| **P2** | CORS 配置待验证 | 配置风险 | 可能过宽 | Phase 3 |

---

## 4. V4.0 修复方案对照

| Gap | V3.8 现状 | V4.0 修复 | 修复文件 |
|-----|---------|---------|---------|
| CategoryListView | `IsAuthenticated` 仅 | `HasPermission('category.create')` 分离 GET/POST | `backend/apps/knowledge/views.py` |
| 管理员名单泄露 | `UserSerializer` 含 `is_hr_admin` | 移除公开字段，新增 `UserAdminSerializer` | `backend/apps/users/serializers.py` |
| 无角色分配 API | 无 | `POST /api/v1/rbac/user-roles/` | 新建 `backend/apps/rbac/views.py` |
| 审计日志缺系统操作 | 11 个 ACTION_CHOICES | 新增 9 个系统级 ACTION_CHOICES | `backend/apps/audit/models.py` |
| 前端 `is_hr_admin` 硬编码 | 4 处 `boolean` | 改为 `roles: string[]` | `AuthProvider.tsx` + `AppLayout.tsx` + `LoginPage.tsx` |
| 无 RoleGuard | 无 | 新建 `RoleGuard.tsx` 组件 | 新建 `frontend/src/components/RoleGuard.tsx` |
| Token 限速 | 全局 30/min | 登录端点 5/min/IP | `backend/config/settings/base.py` |

---

## 5. 风险量化评估

### 5.1 潜在攻击场景

| 场景 | 当前可行性 | V4.0 修复后 |
|------|-----------|------------|
| Employee 创建恶意分类 | ✅ 可行（`IsAuthenticated` 仅） | ❌ 需 `category.create` 权限 |
| Employee 获取管理员名单 | ✅ 可行（`GET /auth/me/` 含 `is_hr_admin`） | ❌ 字段已移除 |
| Employee 手动导航进入管理界面 | ✅ 可行（前端无 RoleGuard） | ❌ 路由守卫拦截 |
| 外部猜测 URL 下载内部文档 | ✅ 可行（DEBUG 模式） | ❌ 生产关闭 DEBUG + 签名 URL |
| 暴力破解登录密码 | ⚠️ 可行（30/min 限速过宽） | ❌ 5/min/IP 专项限速 |
| HR 误删他人文档 | ✅ 可行（无 ownership 检查） | ⚠️ 后续版本加 ownership |
| Admin 行为不可追溯 | ✅ 确认（审计日志缺系统操作） | ❌ ACTION_CHOICES 扩展 |

### 5.2 整体风险评分

| 维度 | V3.8 评分 | V4.0 评分（修复后） | 变化 |
|------|---------|------------------|------|
| API 鉴权完整性 | 3/10 | 9/10 | +6 |
| 权限粒度 | 0/10 | 8/10 | +8 |
| 信息泄露防护 | 3/10 | 9/10 | +6 |
| 审计可追溯性 | 2/10 | 8/10 | +6 |
| 前端路由安全 | 2/10 | 9/10 | +7 |
| **综合** | **2/10** | **8.6/10** | **+6.6** |

> [来源: V3.8/Bug清单汇总_V3.8.md §安全评分] — V3.8 安全评分已识别多项高危漏洞

---

## 附录：代码引用索引

| 引用 | 文件路径 | 行号 | 内容摘要 |
|------|---------|------|---------|
| G-01 | `backend/apps/core/permissions.py` | L6-12 | `IsHROrAdmin: is_hr_admin OR is_superuser` |
| G-02 | `backend/apps/users/models.py` | L53 | `is_hr_admin = models.BooleanField(default=False)` |
| G-03 | `backend/apps/users/serializers.py` | L22 | `is_hr_admin` 在公开 serializer fields 中 |
| G-04 | `backend/apps/knowledge/views.py` | L124 | `CategoryListView: permission_classes = [IsAuthenticated]` |
| G-05 | `backend/apps/audit/models.py` | L12-24 | `ACTION_CHOICES` 缺系统级操作 |
| G-06 | `frontend/src/auth/AuthProvider.tsx` | L8 | `is_hr_admin: boolean` User 接口 |
| G-07 | `frontend/src/layout/AppLayout.tsx` | L115 | `user?.is_hr_admin` 侧边栏判断 |
| G-08 | `frontend/src/auth/LoginPage.tsx` | L52 | `is_hr_admin: user.is_hr_admin` 硬编码 |
| G-09 | `backend/apps/core/permissions.py` | L15-21 | `IsOwnerOrReadOnly` 死代码 |
| G-10 | `backend/config/urls.py` | L16-17 | DEBUG 模式 Media 无鉴权 |
