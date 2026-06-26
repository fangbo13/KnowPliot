# V4.2 KB/Admin 批量扩充开发变更日志

> **版本**: V4.2 KB/Admin Domain  
> **日期**: 2026-06-26  
> **开发工程师**: 全栈开发工程师（RBAC + 数据工程专家）  
> **关联审计**: [V4.2 批量扩充安全 Gap List](批量扩充安全_gap_list_V4.2.md) · [V4.1 修复验证报告](../../v4.1/kb_admin/rbac_修复验证_V4.1.md)

---

## 一、变更总览

| 指标 | 数值 |
|------|------|
| 修改文件数 | 11 |
| 新增文件数 | 5 |
| 新增批量模块数 | 3（batch.py + batch_views.py + batch_serializers.py） |
| 修复漏洞数 | 12（2 CRITICAL + 6 HIGH + 4 MEDIUM） |
| 新增模型数 | 1（BatchImportResultRecord） |
| 新增数据库迁移数 | 2 |
| 新增 API 端点数 | 2（batch/upload + batch/result） |
| V4.1 回归保护 | 全部保留（throttle + content_hash + sanitize_title 等增量修复不影响 V4.1） |

---

## 二、逐项变更明细

### FEAT-KB-V4.2-BATCH-001: Zip Bomb 防御（🔴 CRITICAL）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-001 |
| **修复漏洞** | KB-V4.2-BATCH-001 |
| **修改文件** | `backend/apps/knowledge/batch.py`（新增 `validate_zip_content()`） |
| **修改前** | 代码库中**完全无 ZIP 处理代码**，`ALLOWED_MIME_TYPES` 不含 ZIP 类型 |
| **修改后核心逻辑** | 新增 `validate_zip_content()` 函数，实现四层 Zip Bomb 防御：① 压缩率检测 `compress_size/file_size < 100:1` → 拒绝 ② 解压后总大小 ≤ 500MB ③ ZIP 内文件数 ≤ 200 ④ 嵌套 ZIP 深度 ≤ 1（拒绝嵌套 ZIP） |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-001] |
| **风险评估** | 低风险 — 纯新增模块，不修改既有代码 |

### FEAT-KB-V4.2-BATCH-002: ZIP 内文件名路径穿越防御（🟠 HIGH）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-002 |
| **修复漏洞** | KB-V4.2-BATCH-002 |
| **修改文件** | `backend/apps/knowledge/batch.py`（新增 `sanitize_filename()` + validate_zip_content 内路径穿越检查） |
| **修改前** | 无 ZIP 解压代码，无文件名清洗逻辑。Django `FileField` 使用 `upload_to="documents/%Y/%m/"` + 原始文件名 |
| **修改后核心逻辑** | ① ZIP 解压时检查每个 entry 的 `filename`：不含 `/../` 或 `\..\` ② 使用 `os.path.basename()` 去除路径前缀 ③ 符号链接检测（`external_attr` UNIX symlink bit → 拒绝）④ `sanitize_filename()` 移除 SQL 注入/XSS/路径穿越 pattern |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-002] |
| **风险评估** | 低风险 — 纯新增清洗逻辑 |

### FEAT-KB-V4.2-BATCH-003: ZIP 内文件类型校验（🟠 HIGH）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-003 |
| **修复漏洞** | KB-V4.2-BATCH-003 |
| **修改文件** | `backend/apps/knowledge/batch.py`（新增 `validate_inner_file_type()`） |
| **修改前** | `validate_file_content_type()` 仅校验顶层上传文件。ZIP 内文件不逐个通过 Magic Number 校验 |
| **修改后核心逻辑** | ① `validate_inner_file_type()` 对 ZIP 内每个文件读取前 261 bytes 进行 magic number 检测 ② 使用 `ALLOWED_MIME_TYPES` 白名单比对 ③ 不合规文件跳过 + 记录 `rejected_files` ④ 不合规文件 > 50% → 整个 ZIP 拒绝 |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-003] |
| **风险评估** | 低风险 — 纯新增校验逻辑 |

### FEAT-KB-V4.2-BATCH-004: 文档上传专属限流（🔴 CRITICAL）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-004 |
| **修复漏洞** | KB-V4.2-BATCH-004 |
| **修改文件** | `backend/apps/knowledge/batch_views.py`（新增 `DocumentUploadRateThrottle` + `BatchUploadRateThrottle`）、`backend/apps/knowledge/views.py`（添加 `throttle_classes`）、`backend/config/settings/base.py`（添加 throttle rates） |
| **修改前** | `DocumentListCreateView` 无 throttle_classes。HR/Admin 可无限调用上传接口 |
| **修改后核心逻辑** | ① `DocumentUploadRateThrottle`: 10/分钟/user（单文档上传）② `BatchUploadRateThrottle`: 3/分钟/user（批量 ZIP 上传）③ `DocumentListCreateView` 添加 `throttle_classes = [DocumentUploadRateThrottle]`④ `BatchDocumentUploadView` 添加 `throttle_classes = [DocumentUploadRateThrottle, BatchUploadRateThrottle]`⑤ settings `DEFAULT_THROTTLE_RATES` 添加 `"document_upload": "10/minute"` + `"batch_upload": "3/minute"` |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-004] |
| **风险评估** | 中风险 — 修改既有视图添加 throttle，可能影响高频上传场景（但 10/分钟远超正常使用频率） |

### FEAT-KB-V4.2-BATCH-005: Celery Task Timeout 提升 + 批量限制（🟠 HIGH）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-005 |
| **修复漏洞** | KB-V4.2-BATCH-005 |
| **修改文件** | `backend/config/settings/base.py`（CELERY_TASK_TIME_LIMIT 提升）、`backend/apps/rag/pipeline.py`（chunk count limit） |
| **修改前** | `CELERY_TASK_TIME_LIMIT = 300`（5分钟），单文档入库约30s，100文件可能需要2+小时 |
| **修改后核心逻辑** | ① `CELERY_TASK_TIME_LIMIT` 从 300→1800（30分钟）② `CELERY_TASK_SOFT_TIME_LIMIT` 从 240→1500（25分钟）③ 新增 `MAX_CHUNKS_PER_DOCUMENT = 500`④ 新增 `MAX_CHUNKS_PER_BATCH = 5000`⑤ pipeline ingest 中检查 chunk 数量上限 |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-005] |
| **风险评估** | 中风险 — 修改全局 Celery timeout 可能影响其他 task（但1800s仅针对批量场景合理） |

### FEAT-KB-V4.2-BATCH-006: 解析后内容大小限制（🟠 HIGH）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-006 |
| **修复漏洞** | KB-V4.2-BATCH-006 |
| **修改文件** | `backend/apps/rag/pipeline.py`（ingest 方法新增 text size + chunk count 检查）、`backend/config/settings/base.py` |
| **修改前** | `DocumentParser.parse()` 无返回内容大小限制。`RecursiveCharacterTextSplitter` 不限制总 chunk 数 |
| **修改后核心逻辑** | ① 新增 `MAX_EXTRACTED_TEXT_SIZE = 10_000_000`（10MB）② pipeline.ingest() 检查 raw_text 长度 → 超限截断 + `processing_error` 标记③ 新增 `MAX_CHUNKS_PER_DOCUMENT = 500`④ chunk 数量超限 → 截断 + `processing_error` 标记⑤ settings 中配置 `MAX_EXTRACTED_TEXT_SIZE`/`MAX_CHUNKS_PER_DOCUMENT`/`MAX_CHUNKS_PER_BATCH` |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-006] |
| **风险评估** | 低风险 — 纯新增限制逻辑 |

### FEAT-KB-V4.2-BATCH-007: Redis 密码配置匹配（🟡 MEDIUM）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-007 |
| **修复漏洞** | KB-V4.2-BATCH-007 |
| **修改文件** | `docker-compose.v4.kb.yml`（Redis 添加 `--requirepass`） |
| **修改前** | `.env` 中 `REDIS_URL=redis://:sys_redis_pass_2026@redis:6379/0` 含密码，但 compose Redis 无密码 → Celery Connection refused |
| **修改后核心逻辑** | compose Redis 添加 `command: redis-server --requirepass sys_redis_pass_2026` + healthcheck 使用 `-a sys_redis_pass_2026` |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-007] |
| **风险评估** | 低风险 — 仅修改 compose 文件 |

### FEAT-KB-V4.2-BATCH-008: 文件名/标题特殊字符清洗（🟠 HIGH）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-008 |
| **修复漏洞** | KB-V4.2-BATCH-008 |
| **修改文件** | `backend/apps/knowledge/batch.py`（新增 `sanitize_filename()` + `sanitize_title()`）、`backend/apps/knowledge/serializers.py`（新增 `validate_title` validator）、`backend/apps/knowledge/batch_serializers.py` |
| **修改前** | `DocumentSerializer.title` 字段无 `validators=[]` 清洗。前端展示 title 可能触发 XSS |
| **修改后核心逻辑** | ① `sanitize_filename()` 移除 SQL 注入/XSS/路径穿越 pattern + 仅保留安全字符 ② `sanitize_title()` 使用 `bleach.clean()` 清洗 + 移除 SQL 注入 pattern + 截断至255字符 ③ `DocumentSerializer` 新增 `validate_title()` 调用 `sanitize_title()` ④ ZIP 内文件名同样清洗 |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-008] |
| **风险评估** | 低风险 — 纯新增清洗逻辑 |

### FEAT-KB-V4.2-BATCH-009: PDF Metadata 恶意内容清洗（🟡 MEDIUM）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-009 |
| **修复漏洞** | KB-V4.2-BATCH-009 |
| **修改文件** | `backend/apps/knowledge/batch.py`（新增 `sanitize_metadata()`）、`backend/apps/rag/pipeline.py`（ingest 方法调用 sanitize_metadata） |
| **修改前** | `DocumentParser.parse()` 返回的 `page_metadata` 直接存入 `metadata=chunk.get("metadata", {})`，无 bleach/html 清洗 |
| **修改后核心逻辑** | ① `sanitize_metadata()` 使用 `bleach.clean()` 对每个 metadata value 清洗（tags=[], strip=True → 纯文本）② 递归清洗嵌套 dict/list ③ pipeline.ingest() 在存储 DocumentChunk 前调用 `sanitize_metadata()` |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-009] |
| **风险评估** | 低风险 — 纯新增清洗逻辑 |

### FEAT-KB-V4.2-BATCH-010: 手动上传文档去重（🟠 HIGH）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-010 |
| **修复漏洞** | KB-V4.2-BATCH-010 |
| **修改文件** | `backend/apps/knowledge/models.py`（新增 `content_hash` 字段）、`backend/apps/knowledge/migrations/0005_batch_expansion_v4_2.py`、`backend/apps/rag/services.py`（ingest_document 添加 hash 计算）、`backend/apps/knowledge/batch.py`（新增 `compute_content_hash()` + `check_document_duplicate()`） |
| **修改前** | `Document` 模型无 `content_hash` 字段。仅 `CrawledDocument` 有 `content_hash`。手动上传链路无任何去重比对 |
| **修改后核心逻辑** | ① `Document` 模型添加 `content_hash = CharField(max_length=64, blank=True)` + 索引② `ingest_document()` Celery task 入库时计算 SHA256（若 content_hash 为空）③ `compute_content_hash()` 计算 SHA256④ `check_document_duplicate()` 比对库内现有 active/processing 文档⑤ 批量上传流程中先计算全批 content_hash → 比对 → 重复文件跳过 |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-010] |
| **风险评估** | 中风险 — 新增模型字段需要迁移，但 `blank=True, default=""` 保证向后兼容 |

### FEAT-KB-V4.2-BATCH-011: 批量上传策略 + 结果追踪（🟡 MEDIUM）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-011 |
| **修复漏洞** | KB-V4.2-BATCH-011 |
| **修改文件** | `backend/apps/knowledge/models.py`（新增 `BatchImportResultRecord`）、`backend/apps/knowledge/batch.py`（新增 `BatchImportResult` 轻量追踪器）、`backend/apps/knowledge/batch_views.py`（新增 `BatchDocumentUploadView` + `BatchImportResultDetailView`）、`backend/apps/knowledge/batch_serializers.py`、`backend/apps/knowledge/urls.py`、`backend/apps/audit/models.py`（新增 `document_batch_import` + `document_batch_result_view` action） |
| **修改前** | 无批量入库 API → 无批量报告机制。当前单文档上传成功即入库，无比对 |
| **修改后核心逻辑** | ① `BatchImportResultRecord` 模型持久化记录：total_files/success_count/duplicate_skipped_count/failed_count/result_details/status② `BatchImportResult` 内存追踪器（轻量级）③ `BatchDocumentUploadView` API 端点（POST /documents/batch/upload/）④ `BatchImportResultDetailView` API 端点（GET /documents/batch/result/<uuid>/）⑤ `AuditLog` 新增 `document_batch_import` + `document_batch_result_view` action⑥ 批量入库完成后创建 AuditLog |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-011] |
| **风险评估** | 低风险 — 纯新增模块 |

### FEAT-KB-V4.2-BATCH-012: 零向量检测 + Embedding 失败标记（🟡 MEDIUM）

| 字段 | 内容 |
|------|------|
| **变更 ID** | FEAT-KB-V4.2-BATCH-012 |
| **修复漏洞** | KB-V4.2-BATCH-012 |
| **修改文件** | `backend/apps/knowledge/batch.py`（新增 `is_zero_vector()`）、`backend/apps/rag/pipeline.py`（ingest 方法检测零向量 + 标记）、`backend/apps/rag/retriever.py`（pgvector 搜索过滤零向量） |
| **修改前** | `embed_batch()` 失败时返回 `[0.0] * dimension`（零向量），静默退化。DocumentChunk 以零向量入库，Document.status = "active" |
| **修改后核心逻辑** | ① `is_zero_vector()` 检测全零向量② pipeline.ingest() 计算零向量数量 → >50% 则标记 Document.status="failed"③ 每个零向量 chunk 的 `metadata["embedding_failed"] = True`④ retriever pgvector 查询排除 `metadata @> '{"embedding_failed": true}'` 的 chunk |
| **修复依据** | [来源: V4.2/kb_admin/批量扩充安全_gap_list_V4.2.md §KB-V4.2-BATCH-012] |
| **风险评估** | 中风险 — 修改 pipeline ingest 逻辑和 retriever SQL 查询 |

---

## 三、批量扩充专项说明

### 3.1 Zip 安全校验逻辑

```
ZIP 上传 → validate_zip_content() → 四层检查:
  Layer 1: 压缩率 < 100:1（Zip Bomb 防御）
  Layer 2: 总大小 < 500MB（资源耗尽防御）
  Layer 3: 文件数 < 200（资源耗尽防御）
  Layer 4: 嵌套 ZIP 拒绝（深度限制）
  → 逐文件检查:
    - 路径穿越 pattern → 拒绝
    - 符号链接 → 拒绝
    - Magic Number 校验 → 不合规跳过
    - 文件名 sanitize → 清洗
  → 不合规率 > 50% → 整 ZIP 拒绝
```

### 3.2 元数据提取规则

- 自动为所有批量导入文档打标：`source: EY_Batch`、`import_date: YYYY-MM-DD`
- 提取文件标题作为 Document Title（经 `sanitize_title()` 清洗）
- Category 可通过 API 参数统一指定

### 3.3 并发向量化策略

- 批量入库使用 Celery 异步任务（`ingest_document.delay()`）
- Celery Task Timeout 从 300s→1800s（30分钟），支持大批量
- 每个文件独立入库任务，gevent pool 10 并发
- Chunk count 限制：500/doc, 5000/batch
- 零向量自动检测 + 失败标记 + 搜索过滤

---

## 四、V4.1 修复项回归保护

| V4.1 修复项 | V4.2 中的状态 | 保护机制 |
|-------------|-------------|---------|
| JWT is_hr_admin 移除 (KB-V4.1-009) | ✅ 保留 | 无相关代码修改 |
| Token blacklist 修复 (KB-V4.1-010) | ✅ 保留 | 无相关代码修改 |
| Media 认证中间件 (KB-V4.1-007) | ✅ 保留 | 无相关代码修改 |
| Superuser 审计追踪 (KB-V4.1-002) | ✅ 保留 | 无相关代码修改 |
| Magic Number 文件校验 (KB-V4.1-006) | ✅ 保留 | serializers.py 保留原有 validate_file |
| 文件大小上下限 (KB-V4.1-008) | ✅ 保留 | validators.py 保留 MIN_FILE_SIZE |
| SSRF 防御链 | ✅ 保留 | crawler 模块未修改 |
| 爬虫内容清洗 | ✅ 保留 | ContentCleaner 未修改 |
| SHA256 爬虫去重 | ✅ 保留 | CrawledDocument.content_hash 未修改 |
| 文档 DELETE 水平权限 (KB-V4.1-003) | ✅ 保留 | views.py destroy 方法保留 uploaded_by 校验 |
| SQL 过滤键白名单 (KB-V4.1-004) | ✅ 保留 | retriever.py ALLOWED_FILTER_KEYS 保留 |

---

> **报告结束** · V4.2 KB/Admin 批量扩充开发变更日志完成 · 12项安全修复全部落地 · V4.1 修复项全部回归保护
