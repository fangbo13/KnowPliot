# EY Onboarding AI V4.2 — 修复执行 Prompt

**请严格按照以下计划修复所有缺陷。修改源代码时不要引入新Bug。每个修复完成后请自行验证。**

---

## 项目信息

**项目**: EY Onboarding AI — RAG驱动的新员工入职Chatbot
**技术栈**: Django 5 + DRF + Celery + Redis / React 18 + TypeScript + Vite + Ant Design 5 + Zustand
**环境**: Docker SYS — Frontend :3030 / Backend :8030 / DB :5435 / Redis :6382
**测试账号**: admin@ey.com / admin123
**完整修复计划**: 见 `audit_reports/V4.2_Fix_Plan.md`

---

## 修复顺序（必须严格按顺序执行）

### Phase 1: P0 阻断缺陷（最高优先级）

#### FIX-001: JWT黑名单未阻断access token (SYS-V4.2-020)

**文件**:
- `backend/apps/users/authentication.py` — **新建**
- `backend/config/settings/base.py` — 修改 `DEFAULT_AUTHENTICATION_CLASSES`
- `backend/apps/core/middleware.py` — 替换 `AuthenticatedMediaMiddleware` 中的 `JWTAuthentication()`

**步骤**:

1. 新建 `backend/apps/users/authentication.py`:

```python
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework.exceptions import AuthenticationFailed

class BlacklistCheckingJWTAuthentication(JWTAuthentication):
    """SYS-V4.2-020: Check blacklist table during access token validation."""
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, validated_token = result
        jti = validated_token.get("jti")
        if jti:
            outstanding = OutstandingToken.objects.filter(jti=jti).first()
            if outstanding and BlacklistedToken.objects.filter(token=outstanding).exists():
                raise AuthenticationFailed("Token has been blacklisted.")
        return result
```

2. 修改 `backend/config/settings/base.py`，替换 `DEFAULT_AUTHENTICATION_CLASSES`:

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.BlacklistCheckingJWTAuthentication",
    ],
}
```

3. 修改 `backend/apps/core/middleware.py` 中 `AuthenticatedMediaMiddleware`，将 `JWTAuthentication()` 替换为 `BlacklistCheckingJWTAuthentication()`。

4. 验证（在修复完成后执行）:
```bash
TOKEN=$(curl -s http://127.0.0.1:8030/api/v1/auth/token/ -X POST -H "Content-Type: application/json" -d '{"email":"admin@ey.com","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access'])")
curl -s http://127.0.0.1:8030/api/v1/auth/logout/ -X POST -H "Authorization: Bearer $TOKEN"
# 必须返回 401 "Token has been blacklisted."
curl -s http://127.0.0.1:8030/api/v1/auth/me/ -H "Authorization: Bearer $TOKEN"
```

---

### Phase 2: P1 严重缺陷

#### FIX-002: handleRetry绕过sendLock守卫 (UI-V4.2-002)

**文件**: `frontend/src/pages/ChatPage.tsx`

**修复**: 重构 `handleRetry` 复用 `handleSend` 的守卫逻辑。提取 `sendWithGuard` 函数，让 `handleSend` 和 `handleRetry` 都调用它。守卫条件：`isStreaming || isSendLocked || isSendingRef.current || !navigator.onLine`。

#### FIX-003: CrawlerAdminPage useEffect风暴 (UI-V4.2-001)

**文件**: `frontend/src/pages/admin/CrawlerAdminPage.tsx`

**修复**: 将 `useEffect(() => { fetchDocs(); }, [fetchDocs])` 改为 `useEffect(() => { fetchDocs(); const interval = setInterval(fetchDocs, 30000); return () => clearInterval(interval); }, [])`。空依赖数组，仅mount时执行一次，后续靠30s polling刷新。

#### FIX-004: Admin Dashboard健康面板硬编码 (UI-V4.2-011)

**文件**: `frontend/src/pages/admin/AdminDashboardPage.tsx`

**修复**: `loadSystemStatus` 中使用 `auditRes.data` 真实数据填充面板。仅在API失败时显示 `'unknown'`。

#### FIX-005: ErrorBoundary重试丢失全部SPA状态 (UI-V4.2-010)

**文件**: `frontend/src/components/ErrorBoundary.tsx`

**修复**: 将 `window.location.reload()` 替换为 `this.setState({ hasError: false, error: null })`，重挂载子树而非全页面刷新。

#### FIX-006: admin账号无法访问Admin/Knowledge页面

**修复**: 检查 `admin@ey.com` 的 `role_level` 字段，确保设置为 `'admin'`。检查 `frontend/src/auth/RoleGuard.tsx` 的权限判断逻辑。

---

### Phase 3: P2 一般缺陷

#### FIX-007: 暗色模式硬编码颜色（8处）

| 文件 | 硬编码值 | 替换为 |
|------|----------|--------|
| `ChatPage.tsx` ~304-308 | `background: '#fff2f0'` | `var(--color-error-bg)` |
| `ChatPage.tsx` ~304-308 | `border: '2px solid #ff4d4f'` | `var(--color-error)` |
| `AppLayout.tsx` ~383 | `rgba(0, 82, 255, 0.25)` | `var(--shadow-accent)` |
| `AdminDashboardPage.tsx` ~224 | `'#52c41a'` | `var(--color-success)` |
| `MessageBubble.tsx` ~35-39 | `'#52c41a'`/`'#faad14'`/`'#8c8c8c'` | CSS变量 |

#### FIX-008: Sidebar hover --color-fill未定义 (UI-V4.2-007)

**文件**: `frontend/src/styles/globals.css`

**修复**: 在 `:root` 中添加 `--color-fill: rgba(0, 82, 255, 0.04)` 和 `--color-fill-secondary: rgba(0, 82, 255, 0.08)`；在 `[data-theme="dark"]` 中添加 `--color-fill: rgba(77, 124, 255, 0.08)` 和 `--color-fill-secondary: rgba(77, 124, 255, 0.12)`。

#### FIX-009~012: 其余P2修复

- FIX-009: Google Fonts Docker加载失败 — 在 `index.html` 添加 `font-display: swap`
- FIX-010: NetworkStatusBanner animation — 移除inline animation依赖antd内置动画
- FIX-011: emoji可访问性 — 替换为 antd icon + aria-label
- FIX-012: 字数计数器ARIA — 添加 `role="status" aria-live="polite"`

---

## 修复后验证清单

1. 重建Docker: `docker compose -f docker-compose.v4.sys.yml up -d --build`
2. JWT黑名单: logout后access token返回401
3. handleRetry: 断网后Retry按钮不发送请求
4. CrawlerAdmin: 语言切换后不触发额外API请求
5. Admin Dashboard: 系统健康面板显示真实数据
6. ErrorBoundary: 重试不丢失页面状态
7. admin账号: 可访问/admin/dashboard和/admin/knowledge
8. 暗色模式: 无硬编码颜色
9. Sidebar hover: 暗色/亮色模式均有视觉反馈

## 注意事项

- **绝对不要修改 `audit_reports/` 目录下的任何文件**
- **绝对不要修改 `tests/` 目录下的测试脚本**
- 每个修复保持独立，不要重构无关代码
- 修复完成后在每个修改过的文件添加注释：`// FIX-XXX: <修复描述>`
