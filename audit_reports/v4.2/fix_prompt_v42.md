# V4.2 上线前测试发现的缺陷修复 Prompt

## 上下文

V4.2上线前最终功能测试于2026-06-26执行，发现1个P0关键安全缺陷和3个P1缺陷。测试报告位于 `audit_reports/Release_Test_Report_20260626.md`。

测试环境: docker-compose.v4.sys.yml (Frontend:3030 / Backend:8030)

---

## 🔴 P0: JWT 黑名单未阻断 access token (SYS-V4.2-020 NOT FIXED)

### 问题

调用 `/api/v1/auth/logout/` 后，被黑名单的 **access token** 仍可正常访问所有受保护API端点（返回200+完整用户数据），应返回401。

### 根因分析（已确认）

在 `backend/config/settings/base.py` 中，DRF认证类配置为：

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
}
```

`simplejwt` 的默认 `JWTAuthentication.authenticate()` 流程：
1. 解码JWT，验证签名和 `exp` 过期时间
2. 在 `outstanding_tokens` 表查找用户
3. **完全忽略 `blacklisted_tokens` 表**

`BlacklistCheckingTokenRefreshSerializer`（`backend/apps/users/views.py` 第90-127行）仅检查refresh流程中的黑名单，对access token验证无任何影响。

Logout view（`backend/apps/users/views.py` 第178-239行）正确地将access和refresh token写入 `BlacklistedToken` 表，但由于认证类不查询此表，写入毫无效果。

### 修复方案

创建自定义JWT认证类，继承 `JWTAuthentication`，在 `authenticate()` 方法中增加黑名单检查：

**文件: `backend/apps/users/authentication.py`**（新建）

```python
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

class BlacklistCheckingJWTAuthentication(JWTAuthentication):
    """
    SYS-V4.2-020: Extends JWTAuthentication to check the blacklist table.
    The default JWTAuthentication only validates signature + expiry,
    completely ignoring the blacklisted_tokens table.
    """
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None  # No token provided → skip
        
        user, validated_token = result
        jti = validated_token.get("jti")
        if jti:
            outstanding = OutstandingToken.objects.filter(jti=jti).first()
            if outstanding and BlacklistedToken.objects.filter(token=outstanding).exists():
                from rest_framework.exceptions import AuthenticationFailed
                raise AuthenticationFailed("Token has been blacklisted.")
        
        return result
```

**文件: `backend/config/settings/base.py`**（修改）

将 `DEFAULT_AUTHENTICATION_CLASSES` 替换为：

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.BlacklistCheckingJWTAuthentication",
    ],
}
```

**同时修改 `AuthenticatedMediaMiddleware`**（`backend/apps/core/middleware.py`），将中间件中的 `JWTAuthentication()` 替换为 `BlacklistCheckingJWTAuthentication()`。

### 验证方法

```bash
# 1. 获取token
curl -s http://127.0.0.1:8030/api/v1/auth/token/ \
  -X POST -H "Content-Type: application/json" \
  -d '{"email":"admin@ey.com","password":"admin123"}'

# 2. Logout(黑名单)
curl -s http://127.0.0.1:8030/api/v1/auth/logout/ \
  -X POST -H "Authorization: Bearer {access_token}"

# 3. 使用黑名单access token访问 → 必须返回401
curl -s http://127.0.0.1:8030/api/v1/auth/me/ \
  -H "Authorization: Bearer {access_token}"
# 期望: 401 {"detail": "Token has been blacklisted."}
```

---

## P1-001: 自停用端点路径不匹配

### 问题

测试中调用 `POST /api/v1/users/{id}/deactivate/` 返回404。

### 根因

实际端点路径为 `POST /api/v1/rbac/users/{id}/deactivate/`（定义在 `backend/apps/rbac/urls.py` 第28行），而非 `/api/v1/users/`。

### 状态: **功能已实现且正常工作**

经查证，SYS-V4.2-022 自停用阻止代码在 `backend/apps/rbac/views.py` 第293-298行已正确实现：

```python
if user.id == request.user.id:
    return Response({"detail": "Cannot deactivate your own account."}, status=400)
```

仅需在测试脚本中修正API路径即可验证。**无需修改代码。**

验证命令：
```bash
curl -s http://127.0.0.1:8030/api/v1/rbac/users/{admin_uuid}/deactivate/ \
  -X POST -H "Authorization: Bearer {access_token}" -H "Content-Type: application/json"
# 期望: 400 {"detail": "Cannot deactivate your own account."}
```

---

## P1-002: UI Onboarding 阻挡页面导航

### 问题

新用户首次登录弹出onboarding wizard（"Get Started"/"Skip for now"），所有admin页面均显示此弹窗而非实际内容。

### 根因

onboarding状态存储在localStorage（`ey-onboarding-seen`），由 `frontend/src/layout/AppLayout.tsx` 第82-84行控制：

```typescript
const [onboardingVisible, setOnboardingVisible] = useState(() => {
    return !localStorage.getItem('ey-onboarding-seen');
});
```

### 状态: **非应用缺陷，仅影响测试覆盖**

这是正常的首次使用引导功能，不影响用户体验。测试脚本需在登录后先设置localStorage跳过wizard：

```javascript
localStorage.setItem('ey-onboarding-seen', 'true');
```

**无需修改代码。** 但建议在生产部署中预置此localStorage值（或后端增加 `has_completed_onboarding` 字段），避免admin用户被引导流程阻挡。

---

## P1-003: 前端 nginx build hash 验证

### 问题

API测试检查 `http://127.0.0.1:3030/` HTML中是否含 `assets/index-{hash}` 模式，实际HTML确实包含 `assets/index-CgHCig4a.js`，但测试脚本匹配逻辑有误。

### 状态: **测试脚本缺陷，非应用缺陷**

nginx确实在生产模式服务前端（`Server: nginx/1.31.2`），HTML含正确build hash。**无需修改代码。**

---

## P2: Google Fonts CDN 加载失败

### 问题

Docker容器内无法加载 `fonts.gstatic.com` 的woff2字体文件（net::ERR_ABORTED）。

### 建议修复（可选）

在 `frontend/Dockerfile` 或 nginx配置中增加本地字体fallback。或在 `frontend/src/index.html` 中增加 `font-display: swap` 以减少字体加载阻塞。

---

## 执行优先级

| 优先级 | 缺陷 | 工期 | 是否需改代码 |
|--------|------|------|-------------|
| **P0** | JWT黑名单access阻断 | ~2h | **是** |
| P1-001 | 自停用端点路径 | 0h | 否(测试路径修正) |
| P1-002 | onboarding阻挡 | 0h | 否(测试localStorage设置) |
| P1-003 | build hash验证 | 0h | 否(测试逻辑修正) |
| P2 | Fonts CDN | ~1h | 可选 |

## 修复后验证步骤

1. 修改 `backend/apps/users/authentication.py` 和 `backend/config/settings/base.py`
2. 重建Docker: `docker-compose -f docker-compose.v4.sys.yml up -d --build backend`
3. 执行验证命令序列（上述P0验证方法）
4. 执行自停用验证（使用正确路径 `/api/v1/rbac/users/{id}/deactivate/`）
5. 重跑API测试: `python tests/api_release_test_v42.py`
6. 确认所有API-AUTH-04/05返回401 → 上线决策升级为PASS
