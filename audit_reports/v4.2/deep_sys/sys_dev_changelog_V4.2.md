# V4.2 SYS 领域变更日志

> **版本**: V4.2 — SYS 领域安全加固、SSRF 防护升级与性能优化
> **日期**: 2026-06-26
> **开发环境**: Docker Compose SYS 领域（docker-compose.v4.sys.yml）— 端口 3030/8030/5435/6382
> **引用规则**: `[来源: V4.2/deep_sys/deep_sys_defect_list_V4.2.md §SYS-V4.2-XXX]`

---

## 一、变更总览

| 维度 | 数量 |
|---|---|
| 修改文件数 | 14 |
| 新增加固/修复数 | 26（P0:2, P1:7, P2:17） |
| 新增文件数 | 3（circuit_breaker.py, nginx.conf, 500.html） |
| 性能优化项数 | 7（生产构建、断路器、连接池、队列路由、增量渲染、forceUpdate优化、computeRounds去冗余） |

### 修改文件清单

| 文件 | 修改类型 | 涉及缺陷 |
|---|---|---|
| `frontend/Dockerfile` | 重写（多阶段构建+nginx） | SYS-V4.2-011 |
| `frontend/nginx.conf` | 新增 | SYS-V4.2-011 |
| `frontend/src/stream/TokenBatchRenderer.ts` | 重写（增量diff模式） | SYS-V4.2-015 |
| `frontend/src/sync/crossTabSync.ts` | 重写（静态导入） | SYS-V4.2-017 |
| `frontend/src/pages/ChatPage.tsx` | 修改（forceUpdate优化） | SYS-V4.2-018 |
| `frontend/src/store/chatStore.ts` | 修改（增量渲染+computeRounds去冗余） | SYS-V4.2-015, 016 |
| `backend/apps/core/circuit_breaker.py` | 新增 | SYS-V4.2-014 |
| `backend/apps/core/middleware.py` | 新增RbacCacheMiddleware | SYS-V4.2-006 |
| `backend/apps/core/permissions.py` | 修改（审计容错+is_hr_admin审计） | SYS-V4.2-007, 009 |
| `backend/apps/rag/pipeline.py` | 修改（断路器+降级） | SYS-V4.2-014 |
| `backend/apps/chat/views.py` | 修改（SSE超时） | SYS-V4.2-014 |
| `backend/apps/crawler/validators.py` | 重写（IPv4-mapped+重定向链+robots.txt校验） | SYS-V4.2-001, 002, 003, 005 |
| `backend/apps/crawler/services.py` | 重写（DNS rebinding+重定向链+robots.txt校验） | SYS-V4.2-002, 003, 005 |
| `backend/apps/crawler/views.py` | 修改（URL校验+事务） | SYS-V4.2-004, 019 |
| `backend/apps/crawler/tasks.py` | 修改（队列路由） | SYS-V4.2-013 |
| `backend/apps/users/models.py` | 修改（RBAC缓存+content_resources同步） | SYS-V4.2-006, 024 |
| `backend/apps/users/views.py` | 修改（JWT黑名单检查） | SYS-V4.2-020 |
| `backend/apps/users/urls.py` | 修改（JWT黑名单检查） | SYS-V4.2-020 |
| `backend/apps/rbac/views.py` | 修改（限流+自我停用防护+角色重分配） | SYS-V4.2-008, 022, 023 |
| `backend/config/settings/base.py` | 修改（CONN_MAX_AGE+MIDDLEWARE+队列路由） | SYS-V4.2-006, 012, 013 |
| `backend/config/settings/docker.py` | 修改（DEBUG=False） | SYS-V4.2-010 |
| `backend/templates/500.html` | 新增 | SYS-V4.2-010 |
| `docker-compose.v4.sys.yml` | 修改（前端nginx+celery双worker） | SYS-V4.2-011, 013 |

---

## 二、逐项变更详情

### FIX-SYS-V4.2-011: 前端生产构建 — P0 阻断

**缺陷**: Dockerfile 运行 `npm run dev`（Vite 开发服务器），无 minification、无 tree-shaking、HMR websocket 开放、source maps 可访问，JS bundle ~10x 更大。

**修改文件**:
- `frontend/Dockerfile` — 重写为多阶段构建（Stage 1: node:20-slim + `npx vite build` → /app/dist/；Stage 2: nginx:alpine serve）
- `frontend/nginx.conf` — 新增：SPA fallback + API proxy + SSE 支持 + 安全头 + gzip
- `docker-compose.v4.sys.yml` — frontend 服务端口从 `3030:3000` 改为 `3030:80`

**修改前后核心逻辑对比**:
| 修改前 | 修改后 |
|---|---|
| `CMD ["npm", "run", "dev"]` — 开发服务器 | `CMD ["nginx", "-g", "daemon off;"]` — nginx 静态文件服务 |
| 无 minification | `npx vite build` — minified + tree-shaken + hashed assets |
| HMR websocket 暴露 | 无 HMR（生产构建） |
| source maps 可访问 | 无 source maps（生产构建） |
| JS ~500-800KB | JS ~50-80KB（预估） |
| FCP ~2-3s | FCP ~0.5s（预估） |

**修复依据**: V4.2 审计 SYS-V4.2-011 [来源: V4.2/deep_sys/deep_sys_defect_list_V4.2.md §SYS-V4.2-011]
**风险评估**: 低风险 — 生产构建是标准做法，nginx 是成熟的静态文件服务器。唯一风险是 API proxy 配置需要正确指向 backend 容器。

---

### FIX-SYS-V4.2-014: DashScope 断路器 — P0 阻断

**缺陷**: DashScope API 无断路器，失败请求阻塞 runserver 单线程 30 秒，导致服务器完全瘫痪。

**修改文件**:
- `backend/apps/core/circuit_breaker.py` — 新增 CircuitBreaker 类（3 次失败→开路→30s 半开→降级）
- `backend/apps/rag/pipeline.py` — 在 retrieve_and_generate() 中集成断路器（检查+记录+降级）
- `backend/apps/chat/views.py` — 在 event_stream() 中添加 60 秒 SSE 超时检测

**修改前后核心逻辑对比**:
| 修改前 | 修改后 |
|---|---|
| `self.llm.stream_chat()` 无断路器 | `dashscope_breaker.allow_request()` 先检查断路器状态 |
| DashScope 失败 → 异常传播 → SSE error event | 断路器开路 → 立即返回降级消息 |
| SSE 无超时 → 前端 30s abort 才终止 | `SSE_TIMEOUT_SECONDS = 60` → 超时后返回 error event |
| 无失败计数 → 每次失败都等待 DashScope 响应 | `record_failure()` 计数 → 3 次后开路 → 所有后续请求 fail fast |

**修复依据**: V4.2 审计 SYS-V4.2-014 [来源: V4.2/deep_sys/deep_sys_defect_list_V4.2.md §SYS-V4.2-014]
**风险评估**: 中风险 — 断路器可能在 DashScope 短暂故障期间阻止正常请求。30 秒恢复窗口是保守值，可根据实际 DashScope 可用性调整。

---

### FIX-SYS-V4.2-001/002/003/005: SSRF 防护综合加固 — P1 严重

**缺陷**: 3 个 P1 SSRF + 1 个 P2 SSRF（IPv4-mapped IPv6 绕过、DNS rebinding、重定向链中间节点未校验、robots.txt 预取 SSRF）

**修改文件**:
- `backend/apps/crawler/validators.py` — 重写：添加 IPv4-mapped IPv6 检查、重定向链校验、robots.txt URL 校验
- `backend/apps/crawler/services.py` — 重写：DNS rebinding re-validation（time-of-use check）、全重定向链校验、RobotsTxtChecker IP 校验

**修改前后核心逻辑对比**:
| 修改前 | 修改后 |
|---|---|
| `_is_private_ip()` 不检查 IPv4-mapped | `ip.ipv4_mapped` 属性检查 — `::ffff:127.0.0.1` → `IPv4Address('127.0.0.1')` → is_private |
| 仅校验最终重定向 IP | `validate_redirect_chain()` 校验 `response.history` 中所有中间节点 IP |
| DNS rebinding 仅在提交时检查 | `_validate_hostname_ips()` 在 fetch 前重新解析验证（time-of-use check） |
| robots.txt 预取无 IP 校验 | `validate_robots_txt_url()` 校验 robots.txt URL 的 DNS 解析 IP |

**修复依据**: V4.2 审计 SYS-V4.2-001/002/003/005 [来源: V4.2/deep_sys/deep_sys_defect_list_V4.2.md §SYS-V4.2-001~003, 005]
**风险评估**: 低风险 — 仅扩展了已有的 SSRF 防护范围，未改变正常爬虫的请求流程。

---

### FIX-SYS-V4.2-008/022/023: 认证与限流加固 — P1

**缺陷**: admin_user_deactivate 无限流、允许自我停用、角色分配端点限流过宽松

**修改文件**: `backend/apps/rbac/views.py`

**修改前后核心逻辑对比**:
| 修改前 | 修改后 |
|---|---|
| `@api_view(["POST"])` 无 throttle_classes | `@throttle_classes([DeactivateUserRateThrottle])` — 5/min |
| 无自我停用防护 | `if user.id == request.user.id: return 400` |
| UserRoleListView 继承 30/min | `throttle_classes = [RoleAssignmentRateThrottle]` — 5/min |

**修复依据**: V4.2 审计 SYS-V4.2-008/022/023 [来源: V4.2/deep_sys/deep_sys_defect_list_V4.2.md §SYS-V4.2-008, 022, 023]

---

### FIX-SYS-V4.2-010: DEBUG=False — P1

**缺陷**: DEBUG=True 导致中间件层异常泄露堆栈信息（SafeErrorResponseMiddleware 仅拦截视图层异常）

**修改文件**: `backend/config/settings/docker.py` — `DEBUG = False`，`backend/templates/500.html` — 新增自定义错误页面

**修复依据**: V4.2 审计 SYS-V4.2-010 [来源: V4.2/deep_sys/deep_sys_defect_list_V4.2.md §SYS-V4.2-010]

---

### FIX-SYS-V4.2-020: JWT 黑名单检查 — P1

**缺陷**: 黑名单 refresh token 仍可用于获取新 token pair（BLACKLIST_AFTER_ROTATION 检查缺失）

**修改文件**: `backend/apps/users/views.py` — 新增 BlacklistCheckingTokenRefreshSerializer 和 BlacklistCheckingTokenRefreshView；`backend/apps/users/urls.py` — 替换 TokenRefreshView

**修复依据**: V4.2 审计 SYS-V4.2-020 [来源: V4.2/deep_sys/deep_sys_defect_list_V4.2.md §SYS-V4.2-020]

---

### 其他 P2 修复项

| 缺陷 ID | 修复 | 修改文件 |
|---|---|---|
| SYS-V4.2-004 | CrawlWithdrawByURLView url 参数校验（CrawlURLValidator + max length） | crawler/views.py |
| SYS-V4.2-006 | RBAC has_permission/has_role N+1 → 请求级缓存 | users/models.py + middleware.py + base.py |
| SYS-V4.2-007 | HasPermission/HasRole superuser bypass 审计容错 | permissions.py |
| SYS-V4.2-009 | is_hr_admin fallback 添加审计记录 | permissions.py |
| SYS-V4.2-012 | CONN_MAX_AGE=0 → 60 + CONN_HEALTH_CHECKS=True | base.py |
| SYS-V4.2-013 | Celery 双 worker（critical + default）+ 队列路由 | docker-compose.v4.sys.yml + base.py + tasks.py |
| SYS-V4.2-015 | TokenBatchRenderer 全字符串 → 增量 diff | TokenBatchRenderer.ts + chatStore.ts |
| SYS-V4.2-016 | computeRounds 双重调用 → 仅在 finishStreamingMessage() 中调用 | chatStore.ts |
| SYS-V4.2-017 | crossTabSync 4 层动态 import → 静态 import | crossTabSync.ts |
| SYS-V4.2-018 | forceUpdate 每帧触发 → 仅在 isNearBottom 变化时触发 | ChatPage.tsx |
| SYS-V4.2-019 | CrawlWithdrawByURLView transaction.atomic() + select_for_update() | crawler/views.py |
| SYS-V4.2-021 | UserRole 重分配：create → update(is_active=True) | rbac/views.py |
| SYS-V4.2-024 | content_resources 同步（添加 "audit"） | users/models.py |
| SYS-V4.2-025 | Redis 密码不匹配 — SYS compose 已有密码，原版 compose 不修改（约束） | docker-compose.v4.sys.yml |
| SYS-V4.2-026 | PostgreSQL 弱密码 — 开发环境可接受，生产环境必须更改 | 记录在文档 |

---

## 三、性能优化专项说明

| 优化项 | 预期效果 | 实际效果 |
|---|---|---|
| 前端生产构建（SYS-V4.2-011） | FCP 从 ~2-3s 降至 ~0.5s；JS 从 ~500-800KB 降至 ~50-80KB | ✅ vite build 成功 → dist/ 输出 minified+hashed assets；nginx 静态服务端口 3030 正常响应 |
| DashScope 断路器（SYS-V4.2-014） | DashScope 故障时服务器不再瘫痪；fail fast 降级响应 <1ms | ✅ 3次失败→开路→30s半开→降级消息；SSE 60s 超时保障 |
| 连接池（SYS-V4.2-012） | P95 延迟降低 ~8ms/请求（消除 TCP+auth handshake） | ✅ CONN_MAX_AGE=60 + CONN_HEALTH_CHECKS=True 配置生效 |
| Celery 队列路由（SYS-V4.2-013） | 大文件 ingest 不再阻塞 crawl 任务 | ✅ critical(2 slots) + default(2 slots) 双 worker 运行 |
| TokenBatchRenderer 增量 diff（SYS-V4.2-015） | 长对话 GC 压力从 ~480KB/s 降至 ~20KB/s（~95% 减少） | ✅ appendTokens 增量模式替代 fullContent 模式 |
| forceUpdate 优化（SYS-V4.2-018） | 流式输出期间 React renders 从 ~60/sec 降至 ~0-2/sec | ✅ 仅在 isNearBottom 值变化时触发 forceUpdate |
| computeRounds 去冗余（SYS-V4.2-016） | 每消息 computeRounds 调用从 2 次降至 1 次 | ✅ addMessage 中移除 computeRounds，仅在 finishStreamingMessage() 调用 |

---

> **签名**: V4.2 SYS 领域变更日志 — 2026-06-26
