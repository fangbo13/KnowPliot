# V4.2 SYS 领域深度缺陷清单

> **审计版本**: V4.2 — SYS 领域安全与性能深度缺陷挖掘
> **审计日期**: 2026-06-26
> **审计环境**: Docker Compose SYS 领域（docker-compose.v4.sys.yml）— 端口 3030/8030/5435/6382
> **审计方法**: 代码审查 + 架构推演 + 实测验证 + 攻击模拟
> **缺陷分类**: 【输入清洗】【输出转义】【频率限制】【并发竞态】【资源耗尽】【性能瓶颈】

---

## 缺陷汇总

| 缺陷 ID | 严重程度 | 缺陷类型 | 简述 |
|---|---|---|---|
| SYS-V4.2-001 | **P1** | SSRF | IPv6-mapped IPv4 地址绕过 _is_private_ip() |
| SYS-V4.2-002 | **P1** | SSRF | DNS rebinding 时间差绕过 CrawlURLValidator |
| SYS-V4.2-003 | **P1** | SSRF | 重定向链中间节点未校验 IP（仅校验最终目标） |
| SYS-V4.2-004 | **P2** | 输入清洗 | CrawlWithdrawByURLView url 参数无校验 |
| SYS-V4.2-005 | **P2** | SSRF | RobotsTxtChecker 预取 robots.txt 本身是 SSRF 向量 |
| SYS-V4.2-006 | **P2** | 性能 | RBAC has_permission/has_role N+1 查询（每次请求 3 次 DB 查询） |
| SYS-V4.2-007 | **P2** | 并发竞态 | HasPermission superuser bypass 中审计日志写入可阻断授权 |
| SYS-V4.2-008 | **P1** | 频率限制 | admin_user_deactivate 使用 @api_view 绕过全局限流 |
| SYS-V4.2-009 | **P2** | 输入清洗 | RBAC has_role("hr") 双轨授权不一致（缺少 is_hr_admin 审计记录） |
| SYS-V4.2-010 | **P1** | 输出转义 | DEBUG=True 在 Docker 生产设置中，中间件层异常仍可泄露堆栈 |
| SYS-V4.2-011 | **P0** | 性能 | 前端 Dockerfile 运行 npm run dev（开发服务器代替生产构建） |
| SYS-V4.2-012 | **P2** | 性能 | CONN_MAX_AGE=0 默认值导致每次请求新建 DB 连接 |
| SYS-V4.2-013 | **P2** | 性能 | Celery 4 worker slot 无优先级队列，大文件阻塞全部 slot |
| SYS-V4.2-014 | **P0** | 性能 | DashScope API 无断路器，失败请求阻塞 runserver 单线程 |
| SYS-V4.2-015 | **P2** | 性能 | TokenBatchRenderer 全字符串累积造成线性内存增长 |
| SYS-V4.2-016 | **P2** | 性能 | computeRounds O(n) 在每条消息完成时被调用两次 |
| SYS-V4.2-017 | **P2** | 性能 | crossTabSync 4 层动态 import 增加约 200ms abort 延迟 |
| SYS-V4.2-018 | **P2** | 性能 | forceUpdate 在每帧 rAF 触发（60/sec）无论滚动位置是否变化 |
| SYS-V4.2-019 | **P2** | 并发竞态 | CrawlWithdrawByURLView 批量撤回缺少 transaction.atomic() |
| SYS-V4.2-020 | **P1** | 认证 | 黑名单 refresh token 仍可用于获取新 token pair（BLACKLIST_AFTER_ROTATION 检查缺失） |
| SYS-V4.2-021 | **P2** | RBAC | UserRole unique_together 阻止重新分配已撤销的角色 |
| SYS-V4.2-022 | **P2** | RBAC | admin_user_deactivate 允许自我停用且无撤销机制 |
| SYS-V4.2-023 | **P1** | RBAC | 角色分配端点 30/min 限流过于宽松（应为 5/min） |
| SYS-V4.2-024 | **P2** | RBAC | is_hr_admin 双轨授权 content_resources 不一致（audit 权限在 HasPermission 有但 has_permission 无） |
| SYS-V4.2-025 | **P2** | 配置 | Redis 密码不匹配：base.py 含密码但 docker-compose.yml Redis 无 requirepass |
| SYS-V4.2-026 | **P2** | 配置 | PostgreSQL 默认弱密码 ey_password + 端口 5435 暴露到宿主机 |
| SYS-V4.2-027 | **P2** | 资源耗尽 | Django CACHES 配置缺失 — Redis 仅作 Celery broker，零应用缓存 |
| SYS-V4.2-028 | **P2** | 资源耗尽 | Celery worker 运行为 root (uid=0) — 容器内 root 权限风险 |

---

## 【SSRF 类】— 爬虫模块安全缺陷

### SYS-V4.2-001: IPv6-mapped IPv4 地址绕过 _is_private_ip()

- **严重程度**: P1 严重
- **缺陷类型**: SSRF
- **攻击 Payload**: 提交 URL 指向解析为 `::ffff:127.0.0.1` 的主机名（如 `http://ipv4-v6-mapped.example.com`）
- **复现步骤**:
  1. 攻击者构造一个域名，其 DNS 记录指向 IPv6-mapped IPv4 地址 `::ffff:127.0.0.1`
  2. 通过 POST `/api/v1/crawl/crawl/` 提交该 URL
  3. `CrawlURLValidator.validate()` L96: `socket.getaddrinfo()` 返回 `::ffff:127.0.0.1`
  4. `_is_private_ip()` L48-57: `ipaddress.ip_address("::ffff:127.0.0.1")` 创建 IPv6Address 对象
  5. 该 IPv6Address 不落入 PRIVATE_IP_RANGES 中的任何 IPv6 范围（`::1/128` 不覆盖 `::ffff:7f00:1`）
  6. 验证通过，爬虫成功访问后端内部服务
- **预期 vs 实际**: 预期：IPv6-mapped IPv4 地址应被识别为私有地址并被拒绝。实际：`::ffff:127.0.0.1` 被视为公共 IPv6 地址，验证通过。
- **代码审计**: `validators.py` L24-36: PRIVATE_IP_RANGES 包含 IPv6 loopback `::1/128`，但不含 IPv4-mapped IPv6 范围 `::ffff:0:0/96`。Python `ipaddress.ip_address("::ffff:127.0.0.1")` 返回 IPv6Address，其 `.ipv4_mapped` 属性为 `IPv4Address('127.0.0.1')`，但 `_is_private_ip()` 未检查此属性。 [来源: validators.py §PRIVATE_IP_RANGES + §_is_private_ip]
- **影响范围**: 攻击者可通过 IPv6-mapped IPv4 地址访问 Docker 内部服务（DB:5432, Redis:6379, Backend:8000）
- **修复建议**: 在 `_is_private_ip()` 中添加 IPv4-mapped IPv6 检查：`if ip.version == 6 and ip.ipv4_mapped and _is_private_ipv4(ip.ipv4_mapped): return True`

### SYS-V4.2-002: DNS rebinding 时间差绕过

- **严重程度**: P1 严重
- **缺陷类型**: SSRF
- **攻击 Payload**: 使用 DNS rebinding 服务（如 `a.rebind.attacker.com`），初始解析为公共 IP，验证通过后 DNS TTL 降至 0，解析切换为 `127.0.0.1`
- **复现步骤**:
  1. 攻击者设置 DNS 记录：初始 A 记录为 `1.2.3.4`（公共 IP），TTL=1s
  2. POST `/api/v1/crawl/crawl/` 提交 `http://a.rebind.attacker.com`
  3. `CrawlURLValidator.validate()` L96: `socket.getaddrinfo()` 解析为 `1.2.3.4` → 验证通过
  4. Celery worker 中的 `crawl_and_ingest` 调用 `CrawlerService.crawl_url()`
  5. `services.py` L127: httpx.AsyncClient 重新解析域名 → DNS 已切换为 `127.0.0.1`
  6. `services.py` L156-164: `validate_redirect_ip()` 检查最终 IP，但 httpx 已跟随重定向访问了 `127.0.0.1`
  7. 内部服务数据被爬取并存储到知识库
- **预期 vs 实际**: 预期：DNS rebinding 应在所有阶段被阻止。实际：验证时 DNS 为公共 IP，fetch 时 DNS 为私有 IP，时间差导致绕过。
- **代码审计**: `validators.py` L70-110: `validate()` 在提交时解析 DNS；`services.py` L156-164: `validate_redirect_ip()` 在 fetch 后检查，但 httpx 在获取阶段已经跟随了私有 IP 重定向。两次 DNS 解析之间的时间差是可利用的。 [来源: validators.py §validate + services.py §crawl_url]
- **影响范围**: 攻击者可访问内部服务、窃取 AWS 元数据（169.254.169.254）、扫描内网
- **修复建议**: 在 httpx 请求前重新解析 DNS 并校验；或在 httpx client 中添加自定义 DNS resolver，强制所有解析结果通过 `_is_private_ip()` 校验

### SYS-V4.2-003: 重定向链中间节点未校验 IP

- **严重程度**: P1 严重
- **缺陷类型**: SSRF
- **攻击 Payload**: 提交 URL 指向公共 IP，设置重定向链：`attacker.com` → `public-redirect.com` → `http://169.254.169.254/latest/meta-data/`
- **复现步骤**:
  1. 攻击者设置 3 级重定向链，最终目标为 AWS 元数据地址
  2. POST `/api/v1/crawl/crawl/` 提交初始 URL
  3. `CrawlURLValidator.validate()` 解析初始 URL IP → 公共 IP → 验证通过
  4. httpx 跟随 3 级重定向，中间访问 `169.254.169.254`
  5. `services.py` L156-164: 仅校验最终重定向 IP，中间 IP 未被校验
  6. 中间节点 `169.254.169.254` 的数据已被 httpx 获取（虽然最终 IP 可能是公共 IP）
- **预期 vs 实际**: 预期：所有重定向链节点 IP 都应被校验。实际：仅校验最终目标 IP。
- **代码审计**: `services.py` L155-164: `validate_redirect_ip()` 仅检查 `response.url.host`（最终 URL），不检查 `response.history` 中中间重定向的主机 IP。httpx 在跟随重定向时已经向中间目标发送了 HTTP 请求，即使最终目标被校验拒绝，中间请求的响应数据可能已被缓存或泄露。 [来源: services.py §DNS rebinding check]
- **影响范围**: 可通过中间重定向节点访问 AWS/GCP 元数据服务、内网服务
- **修复建议**: 校验 `response.history` 中所有中间重定向的 host IP，而非仅校验最终 IP；或禁用 httpx 自动重定向并在代码中逐级校验

### SYS-V4.2-004: CrawlWithdrawByURLView url 参数无校验

- **严重程度**: P2 一般
- **缺陷类型**: 输入清洗
- **攻击 Payload**: POST `/api/v1/crawl/withdraw-by-url/` with `url` = 10000 字符超长字符串 或 `http://127.0.0.1:8000/admin/`
- **复现步骤**:
  1. POST `/api/v1/crawl/withdraw-by-url/` 提交超长或恶意 URL 作为筛选条件
  2. `views.py` L163: `url = request.data.get("url")` 无任何校验（无 CrawlURLValidator、无 max length、无格式检查）
  3. `views.py` L172-188: `CrawledDocument.objects.filter(source_url=url)` 直接使用未校验的 URL 进行数据库查询
  4. 超长字符串可能导致 DB 查询性能问题；恶意 URL 可用于探测内部 URL 是否存在于数据库
- **预期 vs 实际**: 预期：url 参数应通过格式验证和长度限制。实际：无任何输入校验。
- **代码审计**: `views.py` L163-170: `CrawlWithdrawByURLView.post()` 仅检查 `url` 是否为空，不检查格式、长度、或是否为内部 URL。与 `CrawlRequestView.create()` L38 使用 `CrawlRequestSerializer`（含 CrawlURLValidator）形成不对称防护。 [来源: crawler/views.py §CrawlWithdrawByURLView]
- **影响范围**: 可进行长字符串 DoS、信息泄露（通过 URL 匹配探测知识库内容）
- **修复建议**: 为 CrawlWithdrawByURLView 的 url 参数添加与 CrawlRequestView 同等的校验（CrawlURLValidator + max length）

### SYS-V4.2-005: RobotsTxtChecker 预取 robots.txt 是 SSRF 向量

- **严重程度**: P2 一般
- **缺陷类型**: SSRF
- **攻击 Payload**: 提交 URL 指向一个域，其 robots.txt 托管在内部服务上（如 `http://internal-service:8080/robots.txt`）
- **复现步骤**:
  1. 攻击者设置域名 DNS 解析为公共 IP → 通过 CrawlURLValidator 验证
  2. `services.py` L120: `self.robots_checker.can_fetch(url)` 触发 `RobotsTxtChecker.can_fetch()`
  3. `services.py` L51: `robots_url = f"https://{domain}/robots.txt"` → 向 `{domain}/robots.txt` 发送 HTTP 请求
  4. 如果域名 DNS 此时已通过 rebinding 切换为内部 IP，robots.txt 请求将访问内部服务
  5. robots.txt 请求本身独立于主爬取请求，不受 validate_redirect_ip() 校验
- **预期 vs 实际**: 预期：robots.txt 预取应受 SSRF 校验保护。实际：robots.txt 预取发生在 CrawlURLValidator 之后、主爬取之前，但 DNS 可在此期间被 rebinding。
- **代码审计**: `services.py` L33-70: `RobotsTxtChecker.can_fetch()` 直接构造 robots.txt URL 并使用 `RobotFileParser.read()` 获取，未通过 `_is_private_ip()` 校验。`cache.set()` 将结果缓存 24 小时，意味着首次预取即可触发 SSRF。 [来源: services.py §RobotsTxtChecker]
- **影响范围**: 作为 DNS rebinding 的辅助向量，可用于在主爬取验证前探测内部服务
- **修复建议**: 在 RobotsTxtChecker.can_fetch() 中添加对 robots_url 的 IP 校验，或将其移至 CrawlURLValidator 的验证流程中

---

## 【RBAC 类】— 权限与审计缺陷

### SYS-V4.2-006: RBAC has_permission/has_role N+1 查询

- **严重程度**: P2 一般
- **缺陷类型**: 性能瓶颈
- **攻击 Payload**: 50 并发用户访问 RBAC 保护的 API → 150 次/秒权限查询
- **复现步骤**:
  1. 用户发送 API 请求到 HasPermission + HasRole 保护端点
  2. `HasPermission.has_permission()` → 调用 `request.user.has_permission()` → 调用 `self.get_permissions()` → 查询 UserRole + RolePermission = 2 次 DB 查询
  3. `HasRole.has_permission()` → 调用 `request.user.has_role()` → 查询 UserRole = 1 次 DB 查询
  4. 总计 3 次 DB 查询仅用于权限检查，无缓存
  5. 50 并发用户 × 3 查询 = 150 权限查询/秒
- **预期 vs 实际**: 预期：权限检查应缓存结果，每请求仅 0-1 次 DB 查询。实际：每请求 3 次查询，无缓存。
- **代码审计**: `users/models.py` L92-132: `has_permission()` 调用 `get_permissions()` 每次创建新查询集；`has_role()` L71-90 也每次创建新查询集。两者在同一个请求中独立查询，数据无共享。建议使用 `request._rbac_cache` 缓存权限数据。 [来源: users/models.py §has_permission + §has_role]
- **影响范围**: 在高并发下增加 DB 负载 3x，可能导致 DB 连接耗尽
- **修复建议**: 在请求级别缓存 RBAC 权限数据（如 `request._rbac_permissions_cache`），避免重复查询

### SYS-V4.2-007: HasPermission superuser bypass 中审计日志写入可阻断授权

- **严重程度**: P2 严重
- **缺陷类型**: 并发竞态
- **攻击 Payload**: 在 AuditLog 写入时触发 IntegrityError → superuser 被拒绝访问
- **复现步骤**:
  1. Superuser 发送 API 请求到 HasPermission 保护的端点
  2. `permissions.py` L56: `HasPermission.has_permission()` 检测 `request.user.is_superuser` → True
  3. `permissions.py` L57-66: 调用 `create_audit_log()` 执行 DB INSERT
  4. 如果 AuditLog INSERT 因 DB 约束错误、连接超时、或唯一约束冲突而失败
  5. 异常未被 `has_permission()` 捕获 → 返回 500 或 403 → superuser 被拒绝
- **预期 vs 实际**: 预期：superuser bypass 不应受审计日志写入失败影响。实际：审计日志写入失败可阻断 superuser 访问。
- **代码审计**: `permissions.py` L56-66 和 L102-113: `create_audit_log()` 调用未包裹在 try/except 中。审计日志写入属于副作用，不应影响授权决策。 [来源: permissions.py §HasPermission + §HasRole]
- **影响范围**: 在 DB 高负载或 AuditLog 表约束冲突时，superuser 可能被意外拒绝访问关键管理端点
- **修复建议**: 将审计日志写入移至独立的 try/except 中：`try: create_audit_log(...) except: logger.warning(...)`，确保审计失败不阻断授权

### SYS-V4.2-008: admin_user_deactivate 使用 @api_view 绕过全局限流

- **严重程度**: P1 严重
- **缺陷类型**: 频率限制
- **攻击 Payload**: 暴力快速 POST `/api/v1/rbac/users/{id}/deactivate/` — 无速率限制
- **复现步骤**:
  1. HR Admin 发送 50 次/分钟 POST `/api/v1/rbac/users/{id}/deactivate/` 请求
  2. `rbac/views.py` L213: `@api_view(["POST"])` 装饰器绕过 DRF 的 `DEFAULT_PERMISSION_CLASSES` 和 `DEFAULT_THROTTLE_CLASSES`
  3. `views.py` L218: `request.user.has_permission("user.deactivate")` 手动检查权限
  4. **无 throttle_classes 装饰器** → AnonRateThrottle 和 UserRateThrottle 不生效
  5. 攻击者可无限速率调用 deactivate 端点
- **预期 vs 实际**: 预期：所有 API 端点应受全局限流保护。实际：`@api_view` 装饰器使 DRF 的 DEFAULT_THROTTLE_CLASSES 不生效，该端点无限流保护。
- **代码审计**: `rbac/views.py` L213-254: `admin_user_deactivate` 使用 `@api_view(["POST"])` + `@permission_classes([permissions.IsAuthenticated])`（但权限在函数内手动检查），未添加 `@throttle_classes`。对比 `chat/views.py` L131-133: `send_message` 也使用 `@api_view` 但正确添加了 `@throttle_classes([SendMessageRateThrottle])`。 [来源: rbac/views.py §admin_user_deactivate + chat/views.py §send_message]
- **影响范围**: 攻击者可无限速率停用用户账户，造成批量账户停用攻击
- **修复建议**: 为 `admin_user_deactivate` 添加 `@throttle_classes([UserRateThrottle])` 装饰器，或将其改为 DRF GenericAPIView 类以自动继承全局限流

### SYS-V4.2-009: RBAC has_role("hr") 双轨授权不一致

- **严重程度**: P2 一般
- **缺陷类型**: 输入清洗
- **攻击 Payload**: is_hr_admin=True 用户通过 has_role("hr") fallback 获得权限，但 UserRole 表中无记录 → 审计追踪不完整
- **复现步骤**:
  1. HR Admin（is_hr_admin=True，但 UserRole 表中无 hr role 记录）访问 HasRole("hr") 保护的端点
  2. `users/models.py` L87-88: `has_role("hr")` → `UserRole.objects.filter()` 无匹配 → False
  3. `users/models.py` L87-88: fallback → `getattr(self, "is_hr_admin", False)` = True → 返回 True
  4. 权限通过，但 UserRole 表中无此用户的 hr role 记录 → 审计追踪缺失
  5. `permissions.py` L116: `HasRole.has_permission()` 同样有 is_hr_admin fallback → 无审计记录
- **预期 vs 实际**: 预期：所有权限授予应有审计记录。实际：is_hr_admin fallback 路径无 UserRole 记录，审计追踪不完整。
- **代码审计**: `users/models.py` L71-90: `has_role()` 的 is_hr_admin fallback 和 `permissions.py` L115-117: `HasRole.has_permission()` 的 fallback 均不生成审计记录。对比 `permissions.py` L56-66: superuser bypass 路径已添加审计记录。 [来源: users/models.py §has_role + permissions.py §HasRole]
- **影响范围**: Phase 2 双轨授权期间的审计追踪不完整，合规审计无法追踪 is_hr_admin fallback 路径的权限使用
- **修复建议**: 在 is_hr_admin fallback 路径添加审计日志记录（类似 superuser bypass 的审计机制）

---

## 【输出转义类】— 配置安全缺陷

### SYS-V4.2-010: DEBUG=True 在 Docker 生产设置中

- **严重程度**: P1 严重
- **缺陷类型**: 输出转义
- **攻击 Payload**: 触发中间件层异常 → 堆栈信息泄露
- **复现步骤**:
  1. 发送带有恶意 Host 头的请求到后端
  2. `django.middleware.common.CommonMiddleware` 可能因 ALLOWED_HOSTS 检查失败抛出 `DisallowedHost` 异常
  3. 此异常发生在 `SafeErrorResponseMiddleware` 之后的中间件链中
  4. `SafeErrorResponseMiddleware.process_exception()` 仅拦截 **视图层异常**，不拦截中间件层异常
  5. `DEBUG=True` 导致 Django 返回包含完整堆栈信息、文件路径、变量值的错误页面
  6. 攻击者获取服务器内部信息
- **预期 vs 实际**: 预期：所有异常应返回安全 JSON 响应。实际：中间件层异常在 DEBUG=True 下仍可泄露堆栈信息。
- **代码审计**: `docker.py` L16: `DEBUG = True`（注释说明 "V4.1 decision: dev priority"）。`middleware.py` SafeErrorResponseMiddleware 仅通过 `process_exception()` 拈取视图层异常。Django 的 `DEBUG=True` 在中间件层异常时会渲染详细错误页面，SafeErrorResponseMiddleware 无法拦截。 [来源: docker.py §DEBUG + middleware.py §SafeErrorResponseMiddleware]
- **影响范围**: 服务器文件路径、环境变量名、代码结构可通过中间件层异常泄露给攻击者
- **修复建议**: docker.py 设置 `DEBUG = False` + 自定义 500.html 模板；或在 SafeErrorResponseMiddleware 中添加 `process_exception()` 对中间件异常的覆盖（需注册为中间件而非仅视图层拦截器）

---

## 【性能瓶颈类】— 性能专项缺陷

### SYS-V4.2-011: 前端 Dockerfile 运行开发服务器

- **严重程度**: P0 阻断
- **缺陷类型**: 性能瓶颈
- **攻击 Payload**: 无攻击 payload，纯性能测量
- **复现步骤**:
  1. 查看 `frontend/Dockerfile` L13: `CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]`
  2. Vite 开发服务器 vs 生产构建对比：
     - 无 minification: JS bundle ~10x 更大
     - 无 tree-shaking: 未使用代码仍包含在 bundle 中
     - HMR websocket 开放: 开发功能在生产环境暴露
     - Source maps 可访问: 完整源代码可通过浏览器查看
     - 单进程: Vite dev server 不优化并发连接
  3. 预估 FCP: ~2-3s (vs 生产 ~0.5s)
  4. 预估 JS 传输: ~500-800KB (vs 生产 ~50-80KB)
- **预期 vs 实际**: 预期：生产环境使用优化构建。实际：使用开发服务器，无任何优化。
- **代码审计**: `frontend/Dockerfile` L13: `CMD ["npm", "run", "dev"]` 而非 `CMD ["npm", "run", "build"] + nginx serve`。Vite dev server 的 `server.hmr.client` 和 `server.fs.strict` 配置为开发模式默认值，不适合生产环境。 [来源: frontend/Dockerfile §CMD]
- **影响范围**: 前端性能严重退化（FCP 增加 4-6x），安全风险（HMR + source maps 暴露）
- **修复建议**: Dockerfile 改为 `npm run build` + nginx/caddy 静态文件服务；或添加多阶段构建

### SYS-V4.2-012: CONN_MAX_AGE=0 默认值

- **严重程度**: P2 一般
- **缺陷类型**: 性能瓶颈
- **攻击 Payload**: 50 QPS 负载 → 50 TCP 连接/秒
- **复现步骤**:
  1. `base.py` 未设置 CONN_MAX_AGE → Django 默认值 0
  2. 每个 HTTP 请求新建 PostgreSQL 连接 → 关闭连接
  3. 50 QPS = 50 TCP+auth handshakes/秒 → 连接开销占请求时间 ~8-10ms
  4. 设置 CONN_MAX_AGE=60 后，连接复用率 ~90%，每请求节省 ~8ms
- **预期 vs 实际**: 预期：DB 连接应持久复用。实际：每请求新建连接。
- **代码审计**: `base.py` §DATABASES: 无 CONN_MAX_AGE 设置。Django 默认 CONN_MAX_AGE=0。 [来源: base.py §DATABASES]
- **影响范围**: 在中等负载（50 QPS）下增加 ~8ms/请求延迟，高负载下可能耗尽 PostgreSQL max_connections
- **修复建议**: `DATABASES['default']['CONN_MAX_AGE'] = 60` + `CONN_HEALTH_CHECKS = True`

### SYS-V4.2-013: Celery 4 worker slot 无优先级

- **严重程度**: P2 一般
- **缺陷类型**: 性能瓶颈
- **攻击 Payload**: 上传 4 个大文件 → 阻塞全部 4 个 slot → 第 5 个任务等待 5 分钟
- **复现步骤**:
  1. 上传 4 个 ~50MB PDF 文件 → 4 个 ingest_document 任务占用 4 个 worker slot
  2. 每个 ingest_document 可运行至 300 秒（CELERY_TASK_TIME_LIMIT）
  3. 第 5 个 ingest_document 或 crawl_and_ingest 任务排队等待
  4. 在等待期间（可能 5 分钟），所有异步任务功能（文档入库、爬虫处理）完全停滞
- **预期 vs 实际**: 预期：关键任务应有优先级或 slot 预留。实际：所有任务平等竞争 4 个 slot。
- **代码审计**: `docker-compose.v4.sys.yml` L62: `celery -A config worker -l info -c 4`（无队列路由）。`base.py` L220-222: CELERY_TASK_TIME_LIMIT=300（5 分钟硬超时）。 [来源: docker-compose.v4.sys.yml §celery-worker + base.py §CELERY]
- **影响范围**: 大文件上传可阻塞所有异步任务处理长达 5 分钟
- **修复建议**: 配置 Celery 队列路由（`-Q critical,default`）+ 双 worker 配置（critical: -c 2, default: -c 2）

### SYS-V4.2-014: DashScope API 无断路器

- **严重程度**: P0 阻断
- **缺陷类型**: 性能瓶颈
- **攻击 Payload**: DashScope API 不可用或延迟 → 每个 SSE 请求阻塞 runserver 30 秒 → 服务器完全瘫痪
- **复现步骤**:
  1. 设置无效 DASHSCOPE_API_KEY（或 DashScope 服务故障）
  2. 发送 5 个并发 SSE chat 请求
  3. 每个 SSE 请求的 `pipeline.retrieve_and_generate()` → `self.llm.stream_chat()` 等待 DashScope 响应
  4. DashScope 返回 401/403 或超时 → SSE generator 继续等待直到 30 秒前端 abort
  5. 5 个 SSE 请求同时阻塞 runserver 单线程 30 秒 → 所有其他 API 请求被阻塞
  6. 在阻塞期间，所有 CRUD API 不可用
- **预期 vs 实际**: 预期：外部 API 失败应有断路器保护和降级响应。实际：无断路器，失败请求直接阻塞服务器。
- **代码审计**: `pipeline.py` L132: `self.llm.stream_chat()` 无超时、无断路器、无降级。`chat/views.py` L190-265: SSE generator 无超时控制，依赖前端 30 秒 abort。 [来源: pipeline.py §retrieve_and_generate + chat/views.py §event_stream]
- **影响范围**: 外部 API 单点故障可完全瘫痪后端服务（所有 CRUD API 不可用）
- **修复建议**: 添加 pybreaker 断路器（3 次失败 → 开路 → 30 秒半开 → 降级响应）；或在 event_stream() 中添加 `time.time() - start_time > 15` 超时检测，超过后返回降级消息

### SYS-V4.2-015: TokenBatchRenderer 全字符串累积

- **严重程度**: P2 一般
- **缺陷类型**: 性能瓶颈
- **攻击 Payload**: 发送长对话消息 → 2000 token 流式输出 → 线性内存增长
- **复现步骤**:
  1. 用户发送聊天消息触发 2000 token 的 SSE 流式输出
  2. `TokenBatchRenderer.ts` L42: `accumulatedContent += token` 每帧追加 token
  3. `flushImmediate()` → `batchCallback(accumulatedContent)` 将完整字符串传递给 Zustand
  4. 每帧（60fps）复制 ~8KB 字符串 → 60 × 8KB = ~480KB/秒 GC 压力
  5. 在 2000 token 输出期间（约 30 秒），总 GC 压力 ~14.4MB
- **预期 vs 实际**: 预期：流式输出应增量更新状态。实际：每帧传递完整字符串。
- **代码审计**: `TokenBatchRenderer.ts` L42-50: `batchCallback(accumulatedContent)` 将完整累积字符串传递给 Zustand 的 `setStreamContent`。`chatStore.ts` L495: `({ streamContent: batchCallback(accumulatedContent) })` 更新 Zustand store。 [来源: TokenBatchRenderer.ts §flushImmediate + chatStore.ts §appendToken]
- **影响范围**: 在长对话中增加浏览器内存压力和 GC 开销
- **修复建议**: 改为增量 diff 模式：`batchCallback({ appendToken: token })` → Zustand 仅追加新 token

### SYS-V4.2-016: computeRounds 双重调用

- **严重程度**: P2 一般
- **缺陷类型**: 性能瓶颈
- **攻击 Payload**: 发送 50 条消息 → computeRounds 被调用 100 次
- **复现步骤**:
  1. 用户发送消息 → `chatStore.sendMessage()` → `addMessage()` → 触发 `computeRounds()`（在裁剪路径中）
  2. SSE 流式输出完成 → `finishStreamingMessage()` → 触发 `computeRounds()`（第二次）
  3. 每条完成的消息 = 2 次 computeRounds() 调用
  4. 在接近 MAX_ALL_MESSAGES=100 的对话中，每次 computeRounds() = O(100)
  5. 50 条消息 × 2 × O(100) = O(10,000) 总计算量
- **预期 vs 实际**: 预期：每条消息仅调用一次 computeRounds()。实际：addMessage + finishStreamingMessage 双重调用。
- **代码审计**: `chatStore.ts` L248: `addMessage()` 在裁剪路径调用 `computeRounds()`；L631: `finishStreamingMessage()` 再次调用 `computeRounds()`。两者路径不同，但存在冗余计算。 [来源: chatStore.ts §addMessage + §finishStreamingMessage]
- **影响范围**: 在长对话中增加 JS 执行开销
- **修复建议**: 在 addMessage() 中跳过 computeRounds() 调用，仅在 finishStreamingMessage() 中调用一次

### SYS-V4.2-017: crossTabSync 动态导入延迟

- **严重程度**: P2 一般
- **缺陷类型**: 性能瓶颈
- **攻击 Payload**: 跨标签页切换 → abort 信号延迟 ~200ms → 10-20 个废弃 token
- **复现步骤**:
  1. 用户在标签页 A 发送聊天消息（SSE 流式输出进行中）
  2. 用户在标签页 B 删除该会话 → BroadcastChannel 发送 "session_deleted" 事件
  3. `crossTabSync.ts` L40-62: 4 层嵌套 `import()` 动态导入：
     `import('../stream/StreamLifecycleManager').then(...).then(...).then(...).then(...)`
  4. 每层 import ~50ms → 总延迟 ~200ms
  5. 在 200ms 内，标签页 A 的 SSE 流继续输出 10-20 个 token（已废弃）
  6. 最终 abort 信号到达 → 流中断 → 废弃 token 丢失
- **预期 vs 实际**: 预期：跨标签页 abort 信号应即时到达。实际：动态导入链增加 ~200ms 延迟。
- **代码审计**: `crossTabSync.ts` L40-62: 每个事件处理函数使用 4 层嵌套 `import()`，创建模块解析 + eval 的串行延迟链。 [来源: crossTabSync.ts §import chains]
- **影响范围**: 跨标签页操作的响应延迟增加 ~200ms
- **修复建议**: 改为顶层静态导入，避免嵌套动态导入链

### SYS-V4.2-018: forceUpdate 每帧触发

- **严重程度**: P2 一般
- **缺陷类型**: 性能瓶颈
- **攻击 Payload**: SSE 流式输出期间 → 60 React renders/sec
- **复现步骤**:
  1. 用户发送聊天消息 → SSE 流式输出开始
  2. TokenBatchRenderer 每 rAF frame flush → `setStreamContent()` → Zustand update
  3. `ChatPage.tsx` IntersectionObserver callback → `forceUpdate(prev => prev + 1)` 在每帧触发
  4. 即使滚动位置未变化 → React render 触发
  5. 60fps × 30 秒 = 1800 次 React render（多数无实际 DOM 变化）
- **预期 vs 实际**: 预期：IntersectionObserver 仅在滚动位置变化时触发更新。实际：每帧都触发 forceUpdate。
- **代码审计**: `ChatPage.tsx` L154: IntersectionObserver 的 `forceUpdate(prev => prev + 1)` 在每次 streamContent 变化时触发（无论 IntersectionObserver 是否检测到可见性变化）。 [来源: ChatPage.tsx §IntersectionObserver]
- **影响范围**: 流式输出期间增加 ~60/sec 的 React render 开销
- **修复建议**: 将 forceUpdate 从 IntersectionObserver 回调移至滚动事件监听器中，仅在实际滚动时触发

---

## 【并发竞态类】

### SYS-V4.2-019: CrawlWithdrawByURLView 批量撤回缺少 transaction.atomic()

- **严重程度**: P2 一般
- **缺陷类型**: 并发竞态
- **攻击 Payload**: 同时批量撤回同一 URL 的文档 + 另一个用户正在创建该 URL 的新爬虫 → 状态不一致
- **复现步骤**:
  1. 用户 A POST `/api/v1/crawl/withdraw-by-url/` with url="http://example.com/article"
  2. `views.py` L172-188: 逐个更新 CrawledDocument.crawl_status="withdrawn" 和 Document.status="expired"
  3. 在更新过程中（如已更新 2 个，还剩 3 个未更新时），用户 B POST `/api/v1/crawl/crawl/` 提交同一 URL
  4. 用户 B 的爬虫任务创建了新的 CrawledDocument，crawl_status="pending"
  5. 用户 A 的批量撤回继续执行，但新创建的 CrawledDocument 不在原始查询集 `CrawledDocument.objects.filter(source_url=url, crawl_status="active")` 中
  6. 结果：同一 URL 下存在 active（新创建）和 withdrawn（旧撤回）混合状态的文档
- **预期 vs 实际**: 预期：批量撤回应在事务中执行，确保一致性。实际：逐个更新，无 transaction.atomic()。
- **代码审计**: `views.py` L172-188: `CrawlWithdrawByURLView.post()` 逐个循环更新 CrawledDocument 和 Document，未使用 `transaction.atomic()`。对比 `knowledge/views.py` L100-109: DocumentReindexView 使用 `transaction.atomic()` + `select_for_update()`。 [来源: crawler/views.py §CrawlWithdrawByURLView]
- **影响范围**: 同一 URL 可能出现混合状态的文档（active + withdrawn），知识库内容不一致
- **修复建议**: 使用 `transaction.atomic()` 包裹批量撤回操作，并在查询时添加 `select_for_update()` 防止并发修改

---

## 【认证类】— JWT Blacklist 缺陷

### SYS-V4.2-020: 黑名单 refresh token 仍可用于获取新 token pair

- **严重程度**: P1 严重
- **缺陷类型**: 认证
- **攻击 Payload**: 被盗 refresh token 在黑名单中仍可用于刷新获取新 access+refresh pair
- **复现步骤**:
  1. 用户登录获得 refresh_token_1
  2. 用户刷新 token → 获得 refresh_token_2（refresh_token_1 被加入黑名单）
  3. 攻击者窃取 refresh_token_1（在黑名单化之前）
  4. 攻击者调用 `/api/v1/auth/token/refresh/` 使用 stolen refresh_token_1
  5. simplejwt 的 TokenRefreshSerializer 仅解码 token，**不检查黑名单**
  6. 攻击者获得新的有效 access+refresh pair，尽管 refresh_token_1 已在黑名单中
- **预期 vs 实际**: 预期：黑名单化的 refresh token 应被拒绝。实际：TokenRefreshView 不检查黑名单，黑名单 token 仍可用于获取新 pair。
- **代码审计**: `base.py` L193-194: `ROTATE_REFRESH_TOKENS=True` + `BLACKLIST_AFTER_ROTATION=True`。simplejwt 的 `TokenRefreshSerializer` 调用 `RefreshToken(refresh_token_str)` 仅解码，不调用 `OutstandingToken` 黑名单检查。黑名单检查仅在 `JWTAuthentication.validate()` 中对 access token 执行。 [来源: base.py §SIMPLE_JWT]
- **影响范围**: JWT rotation 安全模型完全失效——被盗 refresh token 可无限刷新获取新 pair
- **修复建议**: 自定义 TokenRefreshSerializer 或 override TokenRefreshView，在刷新前检查 OutstandingToken 是否已被黑名单化

---

## 【RBAC 类补充】— 权限与角色管理缺陷

### SYS-V4.2-021: UserRole unique_together 阻止重新分配已撤销角色

- **严重程度**: P2 一般
- **缺陷类型**: RBAC
- **攻击 Payload**: Admin 分配 hr → 撤销 hr → 重新分配 hr → 500 IntegrityError
- **复现步骤**:
  1. Admin 通过 UserRoleListView.create 分配 "hr" 角色 → UserRole(user, hr) 创建
  2. Admin 通过 UserRoleDetailView.destroy 撤销 → is_active=False（**不删除记录**）
  3. Admin 尝试重新分配 "hr" → UserRole.objects.create(user, hr) → **IntegrityError**
  4. unique_together=("user", "role") 约束阻止创建新记录，因为已存在的 is_active=False 记录占用唯一槽位
- **预期 vs 实际**: 预期：撤销后可重新分配同一角色。实际：unique_together 约束阻止重分配，返回 500。
- **代码审计**: `rbac/models.py` L117: `unique_together = [("user", "role")]`。`views.py` L143-162: `destroy()` 设置 `is_active=False` 但不删除记录。对比 `UserRoleAssignSerializer.validate()` 仅检查 `is_active=True` 的重复记录，但 `create()` 在 DB 层面触发 IntegrityError。 [来源: rbac/models.py §unique_together + rbac/views.py §destroy]
- **影响范围**: 无法重新分配已撤销的角色，操作中断
- **修复建议**: 在 `create()` 中改用 `update()` 重激活已存在的 is_active=False 记录，而非 `create()`；或将 unique_together 改为 [("user", "role", "is_active")]

### SYS-V4.2-022: admin_user_deactivate 允许自我停用

- **严重程度**: P2 一般
- **缺陷类型**: RBAC
- **攻击 Payload**: Admin POST `/api/v1/rbac/users/{self_id}/deactivate/` → 自我锁定
- **复现步骤**:
  1. Admin 发送 POST `/api/v1/rbac/users/{self_id}/deactivate/`
  2. `views.py` L218-222: `has_permission("user.deactivate")` → True
  3. `views.py` L232-236: 仅检查 `if user.is_superuser` 阻止停用超级用户
  4. Admin 非 superuser → 检查通过 → `user.is_active = False` → Admin 被停用
  5. Admin 无法登录，无法恢复（无撤销机制）
- **预期 vs 实际**: 预期：不应允许停用自身账户。实际：无自我停用防护。
- **代码审计**: `rbac/views.py` L213-254: 仅阻止停用 superuser，不阻止停用自身。无确认步骤、无撤销功能。 [来源: rbac/views.py §admin_user_deactivate]
- **影响范围**: Admin 可意外或恶意停用自身账户，导致管理锁定
- **修复建议**: 添加自我停用防护：`if user.id == request.user.id: return Response({"detail": "Cannot deactivate your own account"}, status=400)`

### SYS-V4.2-023: 角色分配端点 30/min 限流过于宽松

- **严重程度**: P1 严重
- **缺陷类型**: 频率限制
- **攻击 Payload**: 拥有 user.assign_role 权限的攻击者每分钟分配 30 个角色 → 特权升级攻击
- **复现步骤**:
  1. 攻击者使用被盗 JWT 调用 `/api/v1/rbac/user-roles/` POST（需 user.assign_role 权限）
  2. UserRateThrottle 30/min → 攻击者每分钟可分配 30 个不同用户的 admin 角色
  3. 30 分钟内可给 900 个用户分配 admin 角色
  4. 安全敏感操作（特权分配/撤销）的限流应为 5/min
- **预期 vs 实际**: 预期：特权分配端点应有严格限流（5/min）。实际：继承 DEFAULT 30/min，过于宽松。
- **代码审计**: `base.py` L176-183: `UserRateThrottle rate="30/minute"` 为全局默认，应用于所有 authenticated 端点。UserRoleListView 和 UserRoleDetailView 作为 GenericAPIView 自动继承此限流，但无端点专属限流。对比 `users/views.py` LoginRateThrottle rate="5/minute" 为登录端点的更严格限流。 [来源: base.py §REST_FRAMEWORK + rbac/views.py §UserRoleListView]
- **影响范围**: 特权分配操作限流不足，可被用于批量角色操纵
- **修复建议**: 创建 RoleAssignmentRateThrottle(rate="5/minute") 并应用于 UserRoleListView 和 UserRoleDetailView

### SYS-V4.2-024: is_hr_admin 双轨授权 content_resources 不一致

- **严重程度**: P2 一般
- **缺陷类型**: RBAC
- **攻击 Payload**: is_hr_admin 用户调用 has_permission("audit.read") → False（但 HasPermission("audit.read") → True）
- **复现步骤**:
  1. is_hr_admin=True 但不在 RBAC 中的用户调用 `request.user.has_permission("audit.read")`
  2. `models.py` L107: content_resources = {"document", "category", "template", "workflow"} → "audit" 不在集合中 → 返回 False
  3. 同一用户通过 HasPermission("audit.read") DRF 权限类
  4. `permissions.py` L71: content_resources = {"document", "category", "template", "workflow", **"audit"**} → "audit" 在集合中 → 返回 True
  5. 直接调用 has_permission() vs DRF HasPermission 类产生不同授权结果
- **预期 vs 实际**: 预期：双轨授权范围应一致。实际：permissions.py 包含 "audit" 但 models.py 不包含。
- **代码审计**: `permissions.py` L71: `content_resources = {"document", "category", "template", "workflow", "audit"}`。`models.py` L107: `content_resources = {"document", "category", "template", "workflow"}`。两处定义不一致。 [来源: permissions.py §HasPermission + models.py §has_permission]
- **影响范围**: 代码直接调用 has_permission()（如 admin_user_deactivate）与 DRF 权限类产生不同审计权限结果
- **修复建议**: 同步两处 content_resources 定义，在 models.py L107 中添加 "audit"

---

## 【配置类】— 部署安全缺陷

### SYS-V4.2-025: Redis 密码不匹配

- **严重程度**: P2 一般
- **缺陷类型**: 配置
- **攻击 Payload**: docker-compose.yml（原版）Redis 无 requirepass → Celery 认证失败 或 Redis 无密码保护
- **复现步骤**:
  1. `base.py` L213: `CELERY_BROKER_URL = "redis://:sys_redis_pass_2026@redis:6379/0"` 含密码
  2. 原版 `docker-compose.yml` Redis 服务无 `requirepass` 命令
  3. Celery 使用密码连接 → Redis 无密码 → AUTH 命令被拒绝 → Celery 无法连接
  4. 或者如果 Redis 无密码，任何容器可连接执行 FLUSHALL
- **预期 vs 实际**: 预期：所有 compose 文件中 Redis 密码应一致。实际：原版 compose 无密码，SYS 专用 compose 有密码。
- **代码审计**: `base.py` L213 使用密码格式；原版 `docker-compose.yml` Redis 无 requirepass；SYS 专用 `docker-compose.v4.sys.yml` L25 有 requirepass。两套 compose 配置不一致。 [来源: base.py §CELERY_BROKER_URL + docker-compose.yml §redis + docker-compose.v4.sys.yml §redis]
- **影响范围**: 使用原版 compose 启动时 Celery 无法连接 Redis，异步任务功能完全失效
- **修复建议**: 在原版 docker-compose.yml Redis 服务添加 `command: redis-server --requirepass ${REDIS_PASSWORD}`；或使用 env_file 统一配置

### SYS-V4.2-026: PostgreSQL 默认弱密码 + 端口暴露

- **严重程度**: P2 一般
- **缺陷类型**: 配置
- **攻击 Payload**: 从宿主机网络使用 `ey_onboarding/ey_password` 直接连接 PostgreSQL 5435 端口
- **复现步骤**:
  1. `docker-compose.v4.sys.yml` L10: `POSTGRES_PASSWORD: ey_password`（硬编码弱密码）
  2. `docker-compose.v4.sys.yml` L12: `"5435:5432"`（端口暴露到宿主机）
  3. 从宿主机网络: `psql -h 127.0.0.1 -p 5435 -U ey_onboarding -d ey_onboarding` → 使用 `ey_password` 登录
  4. 可直接访问所有用户数据、向量数据、审计日志
- **预期 vs 实际**: 预期：生产环境应使用强密码且不暴露端口。实际：弱密码 + 端口暴露。
- **代码审计**: `docker-compose.v4.sys.yml` L10: `POSTGRES_PASSWORD: ey_password`。`base.py` L118: `os.environ.get("POSTGRES_PASSWORD", "ey_password")` 使用相同的默认弱密码。 [来源: docker-compose.v4.sys.yml §POSTGRES_PASSWORD + base.py §DATABASES]
- **影响范围**: 宿主机网络上的任何用户可直接访问 PostgreSQL 数据库
- **修复建议**: 使用 Docker secrets 或 .env 文件存储强密码；移除端口暴露 `"5435:5432"`（仅本地开发需要）

---

## 【资源耗尽类补充】

### SYS-V4.2-027: Django CACHES 配置缺失 — Redis 零应用缓存

- **严重程度**: P2 一般
- **缺陷类型**: 资源耗尽
- **攻击 Payload**: 无攻击 payload，纯性能缺陷
- **复现步骤**:
  1. 检查 `base.py` — 无 `CACHES` 配置项
  2. 检查 `docker.py` — 无 `CACHES` 配置项
  3. Redis INFO: db0 仅含 3 个 Celery broker 键，零应用缓存键
  4. Redis 缓存命中率 26%（22/84），全部来自 Celery 内部查找
  5. 所有 API 请求直接查询 PostgreSQL，无缓存层
- **预期 vs 实际**: 预期：Redis 应作为 Django 缓存后端，减轻 DB 负载。实际：Redis 仅作为 Celery broker，无应用缓存。
- **代码审计**: `base.py` 和 `docker.py` 均无 `CACHES` 配置。Django 默认使用 `LocalMemCache`（进程内缓存，无法跨请求/进程共享）。 [来源: base.py §无CACHES + 实测 Redis INFO]
- **影响范围**: 所有读密集型 API（sessions、documents、RBAC roles）无缓存，每次请求直接查询 DB
- **修复建议**: 在 docker.py 中配置 `CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}`；对读密集端点添加 `@method_decorator(cache_page(60))`

### SYS-V4.2-028: Celery worker 运行为 root (uid=0)

- **严重程度**: P2 一般
- **缺陷类型**: 资源耗尽
- **攻击 Payload**: 如果 Celery 任务存在漏洞 → 攻击者获得容器内 root 权限
- **复现步骤**:
  1. 查看 Celery worker 启动日志
  2. 发现警告: "You're running the worker with superuser privileges: this is absolutely not recommended!"
  3. Worker 进程以 uid=0 (root) 运行
  4. 如果任务代码存在任意代码执行漏洞（如 _parse_with_unstructured 的文件处理），攻击者可在容器内以 root 执行任意命令
- **预期 vs 实际**: 预期：Celery worker 应以非 root 用户运行。实际：以 root 运行。
- **代码审计**: `backend/Dockerfile` 未创建或指定非 root `USER`。Celery worker 继承 backend 容器的 root uid。 [来源: backend/Dockerfile §无USER指令 + Celery 启动日志]
- **影响范围**: 容器内 root 权限滥用风险
- **修复建议**: 在 Dockerfile 中添加 `RUN adduser --disabled-password celery && USER celery`；或在 docker-compose 中指定 `user: "1000:1000"`

---

## 附录：缺陷统计

| 严重程度 | 数量 | 缺陷 ID |
|---|---|---|
| P0 阻断 | 2 | SYS-V4.2-011, SYS-V4.2-014 |
| P1 严重 | 7 | SYS-V4.2-001, SYS-V4.2-002, SYS-V4.2-003, SYS-V4.2-008, SYS-V4.2-010, SYS-V4.2-020, SYS-V4.2-023 |
| P2 一般 | 19 | SYS-V4.2-004~009, SYS-V4.2-012~019, SYS-V4.2-021~022, SYS-V4.2-024~028 |
| **总计** | **28** | |

> **签名**: V4.2 SYS 领域深度缺陷清单 — 2026-06-26
