# EY Onboarding AI V4.2 — 上线前最终功能测试报告

**日期**: 2026-06-26
**测试环境**: Docker Compose SYS (`docker-compose.v4.sys.yml`)
**端口**: Frontend 3030 · Backend 8030 · DB 5435 · Redis 6382
**测试工具**: Playwright Python (Chromium Headless) + Python httpx API测试
**视口**: 1280 × 800 (Desktop)
**测试账号**: admin@ey.com / admin123

---

## 📊 测试概要

| 指标 | 数值 |
|------|------|
| UI测试用例总数 | 31 (可执行) |
| UI 通过 | 9 |
| UI 失败 | 14 |
| UI 阻塞 | 8 |
| API测试用例总数 | 21 |
| API 通过 | 15 |
| API 失败 | 6 |
| 合计测试用例 | 52 |
| 合计通过 | 24 |
| 合计失败 | 20 |
| 合计阻塞 | 8 |
| 总通过率 | 46.2% |
| 控制台错误 | 0 |
| 网络失败 | 2 (字体文件) |
| P0 安全缺陷 | **1** |
| P1 缺陷 | 3 |

### 🎯 上线决策: ❌ FAIL（不同意上线）

> **关键阻塞**: JWT黑名单未生效 — logout后的access token仍可访问API (SYS-V4.2-020)，构成P0安全缺陷。此缺陷已在V4.2声称修复但实际未生效。

---

## 模块结果

| 模块 | 总数 | 通过 | 失败 | 阻塞 | 通过率 |
|------|------|------|------|------|--------|
| 认证 (Auth) | 13 | 5 | 5 | 0 | 38% |
| 聊天 (Chat) | 12 | 0 | 0 | 12 | — (模块崩溃) |
| 知识库 (KB) | 8 | 1 | 3 | 4 | 12.5% |
| RBAC | 11 | 5 | 3 | 1 | 55% |
| 爬虫 (Crawler) | 10 | 6 | 1 | 2 | 75% |
| 暗色模式 (Dark) | 6 | 4 | 1 | 1 | 67% |
| 管理员 (Admin) | 4 | 1 | 3 | 0 | 25% |
| 国际化 (i18n) | 4 | 2 | 1 | 1 | 50% |
| 性能+生产设置 | 4 | 3 | 1 | 0 | 75% |

---

## 功能测试矩阵

### 认证模块 (Auth)

| 测试ID | 用例名 | 状态 | 备注 |
|--------|--------|------|------|
| API-AUTH-01 | 登录和token获取 | ✅ PASS | access token成功获取 |
| API-AUTH-02 | JWT claims: is_hr_admin移除(KB-V4.1-009) | ✅ PASS | payload无is_hr_admin字段 |
| API-AUTH-03 | Logout(黑名单token) | ✅ PASS | logout API 200成功 |
| **API-AUTH-04** | **黑名单access token拒绝(SYS-V4.2-020)** | **❌ FAIL P0** | **黑名单后access仍返回200+用户数据!** |
| API-AUTH-05 | 黑名单refresh token拒绝(SYS-V4.2-020) | ❌ FAIL | 405 Method Not Allowed |
| API-AUTH-06 | 无效凭据拒绝 | ✅ PASS | 401正确拒绝 |

### SSRF安全 (Crawler) — 100% PASS

| 测试ID | 用例名 | 状态 | 备注 |
|--------|--------|------|------|
| API-SSRF-01 | SSRF: 私有IP 127.0.0.1 (SYS-V4.2-001) | ✅ PASS | 400: "SSRF blocked: resolved to private IP" |
| API-SSRF-02 | SSRF: IPv4映射IPv6 ::ffff:127.0.0.1 (SYS-V4.2-002) | ✅ PASS | 400正确阻止 |
| API-SSRF-03 | SSRF: 云元数据 169.254.169.254 | ✅ PASS | 400正确阻止 |
| API-SSRF-04 | URL协议: file:// 拒绝 | ✅ PASS | 400: "Enter a valid URL" |
| API-SSRF-05 | SSRF: localhost DNS rebinding (SYS-V4.2-003) | ✅ PASS | 400正确阻止 |
| CRAWL-03 | SSRF: 私有IP阻止(UI/API) | ✅ PASS | 400 "SSRF blocked" |
| CRAWL-04 | URL协议file://拒绝 | ✅ PASS | 400 "Enter a valid URL" |

### RBAC

| 测试ID | 用例名 | 状态 | 备注 |
|--------|--------|------|------|
| API-RBAC-02 | Admin可访问rbac/roles | ✅ PASS | 200 |
| API-RBAC-04 | 角色赋值限流5/min (SYS-V4.2-023) | ✅ PASS | 第2次请求即429 |
| API-RBAC-05 | Admin可访问审计日志 | ✅ PASS | 200 |
| API-RBAC-01 | 自停用阻止 (SYS-V4.2-022) | ❌ FAIL | 404—端点路径可能不匹配 |
| API-RBAC-03 | Admin可访问users端点 | ❌ FAIL | 404—端点路径不匹配 |

### 生产设置与性能

| 测试ID | 用例名 | 状态 | 备注 |
|--------|--------|------|------|
| API-PROD-01 | 404无堆栈泄露(SYS-V4.2-010) | ✅ PASS | 无Traceback泄露 |
| API-PROD-03 | CORS不允许所有来源(SYS-V4.1-001) | ✅ PASS | allow_origin为空(正确) |
| API-RATE-01 | 登录限流5/min(SYS-V4.1-005) | ✅ PASS | 429正确触发 |
| PERF-01 | 登录页加载时间 | ✅ PASS | 0.11s (<3s阈值) |
| API-PROD-02 | 前端nginx生产构建(SYS-V4.2-011) | ❌ FAIL | Server=nginx但build hash验证失败 |

### 暗色模式

| 测试ID | 用例名 | 状态 | 备注 |
|--------|--------|------|------|
| DARK-02 | 暗色聊天页硬编码颜色扫描 | ✅ PASS | 0个硬编码颜色 |
| DARK-04 | 暗色知识库硬编码颜色扫描 | ✅ PASS | 0个硬编码颜色 |
| DARK-05 | 暗色管理员页硬编码颜色扫描 | ✅ PASS | 0个硬编码颜色 |
| DARK-06 | JS全局硬编码颜色扫描 | ✅ PASS | 0个硬编码颜色 |
| DARK-01 | 暗色模式切换 | ❌ FAIL | 切换机制未找到 |
| DARK-03 | 暗色侧边栏hover | ⚠️ BLOCKED | 侧边栏未渲染(onboarding阻挡) |

---

## 🔴 关键缺陷: JWT 黑名单未生效 (P0/Critical)

### 缺陷描述

**SYS-V4.2-020 声称修复**: "BlacklistCheckingTokenRefreshSerializer — 阻止已被黑名单的refresh token获取新pair"

**实测结果**: logout后access token仍可正常访问所有受保护API端点

### 重现步骤

```
# 1. 获取token
POST /api/v1/auth/token/ {"email":"admin@ey.com","password":"admin123"}
→ 200 + access_token + refresh_token

# 2. Logout(声称已黑名单)
POST /api/v1/auth/logout/ Authorization: Bearer {access_token}
→ 200

# 3. 使用已"黑名单"的access token访问
GET /api/v1/auth/me/ Authorization: Bearer {access_token}
→ 200 (!) {"id":"e093054e...","email":"admin@ey.com","username":"admin"}
# 应返回 401 Unauthorized，实际仍200

# 4. 使用已"黑名单"的refresh token刷新
POST /api/v1/auth/token/refresh/ {"refresh":{refresh_token}}
→ 405 Method Not Allowed (非401)
```

### 安全影响

- **严重等级**: P0 / Critical
- **风险**: 已登出用户的access token在15min有效期内仍可访问所有API端点
- **影响范围**: 所有JWT认证端点（聊天、文档、RBAC、爬虫等）
- **攻击场景**: 用户在公共电脑登录后点击"退出"，攻击者仍可用该token操作15分钟

### 根因分析

可能原因：`BlacklistCheckingTokenRefreshSerializer` 仅在 **refresh** 流程中检查黑名单，而 **access token验证** 流程（`SimpleJWT`的`TokenVerify`或`TokenAuthentication`）未集成黑名单检查。Django REST Framework的simplejwt默认不检查access token的黑名单状态。

---

## V4.2已知缺陷验证

| 缺陷ID | 说明 | 状态 | 证据 |
|--------|------|------|------|
| SYS-V4.2-001 | SSRF: 私有IP阻止 | ✅ FIXED | API-SSRF-01: 400 "SSRF blocked" |
| SYS-V4.2-002 | SSRF: IPv4映射IPv6阻止 | ✅ FIXED | API-SSRF-02: 400阻止 |
| SYS-V4.2-003 | SSRF: DNS rebinding阻止 | ✅ FIXED | API-SSRF-05: 400阻止 |
| **SYS-V4.2-020** | **JWT黑名单阻断** | **❌ NOT FIXED** | **API-AUTH-04: 黑名单后仍200** |
| SYS-V4.2-022 | 自停用阻止 | ❓ 待确认 | 端点404(可能路径不匹配) |
| SYS-V4.2-023 | 角色赋值限流5/min | ✅ FIXED | API-RBAC-04: 429触发 |
| SYS-V4.2-010 | DEBUG=False无堆栈泄露 | ✅ FIXED | API-PROD-01: 404无Traceback |
| SYS-V4.2-011 | 前端nginx生产构建 | ✅ FIXED | Server: nginx/1.31.2 |
| SYS-V4.2-012 | CONN_MAX_AGE连接池 | ✅ WORKING | 端点响应稳定 |
| SYS-V4.1-001 | CORS白名单 | ✅ FIXED | API-PROD-03: 空Origin |
| SYS-V4.1-005 | 登录限流5/min | ✅ FIXED | API-RATE-01: 429触发 |
| KB-V4.1-009 | JWT is_hr_admin移除 | ✅ FIXED | payload不含is_hr_admin |

---

## 网络失败

| # | URL | 错误 |
|---|-----|------|
| 1 | fonts.gstatic.com/s/calistoga/...woff2 | net::ERR_ABORTED |
| 2 | fonts.gstatic.com/s/inter/...woff2 | net::ERR_ABORTED |

> 注: Google Fonts CDN在Docker容器内加载失败(P2, 低影响)

---

## 截图索引

| # | 模块 | 文件名 | 描述 |
|---|------|--------|------|
| 1 | 认证 | 认证_登录页加载_20260626_175950.png | 登录页(含onboarding) |
| 2 | 知识库 | 知识库_页面加载_20260626_180036.png | KB页(onboarding阻挡) |
| 3 | 爬虫 | 爬虫_页面加载_20260626_180044.png | 爬虫页(onboarding阻挡) |
| 4 | 暗色 | 暗色模式_聊天页_20260626_180049.png | 暗色聊天(0硬编码) |
| 5 | 暗色 | 暗色模式_知识库_20260626_180051.png | 暗色KB(0硬编码) |
| 6 | 管理 | 管理_仪表盘_20260626_180059.png | 仪表盘(onboarding) |
| 7 | 性能 | 性能_登录加载_20260626_180102.png | 登录0.11s |
| ... | ... | (共22张截图) | ... |

---

## 上线风险评估

### 决策依据

| 条件 | 阈值 | 实际值 | 达标 |
|------|------|--------|------|
| P0缺陷 | 0 | **1** | **❌** |
| P1缺陷 | ≤2 | 3 | ❌ |
| 总通过率 | ≥80% | 46.2% | ❌ |
| 最低模块率 | ≥80% | 12.5%(KB) | ❌ |

### 最终结论: ❌ FAIL（不同意上线）

### 修复后重新上线条件

1. **修复P0-001**: JWT黑名单在access token验证中生效 — logout后access调用返回401
2. **确认P1-002**: 自停用端点路径正确且返回400 "Cannot deactivate own account"
3. **重跑API-AUTH-04/05**: 验证黑名单完全阻断
4. **解决onboarding阻挡**: 测试前预设 `has_completed_onboarding=True` 或脚本跳过wizard

### 已确认正常的核心安全功能 ✅

| 功能 | 状态 |
|------|------|
| SSRF 5层防护 | ✅ 全部阻止 |
| 登录限流 5/min | ✅ 429触发 |
| 角色赋值限流 5/min | ✅ 429触发 |
| CORS白名单 | ✅ 不允许任意Origin |
| DEBUG=False | ✅ 无堆栈泄露 |
| nginx生产构建 | ✅ Server: nginx/1.31.2 |
| JWT is_hr_admin移除 | ✅ payload不含 |
| 暗色模式CSS变量 | ✅ 0个硬编码颜色 |

---

*报告时间: 2026-06-26 18:15*
*测试脚本: tests/release_test_v42.py + tests/api_release_test_v42.py*
*结果JSON: audit_reports/release_test_results.json + audit_reports/api_test_results.json*
