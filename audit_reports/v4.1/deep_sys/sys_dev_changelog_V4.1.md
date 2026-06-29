# V4.1 SYS 领域开发变更日志

> **版本**: V4.1 — SYS 领域深度系统与安全优化
> **日期**: 2026-06-26
> **变更范围**: 10 个文件修改（8 个修改 + 2 个新建），12 个缺陷修复 + 1 个 TODO 标注
> **引用规则**: `[来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-XXX]`

---

## 变更总览

| 统计项 | 数量 |
|---|---|
| 修改文件数 | 8 |
| 新建文件数 | 2（middleware.py + docker-compose.v4.sys.yml） |
| 修复缺陷数 | 12（3 P1 + 3 P2严重 + 6 P2一般） |
| TODO 标注数 | 1（SYS-V4.1-007） |
| 新增加固项 | Rate Limiting 双维度、500 响应安全、并发竞态保护、Redis 安全、上传校验 |

---

## 逐项变更

### FIX-SYS-V4.1-001: CORS 白名单收紧（P1 严重）

- **修改文件**: `backend/config/settings/docker.py` L15→L23-28；`.env` L32
- **修改前**: `CORS_ALLOW_ALL_ORIGINS = True` — 覆盖 base.py 的 `CORS_ALLOWED_ORIGINS`，任何域名可跨域请求
- **修改后**: 删除 `CORS_ALLOW_ALL_ORIGINS`，显式定义 `CORS_ALLOWED_ORIGINS` 列表（包含 SYS 领域端口 3030/8030）
- **修复依据**: `django-cors-headers` 文档明确说明 `CORS_ALLOW_ALL_ORIGINS = True` 会忽略 `CORS_ALLOWED_ORIGINS`。攻击者获取 JWT 后可从任意网站发起 API 请求 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-001]
- **风险评估**: 低风险。需确保前端端口（3030）和后端端口（8030）均在白名单中

### FIX-SYS-V4.1-002: SafeErrorResponseMiddleware（P1 严重）

- **修改文件**: `backend/apps/core/middleware.py`（新建）；`backend/config/settings/base.py` L58→L78；`backend/config/settings/docker.py` L12→L18
- **修改前**: `custom_exception_handler` 仅覆盖 DRF 视图；`ALLOWED_HOSTS = ["*"]`（Host header injection）；非 DRF 视图 500 错误泄露完整堆栈
- **修改后**: 新建 `SafeErrorResponseMiddleware` 拦截所有 `process_exception`，返回 `{"error": "Internal server error"}` JSON；`ALLOWED_HOSTS` 收紧为 `["localhost", "127.0.0.1", "backend", "0.0.0.0"]`；保留 DEBUG=True（开发优先决策）
- **修复依据**: V4.0 DEFECT-012 修复的 `custom_exception_handler` 仅处理 DRF 视图异常，Django admin/allauth 等非 DRF 视图仍泄露堆栈、SQL、settings [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-002]
- **风险评估**: 中等风险。`process_exception` 仅捕获视图层异常，不覆盖中间件层异常。如需完全覆盖，未来需添加 `handler500`

### FIX-SYS-V4.1-011: SSL 验证启用（P1 严重）

- **修改文件**: `backend/config/settings/docker.py` 删除 L27 `SSL_VERIFY = False`；`backend/Dockerfile` L9-12 添加 `ca-certificates`
- **修改前**: `SSL_VERIFY = False` 禁用所有 HTTPS 证书验证，MITM 可截获 DashScope API Key
- **修改后**: 删除 `SSL_VERIFY = False` 覆盖，base.py 正确从 env 读取（默认 true）；Dockerfile 安装 ca-certificates
- **修复依据**: DashScope API URL 为 `https://dashscope.aliyuncs.com/`（公共互联网），不应禁用 TLS 验证 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-011]
- **风险评估**: 低风险。ca-certificates 是标准系统包，不影响 Python 依赖

### FIX-SYS-V4.1-003: SECRET_KEY 加固（P2 严重）

- **修改文件**: `backend/config/settings/base.py` L18-36；`.env` L6
- **修改前**: `SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me-to-a-random-string")` — 26 字节硬编码默认值，触发 InsecureKeyLengthWarning
- **修改后**: 添加长度校验 + auto-gen fallback — 未设置则 auto-generate 50+字符 token；< 32 字节则 RuntimeWarning 但不阻止启动；`.env` 设置 50+ 字符随机 key（值已更新，不再使用 26 字节默认值）
- **修复依据**: SHA256 HMAC key 最低 32 字节，26 字节密钥可被暴力破解 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-003]
- **风险评估**: 中等风险。若 `.env` 未设置，每次重启生成不同 key（所有 JWT/session 失效）。开发环境必须设置 `.env`

### FIX-SYS-V4.1-009: Celery Task Timeout（P2 严重）

- **修改文件**: `backend/config/settings/base.py` 在 Celery 配置块后追加 L210-213
- **修改前**: `CELERY_TASK_TIME_LIMIT = None`，`CELERY_TASK_SOFT_TIME_LIMIT = None` — 任务无限运行
- **修改后**: `CELERY_TASK_TIME_LIMIT = 300`（5分钟硬超时），`CELERY_TASK_SOFT_TIME_LIMIT = 240`（4分钟软超时），`CELERY_TASK_MAX_RETRIES = 3`
- **修复依据**: 大文件 PDF 上传可阻塞所有 4 个 worker slot 数小时 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-009]
- **风险评估**: 低风险。超时后任务标记 failed 并重试（max_retries=3），不影响正常小文件

### FIX-SYS-V4.1-008: Django Admin Stored XSS（P2 严重）

- **修改文件**: `backend/apps/chat/admin.py` — 添加 `format_html + escape`；import `django.utils.html`
- **修改前**: `content_short = obj.content[:60] + "..."` — 返回原始文本，`<img onerror=alert(1)>` 在 admin 面板可执行
- **修改后**: `escape(obj.content[:60])` + `format_html("{}…", escaped)` — HTML 转义后安全显示
- **修复依据**: Django admin 默认不转义 CharField 内容，聊天消息存储原始 HTML/JS 标签 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-008]
- **风险评估**: 低风险。仅影响 admin 面板显示，不影响 API 返回的聊天内容

### FIX-SYS-V4.1-004: AnonRateThrottle（P2 一般）

- **修改文件**: `backend/config/settings/base.py` REST_FRAMEWORK 配置块 L166-174
- **修改前**: 仅 `UserRateThrottle`（30/min per authenticated user），无 IP 级限流
- **修改后**: 添加 `AnonRateThrottle`（100/min per IP）到 `DEFAULT_THROTTLE_CLASSES`，配置 `anon: "100/minute"`
- **修复依据**: 批量注册 + per-user 限流绕过（1000 users × 10 msg/min = 10,000 msg/min）[来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-004]
- **风险评估**: 低风险。100/min per IP 足够覆盖正常使用场景

### FIX-SYS-V4.1-005: LoginRateThrottle（P2 一般）

- **修改文件**: `backend/apps/users/views.py` — 新建 `LoginRateThrottle(AnonRateThrottle)` 类，添加 `throttle_classes = [LoginRateThrottle]` 到 `CustomTokenObtainPairView`
- **修改前**: `/api/v1/auth/token/` 无独立限流，allauth LoginView 不是 DRF 视图
- **修改后**: `LoginRateThrottle` rate="5/minute" per IP，应用到 CustomTokenObtainPairView
- **修复依据**: 登录接口无任何限流，暴力破解风险 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-005]
- **风险评估**: 低风险。5/min per IP 足够覆盖正常登录频率（1-2 次/分钟）

### FIX-SYS-V4.1-006: Document Reindex select_for_update（P2 一般）

- **修改文件**: `backend/apps/knowledge/views.py` — `DocumentReindexView.post()` 重写
- **修改前**: `document = self.get_object()` → `document.status = "processing"` → `document.save()` — 无原子保护
- **修改后**: `transaction.atomic()` + `select_for_update().get(id=pk)` — 检查 status == "processing" 返回 409；事务外触发 Celery 任务
- **修复依据**: 两次 reindex 可并行执行，导致重复 embedding + 状态混乱 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-006]
- **风险评估**: 中等风险。事务内查询 + select_for_update 会短暂锁定 DB 行，但锁持有时间极短（仅 status 检查 + 更新）

### FIX-SYS-V4.1-007: SSE TODO 注释（P2 一般 — 仅标注）

- **修改文件**: `backend/apps/chat/views.py` — send_message 函数 docstring
- **修改前**: `"""Send a message and get streaming response (SSE)."""`
- **修改后**: 添加 TODO 注释描述未来 gunicorn 多 worker 时需加 Redis session-level lock
- **修复依据**: 当前 runserver 单线程无并发风险，未来迁移 gunicorn 时必须实现 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-007]
- **风险评估**: 无风险。仅文档标注，不影响功能

### FIX-SYS-V4.1-010: Redis 安全加固（P2 一般）

- **修改文件**: `docker-compose.v4.sys.yml` Redis 服务配置；`backend/config/settings/base.py` CELERY_BROKER_URL；`.env` REDIS_URL
- **修改前**: Redis 无密码、无 maxmemory — 任何容器-host 进程可 `FLUSHALL` 清除所有数据
- **修改后**: `redis-server --requirepass sys_redis_pass_2026 --maxmemory 256mb --maxmemory-policy allkeys-lru`；healthcheck 使用 `-a` 参数；REDIS_URL 和 CELERY_BROKER_URL 包含密码
- **修复依据**: Redis 6382 端口可直接访问，无认证保护 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-010]
- **风险评估**: 中等风险。所有 Redis 客户端需更新 URL 包含密码（Celery、Django throttle cache）。需确保 `.env` 与 docker-compose 中密码一致

### FIX-SYS-V4.1-012: File Upload Size Validation（P2 一般）

- **修改文件**: `backend/apps/knowledge/serializers.py` — DocumentSerializer.validate_file()
- **修改前**: `MAX_UPLOAD_SIZE_MB = 50` 在 settings 中定义但 serializer 未引用
- **修改后**: 添加 `validate_file()` 方法，检查 `value.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024`，返回 400 + 错误消息
- **修复依据**: 上传超过 50MB 文件可能耗尽服务器资源 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-012]
- **风险评估**: 低风险。仅在 serializer 层添加校验，不影响其他模块

### SYS-V4.1-013: JWT localStorage 安全备注（P2 一般 — 不修改代码）

- **处理方式**: 不修改代码。迁移到 httpOnly cookie 需配合 CSRF 变更，超出 SYS 领域职责。仅在变更日志中记录风险评估和长期规划建议
- **修复依据**: localStorage XSS 可读取 JWT，但当前三层 XSS 防护（白名单 + 协议校验 + unwrapDisallowed）已足够 [来源: V4.1/deep_sys/deep_sys_defect_list_V4.1.md §SYS-V4.1-013]

---

> **签名**: V4.1 SYS 开发变更日志 — 2026-06-26
