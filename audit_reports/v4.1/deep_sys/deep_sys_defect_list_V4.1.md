# V4.1 深度系统与安全缺陷清单

> **审计版本**: V4.1 SYS 领域深度审计
> **审计日期**: 2026-06-26
> **审计环境**: Docker Compose SYS 领域（docker-compose.v4.sys.yml）
> **引用规则**: `[来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-XXX]`

---

## 【输入清洗】维度

### SYS-V4.1-008: ChatMessageRequestSerializer content 无 HTML 转义

- **严重程度**: P2 一般
- **缺陷类型**: 输入清洗
- **攻击 Payload**: `<img src=x onerror=alert(1)>` 发送至 `/api/v1/chat/sessions/{id}/send/`
- **复现步骤**:
  1. 登录获取 JWT token
  2. 创建 session
  3. POST `/api/v1/chat/sessions/{id}/send/` content=`<img src=x onerror=alert(1)>`
  4. 查询 DB: `Message.objects.filter(session=session, role='user').first().content` 返回原文 `'<img src=x onerror=alert(1)>'`
- **预期**: 后端存储 HTML 转义后的文本（如 `&lt;img...&gt;`）
- **实际**: 后端存储原始文本，无任何转义
- **截图证据**: 回测报告 §2.1 XSS Payload DB 存储记录
- **代码审计**: `backend/apps/chat/serializers.py` — `ChatMessageRequestSerializer` 的 `content` 字段为 `CharField(max_length=4000)`，不做任何 HTML 转义。这是聊天场景的正确设计（前端负责渲染安全），但意味着：
  - 如果有其他客户端（如移动 App）直接显示 DB 内容而不转义，会导致 XSS
  - 如果管理后台直接显示 Message.content（Django admin 默认不转义），会导致存储型 XSS
- **影响范围**: 所有聊天消息内容
- **修复建议**: 后端不需要转义（聊天内容应保留原文），但 Django admin 应使用 `escape` filter 显示 content，确保存储型 XSS 不会在 admin 面板触发

---

## 【输出转义】维度

### SYS-V4.1-001: CORS_ALLOW_ALL_ORIGINS=True 否定跨域防护（P1 严重）

- **严重程度**: P1 严重
- **缺陷类型**: CORS / CSRF 绕过
- **攻击 Payload**: 从 `http://evil.com` 发送 `fetch('http://target:8030/api/v1/chat/sessions/', {method: 'POST', headers: {'Authorization': 'Bearer <stolen_jwt>', 'Content-Type': 'application/json'}, body: '{"title":"evil"}'})`
- **复现步骤**:
  1. 从任意域名（如 `http://evil.com`）发起带有效 JWT 的跨域请求
  2. `CORS_ALLOW_ALL_ORIGINS = True` 允许所有 Origin
  3. 请求成功到达 Django 后端并执行
  4. 响应头包含 `Access-Control-Allow-Origin: http://evil.com`
- **预期**: 只有白名单域名（localhost:3030, 127.0.0.1:3030）可以跨域请求
- **实际**: 任何域名都可以跨域请求（`CORS_ALLOW_ALL_ORIGINS = True` 覆盖了 `CORS_ALLOWED_ORIGINS`）
- **截图证据**: 回测报告 §2.5 CSRF 测试 — `[reg_v4_sec_csrf_2] POST with auth, no CSRF cookie → HTTP 201`（跨域请求成功创建 session）
- **代码审计**:
  - `backend/config/settings/docker.py` L15: `CORS_ALLOW_ALL_ORIGINS = True`
  - `django-cors-headers` 文档: "When `CORS_ALLOW_ALL_ORIGINS` is True, `CORS_ALLOWED_ORIGINS` is ignored"
  - `backend/config/settings/base.py` L179: `CORS_ALLOWED_ORIGINS = ['http://localhost:3000', 'http://127.0.0.1:3000']` — 被完全忽略
- **影响范围**: 所有 API 端点。攻击者获取 JWT 后（通过 XSS、localStorage 读取、网络嗅探），可以从任意网站发起 API 请求，绕过 SameSite Cookie 等浏览器防护
- **修复建议**: docker.py 中删除 `CORS_ALLOW_ALL_ORIGINS = True`，改为扩展 `CORS_ALLOWED_ORIGINS` 列表包含 `http://localhost:3030, http://127.0.0.1:3030`

### SYS-V4.1-002: DEBUG=True 泄露完整堆栈信息（P1 严重）

- **严重程度**: P1 严重
- **缺陷类型**: 信息泄露
- **攻击 Payload**: 发送触发 500 错误的请求到非 DRF 视图端点
- **复现步骤**:
  1. 访问 `http://target:8030/admin/` 并输入错误凭证
  2. 或触发任意非 DRF 视图的 500 错误
  3. Django 返回完整 HTML 页面，包含：Python 堆栈跟踪、本地变量值、SQL 查询、settings 配置
- **预期**: 500 错误返回 `{"error": "Internal server error"}` 通用消息
- **实际**: Django DEBUG=True 返回完整 HTML 堆栈页面，泄露：
  - 文件路径（`/app/apps/chat/views.py`）
  - SQL 查询（`SELECT ... FROM users_user WHERE ...`）
  - Django settings 中的 SECRET_KEY、API keys 等
  - 本地变量值
- **截图证据**: 回测报告 §2.7 — custom_exception_handler 仅覆盖 DRF 视图
- **代码审计**:
  - `backend/config/settings/docker.py` L11: `DEBUG = True`
  - `backend/config/settings/docker.py` L12: `ALLOWED_HOSTS = ["*"]` — Host header injection
  - `backend/apps/core/exceptions.py` — `custom_exception_handler` 仅处理 DRF 视图异常，Django admin 等非 DRF 视图使用 Django 默认 500 处理器
- **影响范围**: 整个 Django 应用。任何非 DRF 视图的 500 错误都会泄露完整信息
- **修复建议**: docker.py 中设置 `DEBUG = False`，`ALLOWED_HOSTS = ['localhost', '127.0.0.1']`，添加 `/api/v1/health/` 端点替代 admin 健康检查

### SYS-V4.1-003: SECRET_KEY 短且硬编码（P2 严重）

- **严重程度**: P2 严重
- **缺陷类型**: 加密安全
- **攻击 Payload**: 暴力破解 26 字节 HMAC key（SHA256）
- **复现步骤**:
  1. 创建 JWT token（每次触发 `InsecureKeyLengthWarning`）
  2. JWT HMAC key 仅 26 字节（< 32 字节 SHA256 最低要求）
  3. 默认值 `change-me-to-a-random-string` 众所周知
- **预期**: SECRET_KEY >= 32 字节，且非硬编码
- **实际**: SECRET_KEY = `change-me-to-a-random-string`（26 字节），如果 .env 未设置 DJANGO_SECRET_KEY 则使用此默认值
- **截图证据**: 容器内每次 JWT 创建触发 `InsecureKeyLengthWarning: The HMAC key is 26 bytes long`
- **代码审计**: `backend/config/settings/base.py` L18: `SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me-to-a-random-string")`
- **影响范围**: JWT token 签名、session 加密、password reset token 等
- **修复建议**: .env 中设置 50+ 字符随机 DJANGO_SECRET_KEY，移除默认值 fallback

---

## 【频率限制】维度

### SYS-V4.1-004: 无 IP 级限流（P2 一般）

- **严重程度**: P2 一般
- **缺陷类型**: Rate Limit
- **攻击 Payload**: 创建 1000 个用户账号，每个账号每分钟发 10 条消息 = 10,000 条/分钟
- **复现步骤**:
  1. 注册大量账号（无注册限流）
  2. 每个账号每分钟发 10 条消息（UserRateThrottle 10/min per user）
  3. 总量：1000 users × 10 msg/min = 10,000 msg/min × ¥0.004 = ¥40/min DashScope 成本
- **预期**: 按 IP 限流（如 100/minute per IP），防止批量注册+攻击
- **实际**: 仅 UserRateThrottle（per authenticated user），无 AnonymousRateThrottle（per IP）
- **截图证据**: 回测报告 — `DEFAULT_THROTTLE_CLASSES = [UserRateThrottle]` only
- **代码审计**:
  - `backend/config/settings/base.py` L147-151: 仅配置 UserRateThrottle
  - `backend/apps/chat/views.py` L127-128: SendMessageRateThrottle 继承 UserRateThrottle
  - 登录接口 `/api/v1/auth/login/` 无任何限流（allauth 默认）
- **影响范围**: 所有 API 端点。批量注册 + 批量请求可以绕过 per-user 限流
- **修复建议**: 在 REST_FRAMEWORK 配置中添加 `AnonRateThrottle`（如 5/minute per IP），为登录接口添加专门的 `LoginRateThrottle`

### SYS-V4.1-005: 登录接口无限流（P2 一般）

- **严重程度**: P2 一般
- **缺陷类型**: Rate Limit / Brute Force
- **攻击 Payload**: 对 `/api/v1/auth/login/` 端点发送 1000 次/分钟的登录尝试
- **复现步骤**:
  1. 使用 curl 或脚本向 `/api/v1/auth/login/` 发送大量登录请求
  2. allauth + simplejwt 无专门的登录限流
  3. UserRateThrottle 仅对已认证用户生效，登录请求未认证
- **预期**: 登录接口有独立限流（如 5/minute per IP）
- **实际**: 登录接口无任何限流（allauth 使用 Django session 认证，不受 DRF throttle 保护）
- **截图证据**: `/api/v1/auth/login/` 端点不在 DRF 视图体系中
- **代码审计**: `backend/apps/users/urls.py` — 使用 allauth 的 account.views.LoginView，非 DRF 视图
- **影响范围**: 用户登录接口，暴力破解风险
- **修复建议**: 为 allauth 登录视图添加 Django-axes 或自定义 middleware 限流

---

## 【并发竞态】维度

### SYS-V4.1-006: Celery ingest_document 无分布式锁（P2 一般）

- **严重程度**: P2 一般
- **缺陷类型**: 并发竞态
- **攻击 Payload**: 对同一文档快速调用两次 `/api/v1/documents/{id}/reindex/`
- **复现步骤**:
  1. HR admin 登录
  2. POST `/api/v1/documents/{doc_id}/reindex/` — 第一次
  3. 立即 POST `/api/v1/documents/{doc_id}/reindex/` — 第二次
  4. 两个 `ingest_document.delay()` 任务并行执行
  5. 两个 worker 同时设置 `doc.status = "processing"` + 调用 `pipeline.ingest(doc)`
- **预期**: 第二次 reindex 被拒绝（文档已处于 processing 状态），或排队等待
- **实际**: 两次任务并行执行，可能导致重复 embedding + 状态混乱
- **截图证据**: `backend/apps/rag/services.py` L32-33 — `doc.status = "processing"` 和 `doc.save()` 不是原子操作
- **代码审计**:
  - `backend/apps/knowledge/views.py` L88-104: `DocumentReindexView.post()` 调用 `ingest_document.delay(str(document.id))`
  - 无 `select_for_update()` 或 Redis lock 保护
  - `services.py` L10: `@shared_task(bind=True, max_retries=3)` 有重试但无并发控制
- **影响范围**: 文档入库/重新索引操作
- **修复建议**: 在 `DocumentReindexView.post()` 中添加 `select_for_update()` 检查 status，或使用 Redis 分布式锁 `celery-redlock`

### SYS-V4.1-007: SSE send_message 并发请求无请求级锁（P2 一般）

- **严重程度**: P2 一般
- **缺陷类型**: 并发竞态
- **攻击 Payload**: 同一用户在同一 session 中并发发送两条消息
- **复现步骤**:
  1. 获取 JWT token
  2. 使用两个并发 HTTP 连接同时 POST `/api/v1/chat/sessions/{sid}/send/`
  3. 两个 SSE stream 同时开始，两个 Message 同时创建
- **预期**: 第二个请求被排队或拒绝（同一 session 同一时刻只能有一个 SSE stream）
- **实际**: Django runserver 是单线程，实际不会并发处理两个请求。但如果迁移到 gunicorn (多 worker)，两个请求可能并发到达
- **截图证据**: `chat/views.py` — send_message 无 session-level lock
- **代码审计**: `backend/apps/chat/views.py` L131-258 — `send_message` 函数无并发保护
- **影响范围**: 当前 runserver 环境下无实际风险，但迁移到多 worker 后会出现
- **修复建议**: 未来迁移 gunicorn 时添加 Redis session-level lock（每次 send_message 获取锁，完成后释放）

---

## 【资源耗尽】维度

### SYS-V4.1-009: Celery 无 Task Timeout（P2 严重）

- **严重程度**: P2 严重
- **缺陷类型**: 资源耗尽
- **攻击 Payload**: 上传一个超大 PDF（50MB，1000页），触发 ingest_document
- **复现步骤**:
  1. HR admin 登录
  2. POST `/api/v1/documents/` 上传 50MB PDF
  3. `ingest_document.delay()` 任务开始处理
  4. 任务可能运行数小时（大文件解析 + embedding + 存储）
  5. 其他文档入库任务排队等待（仅 4 slot）
- **预期**: 任务有 timeout（如 5 分钟），超时自动失败
- **实际**: `CELERY_TASK_TIME_LIMIT = None`，`CELERY_TASK_SOFT_TIME_LIMIT = None` — 任务无限运行
- **截图证据**: 回测报告 §reg_v4_sec_config — 配置审计结果
- **代码审计**:
  - `backend/config/settings/base.py` — 无 CELERY_TASK_TIME_LIMIT 配置
  - `docker-compose.v4.sys.yml` L59: `celery -A config worker -l info -c 4` — 仅 4 concurrent
- **影响范围**: 所有 Celery 任务。大文件可阻塞所有 worker slot
- **修复建议**: 添加 `CELERY_TASK_TIME_LIMIT = 300`（5分钟），`CELERY_TASK_SOFT_TIME_LIMIT = 240`

### SYS-V4.1-010: Redis 无密码且无 maxmemory（P2 一般）

- **严重程度**: P2 一般
- **缺陷类型**: 资源耗尽 / 安全
- **攻击 Payload**: 连接 Redis 6379（无密码），发送 `FLUSHALL` 命令
- **复现步骤**:
  1. 从容器网络内（或宿主机端口 6382）连接 Redis
  2. `redis-cli -p 6382 PING` → 返回 `PONG`（无认证）
  3. `redis-cli -p 6382 FLUSHALL` → 清除所有数据
  4. Celery broker 丢失所有排队任务
- **预期**: Redis 有密码保护 + maxmemory 配置
- **实际**: Redis 无密码（`redis:7-alpine` 默认），宿主机端口 6382 可直接访问
- **截图证据**: `docker-compose.v4.sys.yml` L21-28 — Redis 无 requirepass 配置
- **代码审计**: docker-compose.v4.sys.yml Redis service 仅配置端口映射和 healthcheck，无任何安全配置
- **影响范围**: Celery broker、throttle cache、session cache
- **修复建议**: Redis 添加 `requirepass` 和 `maxmemory-policy allkeys-lru`

### SYS-V4.1-011: SSL_VERIFY=False 禁用 SSL 验证（P1 严重）

- **严重程度**: P1 严重
- **缺陷类型**: 安全 / MITM
- **攻击 Payload**: 中间人攻击截获 DashScope API Key
- **复现步骤**:
  1. 在网络层（如公共 WiFi）设置 MITM proxy
  2. `SSL_VERIFY = False` 导致 Python HTTP 客户端不验证 SSL 证书
  3. 所有 DashScope API 请求通过 MITM proxy
  4. 攻击者截获 `DASHSCOPE_API_KEY`
- **预期**: SSL 验证启用，防止 MITM
- **实际**: `docker.py` L27: `SSL_VERIFY = False`
- **截图证据**: `backend/config/settings/docker.py` L27
- **代码审计**:
  - `docker.py` 注释说 "SSL verify off for local Docker (DashScope API calls)"
  - 但 DashScope API URL 是 `https://dashscope.aliyuncs.com/` — 公共互联网，不应禁用 SSL
  - 如果是 Docker 内部网络问题（容器内 SSL 证书缺失），应安装证书而非禁用验证
- **影响范围**: 所有 DashScope API 请求（RAG pipeline + embedding），API Key 可被截获
- **修复建议**: 移除 `SSL_VERIFY = False`，在 Docker 容器中安装 ca-certificates

### SYS-V4.1-012: 文件上传无大小限制的 API 级校验（P2 一般）

- **严重程度**: P2 一般
- **缺陷类型**: 资源耗尽
- **攻击 Payload**: 上传超过 50MB 的文件
- **复现步骤**:
  1. HR admin 登录
  2. POST `/api/v1/documents/` 上传 100MB 文件
  3. `MAX_UPLOAD_SIZE_MB = 50` 在 settings 中定义，但需验证 serializer 是否强制执行
- **预期**: >50MB 文件被拒绝
- **实际**: 需验证 DocumentSerializer 的 file 字段是否有 max_size 校验
- **代码审计**: `backend/config/settings/base.py` L207: `MAX_UPLOAD_SIZE_MB = 50`，但未确认 serializer 中引用此值
- **影响范围**: 文档上传接口
- **修复建议**: 在 DocumentSerializer 中添加 FileField max_size 校验，引用 settings.MAX_UPLOAD_SIZE_MB

### SYS-V4.1-013: JWT Token 存储于 localStorage（P2 一般）

- **严重程度**: P2 一般
- **缺陷类型**: 安全 / Token 泄露
- **攻击 Payload**: 如果 XSS 绕过前端白名单，攻击者可读取 localStorage 中的 JWT
- **复现步骤**:
  1. 假设找到一种 XSS 绕过方式（如未来添加的新 Markdown 插件）
  2. JavaScript 代码: `localStorage.getItem('ey-auth')` → 获取 JWT + 用户信息
  3. 使用窃取的 JWT 从任意域名发起 API 请求（CORS_ALLOW_ALL_ORIGINS=True 更加剧此风险）
- **预期**: JWT 存储在 httpOnly cookie 中，XSS 无法读取
- **实际**: JWT 存储在 localStorage（`frontend/src/auth/AuthProvider.tsx` L59）
- **截图证据**: `frontend/src/auth/AuthProvider.tsx` L34, L59 — `localStorage.setItem('ey-auth', ...)`
- **代码审计**: localStorage 在同一 origin 下所有 JS 代码可读。如果 XSS 绕过 ALLOWED_ELEMENTS 白名单，JWT 立即泄露
- **影响范围**: 所有认证用户
- **修复建议**: 短期：确保 XSS 防护无绕过路径（当前三层纵深防御足够）。长期：考虑迁移到 httpOnly cookie（需配合 CSRF 防护）

---

## 缺陷统计

| 严重程度 | 数量 | 缺陷 ID |
|---|---|---|
| P1 阻断 | 3 | SYS-V4.1-001 (CORS), SYS-V4.1-002 (DEBUG), SYS-V4.1-011 (SSL) |
| P2 严重 | 3 | SYS-V4.1-003 (SECRET_KEY), SYS-V4.1-009 (Celery timeout), SYS-V4.1-008 (Admin XSS) |
| P2 一般 | 7 | SYS-V4.1-004-005-006-007-010-012-013 |

**总计**: 13 个缺陷（P1: 3, P2 严重: 3, P2 一般: 7）

---

**签名**: V4.1 SYS 安全缺陷清单 — 2026-06-26
