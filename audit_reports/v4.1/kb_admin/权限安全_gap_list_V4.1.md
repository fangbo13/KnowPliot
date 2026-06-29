# V4.1 权限安全 Gap List

> **版本**: V4.1 — 权限漏洞与安全风险清单（含爬虫预规格）
> **产出路径**: `audit_reports/v4.1/kb_admin/权限安全_gap_list_V4.1.md`
> **日期**: 2026-06-26
> **审计范围**: 越权 + 注入 + 上传 + JWT + 爬虫 SSRF + 爬虫合规 + 爬虫内容安全
> **引用规则**: `[来源: V4.0/kb_admin/权限安全_gap_list.md §编号]`

---

## ⚠️ 重要声明

V4.1 描述的"网络爬取知识入库"功能**在代码中完全不存在**。无爬虫端点、无 trafilatura/SimHash 库、无前端爬虫 UI。爬虫类漏洞（KB-V4.1-011~017）标注为 **⚠️ 预实现安全规格**，Payload 格式正确但标注"待端点实现后执行"。这些漏洞为 **Prompt 2B 开发对话**提供约束。

---

## 一、权限越权类

### KB-V4.1-001: Employee 垂直越权拦截（✓ 已修复验证）

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-001 |
| 风险等级 | 🟢 **已修复** |
| 漏洞类型 | 垂直越权 |
| 攻击 Payload | `curl -s -H "Authorization: Bearer $EMP_TOKEN" http://localhost:8020/api/v1/rbac/roles/` |
| 复现步骤 | 1. Employee 登录获取 Token; 2. 尝试访问 8 个 Admin/RBAC 端点; 3. 全部返回 403 |
| 预期 vs 实际 | 预期 403 → 实际 403 ✓ |
| 影响范围 | V4.0 修复有效，Employee 无法越权访问 Admin API |
| 修复建议 | 保持当前 HasPermission/HasRole 权限类不变 |

> [来源: V4.0/kb_admin/权限安全_gap_list.md §P0-1] — V4.0 已修复 CategoryListView POST 闸门

### KB-V4.1-002: is_superuser 全局绕过（未修复）

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-002 |
| 食险等级 | 🟠 **中危** |
| 漏洞类型 | 权限越权 |
| 攻击 Payload | `# super@example.com 登录（is_superuser=True, 无 admin RBAC 角色）` |
| 复现步骤 | 1. super@example.com 登录（is_superuser=True, roles=[]）; 2. 访问任何 Admin API; 3. HasPermission/HasRole 全部放行（is_superuser=True 直接 return True） |
| 预期 vs 实际 | 预期：superuser 应仅用于紧急 Django Admin → 实际：superuser 绕过所有 API RBAC 权限 |
| 影响范围 | 所有 HasPermission/HasRole 保护的端点 |
| 修复建议 | Phase 3: 添加 superuser 操作审计记录; Phase 4: 限制 superuser 仅 Django Admin 紧急场景 |

> [来源: backend/apps/core/permissions.py §L55] — `if request.user.is_superuser: return True`

### KB-V4.1-003: 横向越权 — HR 可删除他人文档（未修复）

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-003 |
| 食险等级 | ⚠️ **低危** |
| 漏洞类型 | 横向越权 |
| 攻击 Payload | `curl -X DELETE -H "Authorization: Bearer $HR_A_TOKEN" http://localhost:8020/api/v1/documents/<hr_b_doc_id>/` |
| 复现步骤 | 1. HR A 登录; 2. 获取 HR B 上传的文档 ID; 3. DELETE 请求; 4. 204 No Content（成功删除） |
| 预期 vs 实际 | 预期：仅上传者可删除 → 实际：任何 HR/Admin 可删除 |
| 影响范围 | DocumentDetailView destroy 方法 |
| 修复建议 | Phase 3: 添加对象级权限 `uploaded_by=self.request.user OR has_role('admin')` |

> [来源: backend/apps/knowledge/views.py §L57-L76] — 无 `uploaded_by` 检查

---

## 二、注入攻击类

### KB-V4.1-004: Retriever SQL 列名注入（潜在风险）

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-004 |
| 食险等级 | 🟠 **中危** |
| 漏洞类型 | SQL 注入 |
| 攻击 Payload | `# 当前无用户传入 filters 的端点，但代码模式危险` |
| 复现步骤 | 1. 查看 retriever.py L140: `f"{key} = %s"`; 2. 若未来端点允许 `filters={"document_id; DROP TABLE--": "xxx"}`; 3. SQL 列名注入 |
| 预期 vs 实际 | 当前安全（无用户传入路径）→ 代码模式危险（若未来暴露 filters 参数） |
| 影响范围 | PgVectorRetriever._search_pgvector() |
| 修复建议 | P1: 白名单验证 filter keys（仅允许 document_id, category_id） |

> [来源: backend/apps/rag/retriever.py §L138-L142] — `filter_parts.append(f"{key} = %s")`

### KB-V4.1-005: Prompt Injection via Knowledge Content（潜在风险）

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-005 |
| 食险等级 | ⚠️ **低危** |
| 漏洞类型 | Prompt Injection |
| 攻击 Payload | `# 上传一份包含 "IGNORE ALL PREVIOUS INSTRUCTIONS..." 的 PDF` |
| 复现步骤 | 1. HR 上传含恶意指令的 PDF; 2. 用户聊天检索到该文档; 3. LLM 可能执行文档中的指令 |
| 预期 vs 实际 | 预期：guardrails 拦截 → 实际：guardrails 仅检查 LLM 输出，不检查 RAG 检索内容 |
| 影响范围 | RAG pipeline: retriever → guardrails → LLM |
| 修复建议 | P2: 在 RAG 上下文注入前增加内容清洗层 |

---

## 三、文件上传类

### KB-V4.1-006: 无 Magic Number 文件内容校验

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-006 |
| 食险等级 | 🔴 **高危** |
| 漏洞类型 | 文件上传 |
| 攻击 Payload | `echo "MZ\\x00\\x00PE header" > fake.pdf; curl -X POST -F "file=@fake.pdf" -F "file_type=pdf" -F "title=Malicious" http://localhost:8020/api/v1/documents/ -H "Authorization: Bearer $HR_TOKEN"` |
| 复现步骤 | 1. 创建含 PE header 的文件命名为 .pdf; 2. HR 上传 file_type=pdf; 3. 接受入库（无 magic number 检查） |
| 预期 vs 实际 | 预期：拒绝非 PDF 内容 → 实际：仅校验 file_type 字段 CHOICES，不校验文件内容 |
| 影响范围 | DocumentSerializer + 文件解析器 |
| 修复建议 | P0: 添加 python-magic 或 filetype 库校验文件内容与声明类型匹配 |

### KB-V4.1-007: DEBUG 模式 Media 文件无鉴权访问

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-007 |
| 食险等级 | 🔴 **高危** |
| 漏洞类型 | 文件上传 + 配置 |
| 攻击 Payload | `curl http://localhost:8020/media/documents/2026/06/test.pdf` |
| 复现步骤 | 1. Docker settings DEBUG=True; 2. 上传文件; 3. 猜测 URL 直接下载; 4. 无需 Token |
| 预期 vs 实际 | 预期：需 Token 访问 → 实际：DEBUG 模式下任何人可下载 |
| 影响范围 | 所有上传的 PDF/DOCX 文件 |
| 修复建议 | P0: 生产环境关闭 DEBUG; 使用签名 URL 或 Token-based media middleware |

> [来源: backend/config/urls.py §L17-L18] — `if settings.DEBUG: urlpatterns += static(...)`

### KB-V4.1-008: 空文件/超大文件 DoS

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-008 |
| 食险等级 | ⚠️ **低危** |
| 漏洞类型 | 文件上传 |
| 攻击 Payload | `# 上传 0-byte 文件或 100MB+ 文件` |
| 复现步骤 | 1. 创建 0-byte 文件; 2. HR 上传 file_type=txt; 3. Celery 解析空文件 → 可能抛异常; 4. 创建超大文件 → 可能耗尽解析资源 |
| 预期 vs 实际 | 预期：有文件大小限制 → 实际：需检查 Django DATA_UPLOAD_MAX_MEMORY_SIZE 配置 |
| 影响范围 | Celery worker 解析资源 |
| 修复建议 | P1: 添加最小文件大小校验（≥1KB）+ 最大文件大小校验（≤50MB） |

---

## 四、JWT 安全类

### KB-V4.1-009: JWT Claims 泄露 is_hr_admin（P0-2 残留）

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-009 |
| 食险等级 | 🔴 **高危** |
| 漏洞类型 | JWT 安全 |
| 攻击 Payload | `# 解码任意 JWT access token` `echo $TOKEN | cut -d. -f2 | base64 -d | jq .is_hr_admin` |
| 复现步骤 | 1. 获取任何用户的 JWT access token; 2. 解码 payload; 3. 读取 `is_hr_admin: true/false` |
| 预期 vs 实际 | 预期：JWT 不含角色信息 → 实际：JWT 含 is_hr_admin 布尔值 |
| 影响范围 | 所有 JWT token（3 个用户级别的 payload 中均含 is_hr_admin） |
| 修复建议 | P0: 移除 `token["is_hr_admin"]` from CustomTokenObtainPairSerializer.get_token() |

> [来源: backend/apps/users/views.py §L23] — `token["is_hr_admin"] = user.is_hr_admin`

### KB-V4.1-010: Token Blacklist 失效 + 前端无自动刷新

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-010 |
| 食险等级 | 🟠 **中危** |
| 漏洞类型 | JWT 安全 |
| 攻击 Payload | `# 1. 登录获取 token; 2. 调用 /auth/logout/; 3. 用同一 token 访问 /auth/me/ → 200（不应生效）` |
| 复现步骤 | 1. Admin 登录获取 access token; 2. POST /auth/logout/ (200 OK); 3. 用同一 token GET /auth/me/ → 200（黑名单未生效） |
| 预期 vs 实际 | 预期 401 → 实际 200 |
| 影响范围 | JWT token lifecycle security |
| 修复建议 | P0: 检查 SimpleJWT REST_AUTH_TOKEN_BLACKLISTING 配置是否生效; 前端添加 token 自动刷新 |

> [来源: 回测验证] — Logout 后 token 仍返回 200 on /auth/me/

---

## 五、爬虫 SSRF 类（⚠️ 预实现安全规格）

### KB-V4.1-011: 爬虫端点无 SSRF 防护

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-011 |
| 食险等级 | 🔴 **高危（规划级）** |
| 漏洞类型 | 爬虫 SSRF |
| ⚠️ 标注 | 功能未实现，以下为预实现安全要求 |
| 攻击 Payload | `curl -X POST http://localhost:8020/api/v1/documents/crawl/ -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"url":"http://127.0.0.1:8020/admin/"}'` |
| 复现步骤 | 1. 爬虫端点实现后; 2. Admin 提交内网 URL; 3. 爬虫访问内网服务（无 IP 黑名单） |
| 预期 vs 实际 | 预期 400（SSRF 拦截）→ 待端点实现后验证 |
| 影响范围 | 内网服务暴露、云元数据泄露（169.254.169.254） |
| 修复建议 | P0: URL 协议白名单（仅 http/https）+ 内网 IP 黑名单 + DNS Rebinding 防护 |

### KB-V4.1-012: 爬虫无 URL 重定向限制

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-012 |
| 食险等级 | 🟠 **中危（规划级）** |
| 漏洞类型 | 爬虫 SSRF |
| ⚠️ 标注 | 功能未实现 |
| 攻击 Payload | `curl -X POST http://localhost:8020/api/v1/documents/crawl/ -d '{"url":"http://public-site.com/redirect-to-127.0.0.1"}'` |
| 复现步骤 | 1. 提交合法外网 URL; 2. 外网 302 重定向到 127.0.0.1; 3. 无重定向限制 → SSRF |
| 预期 vs 实际 | 预期：最多 3 次重定向 + 内网 IP 重检 → 待验证 |
| 修复建议 | P0: httpx Client 设置 max_redirects=3; 每次重定向后重新检查目标 IP |

### KB-V4.1-013: 爬虫无协议限制（file:///etc/passwd / gopher://）

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-013 |
| 食险等级 | 🔴 **高危（规划级）** |
| 漏洞类型 | 爬虫 SSRF |
| ⚠️ 标注 | 功能未实现 |
| 攻击 Payload | `curl -X POST http://localhost:8020/api/v1/documents/crawl/ -d '{"url":"file:///etc/passwd"}'` |
| 复现步骤 | 1. Admin 提交 file:// URL; 2. 爬虫读取本地文件系统 → 信息泄露 |
| 预期 vs 实际 | 预期 400（非法协议）→ 待验证 |
| 修复建议 | P0: URL 协议白名单仅 http/https; 拒绝 file:///、gopher://、ftp:// 等 |

---

## 六、爬虫合规类（⚠️ 预实现安全规格）

### KB-V4.1-014: 爬虫无 robots.txt 检查

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-014 |
| 食险等级 | 🟠 **中危（规划级）** |
| 漏洞类型 | 爬虫合规 |
| ⚠️ 标注 | 功能未实现 |
| 攻击 Payload | `# 爬取 http://example.com/admin/ (robots.txt 中 Disallow: /admin/)` |
| 复现步骤 | 1. 目标站点 robots.txt 禁止 /admin/ 路径; 2. Admin 提交该 URL; 3. 爬虫不检查 robots.txt 直接爬取 |
| 预期 vs 实际 | 预期：爬取前解析 robots.txt 并遵守 → 待验证 |
| 修复建议 | P1: 爬取前拉取 robots.txt; 缓存解析结果; 遵守 Disallow 和 Crawl-delay |

### KB-V4.1-015: 爬虫频率无限制

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-015 |
| 食险等级 | 🟠 **中危（规划级）** |
| 漏洞类型 | 爬虫合规 |
| ⚠️ 标注 | 功能未实现 |
| 攻击 Payload | `# 短时间内提交 100 个爬取任务` |
| 复现步骤 | 1. Admin 连续提交大量爬取请求; 2. 无频率限制 → 对目标站点造成压力; 3. 系统资源耗尽 |
| 预期 vs 实际 | 预期：10 任务/用户/小时限制 → 待验证 |
| 修复建议 | P1: 令牌桶限流（10 任务/用户/小时）; 设置 User-Agent; 重试退避 |

---

## 七、爬虫内容安全类（⚠️ 预实现安全规格）

### KB-V4.1-016: 爬取内容 XSS 无清洗

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-016 |
| 食险等级 | 🔴 **高危（规划级）** |
| 漏洞类型 | 爬虫内容安全 |
| ⚠️ 标注 | 功能未实现 |
| 攻击 Payload | `# 爬取 http://mock-server.local/xss-page.html (含 <script>alert(1)</script>)` |
| 复现步骤 | 1. 爬取含恶意脚本的页面; 2. HTML 正文未经清洗直接入库; 3. 聊天引用时触发存储型 XSS |
| 预期 vs 实际 | 预期：bleach 清洗后入库 → 待验证 |
| 影响范围 | 所有引用爬取内容的聊天用户 |
| 修复建议 | P0: trafilatura 提取后用 bleach/html-sanitizer 清洗; 过滤 <script>, <iframe>, onload/onerror 等 |

### KB-V4.1-017: 爬取内容版权无记录

| 字段 | 值 |
|---|---|
| 漏洞 ID | KB-V4.1-017 |
| 食险等级 | ⚠️ **低危（规划级）** |
| 漏洞类型 | 爬虫内容安全 |
| ⚠️ 标注 | 功能未实现 |
| 攻击 Payload | `# 爬取受版权保护的网站内容入库，无来源记录` |
| 复现步骤 | 1. Admin 爬取 copyrighted 内容; 2. 无 source_url/copyright 元数据; 3. 无法溯源或下架 |
| 预期 vs 实际 | 预期：记录 source_url + copyright 标记 → 待验证 |
| 修复建议 | P1: CrawledDocument 模型包含 source_url, crawled_at, copyright_disclaimer 字段; 允许 Admin 标记"仅内部参考" |

---

## 八、Gap 汇总矩阵

| 优先级 | 漏洞 ID | 类型 | 严重度 | 影响范围 | 状态 |
|---|---|---|---|---|---|
| **P0** | KB-V4.1-006 | 文件上传：无 magic number 校验 | 🔴 高 | 伪装恶意文件入库 | 未修复 |
| **P0** | KB-V4.1-007 | 文件上传：DEBUG Media 无鉴权 | 🔴 高 | PDF/DOCX 公开访问 | 未修复 |
| **P0** | KB-V4.1-009 | JWT claims 泄露 is_hr_admin | 🔴 高 | 管理员身份泄露 | 未修复 |
| **P0** | KB-V4.1-010 | JWT blacklist 失效 | 🟠 中 | Token lifecycle | 未修复 |
| **P0** | KB-V4.1-011 | 爬虫 SSRF 无防护 | 🔴 高(规划) | 内网暴露 | ⚠️ 未实现 |
| **P0** | KB-V4.1-016 | 爬取内容 XSS 无清洗 | 🔴 高(规划) | 存储型 XSS | ⚠️ 未实现 |
| **P1** | KB-V4.1-004 | retriever SQL 列名注入 | 🟠 中 | 潜在 SQL 注入 | 潜在风险 |
| **P1** | KB-V4.1-002 | is_superuser 全局绕过 | 🟠 中 | 权限审计 | 设计意图 |
| **P1** | KB-V4.1-012 | 爬虫无重定向限制 | 🟠 中(规划) | SSRF via redirect | ⚠️ 未实现 |
| **P1** | KB-V4.1-013 | 爬虫无协议限制 | 🔴 高(规划) | file:///etc/passwd | ⚠️ 未实现 |
| **P1** | KB-V4.1-014 | 爬虫无 robots.txt | 🟠 中(规划) | 合规风险 | ⚠️ 未实现 |
| **P1** | KB-V4.1-015 | 爬虫频率无限制 | 🟠 中(规划) | 目标站点压力 | ⚠️ 未实现 |
| **P2** | KB-V4.1-003 | 横向越权文档删除 | ⚠️ 低 | HR 删他人文档 | 未修复 |
| **P2** | KB-V4.1-005 | Prompt Injection | ⚠️ 低 | LLM 操控 | 潜在风险 |
| **P2** | KB-V4.1-008 | 空文件/超大文件 | ⚠️ 低 | DoS | 未修复 |
| **P2** | KB-V4.1-017 | 爬取版权无记录 | ⚠️ 低(规划) | 法律合规 | ⚠️ 未实现 |

**统计**：17 个漏洞 — 高危 5（含 3 规划级）+ 中危 5（含 4 规划级）+ 低危 4（含 1 规划级）+ 已修复 1

---

## 九、与 V4.0 Gap List 对照

| V4.0 Gap ID | V4.0 状态 | V4.1 状态 | 变化 |
|---|---|---|---|
| P0-1: CategoryListView POST | FIXED | ✓ 验证通过 (8/8 PASS) | 无回归 |
| P0-2: is_hr_admin 公开暴露 | PARTIALLY FIXED | 🔴 仍在 JWT claims + response body | 残留 2 项 |
| P0-3: 无角色分配 API | FIXED | ✓ /api/v1/rbac/user-roles/ 正常 | 无回归 |
| P0-4: AuditLog 缺系统操作 | FIXED | ✓ 20 ACTION_CHOICES + role_used | 无回归 |
| P0-5: 前端 is_hr_admin 硬编码 | FIXED | ✓ roles[] 已替换 | 但 AuthProvider 仍有旧格式迁移逻辑 |

---

> **生成日期**: 2026-06-26
> **数据来源**: Docker API 测试 + 代码审查 + V4.0 gap 对照
> **文件位置**: `audit_reports/v4.1/kb_admin/权限安全_gap_list_V4.1.md`
