# 批量扩充安全 Gap List V4.2 — KB/Admin 领域

> **版本**: V4.2  
> **日期**: 2026-06-26  
> **审计师**: 企业级安全审计师  
> **漏洞分类**: 【批量注入】、【资源耗尽】、【元数据安全】、【去重失效】  
> **核心前提**: 批量扩充功能尚未实现，本报告以攻击模拟 + 代码审查方式识别架构级安全缺漏

---

## 【批量注入】类漏洞

### KB-V4.2-BATCH-001: Zip Bomb 攻击——无压缩率检测

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-001 |
| **风险等级** | 🔴 CRITICAL |
| **漏洞类型** | 批量注入 — Zip Bomb |
| **攻击 Payload** | 构造递归嵌套 ZIP：`zip -9 -r bomb.zip layer1/`，42KB → 4.5GB 解压。或使用经典 Zip42（42KB 压缩 → 4.5PB 解压） |
| **预期** | 系统拒绝压缩率 > 100:1 的 ZIP；解压后总大小 < 设定阈值；解压深度 ≤ 3 层；ZIP 内文件数 ≤ 100 |
| **实际** | 代码库中**完全无 ZIP 处理代码**。`filetype` 库能检测 ZIP MIME (`application/zip`)，但 `ALLOWED_MIME_TYPES` 不含 ZIP 类型。一旦批量扩充功能添加 ZIP 支持，若无防护，将直接接受任何 ZIP |
| **截图证据** | 代码搜索 `zipfile.ZipFile` → 0 结果；`ALLOWED_MIME_TYPES` 不含 `application/zip` |
| **影响范围** | 系统全局：磁盘空间耗尽 → Docker 容器崩溃 → 全服务停机 |
| **修复建议** | 1. `ALLOWED_MIME_TYPES` 添加 `"zip": ["application/zip"]` 但必须配合压缩率检测  
2. 新增 `validate_zip_content()` 函数：检查 `zipfile.infolist()` 压缩率（`compress_size / file_size < 0.01` → 拒绝）  
3. 解压深度限制 ≤ 3 层（检测嵌套 ZIP）  
4. ZIP 内文件数限制 ≤ 200  
5. 解压后总大小 ≤ `BULK_UPLOAD_TOTAL_SIZE_MB` (建议 500MB) |

---

### KB-V4.2-BATCH-002: ZIP 内文件名路径穿越

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-002 |
| **风险等级** | 🟠 HIGH |
| **漏洞类型** | 批量注入 — 路径穿越 |
| **攻击 Payload** | 构造 ZIP 内含文件名 `../../../etc/cron.d/evil.sh` 或 `..\..\..\Windows\System32\evil.bat` |
| **预期** | 系统拒绝含路径穿越 pattern 的 ZIP 内文件名；所有文件名应经过清洗 |
| **实际** | 无 ZIP 解压代码，无文件名清洗逻辑。Django `FileField` 使用 `upload_to="documents/%Y/%m/"` + 原始文件名，可能被穿越 |
| **截图证据** | `Document.file = FileField(upload_to="documents/%Y/%m/")` — 无文件名清洗 |
| **影响范围** | 任意文件写入：攻击者可写入系统关键目录 |
| **修复建议** | 1. ZIP 解压时检查每个 entry 的文件名：`entry.filename` 不应含 `/../` 或 `\..\`  
2. 使用 `os.path.basename(entry.filename)` 去除路径前缀  
3. 新增 `sanitize_filename()` 函数：移除特殊字符 (`'; DROP TABLE; --`、`<script>`、路径穿越 pattern) |

---

### KB-V4.2-BATCH-003: ZIP 内文件类型不校验

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-003 |
| **风险等级** | 🟠 HIGH |
| **漏洞类型** | 批量注入 — 类型绕过 |
| **攻击 Payload** | 构造 ZIP 内含 10 个 PE 可执行文件改名 `.pdf`。外层 ZIP 声明合法，内层文件恶意 |
| **预期** | ZIP 内每个文件必须通过 Magic Number 校验（与顶层上传相同标准） |
| **实际** | `validate_file_content_type()` 仅校验顶层上传的文件。ZIP 内文件不会逐个通过 Magic Number 校验 |
| **截图证据** | `validators.py:ALLOWED_MIME_TYPES` 不含 ZIP 类型；一旦添加，需对每个解压后的文件也校验 |
| **影响范围** | 恶意文件入库：伪装 .pdf/.docx 的可执行文件进入知识库 |
| **修复建议** | 1. ZIP 解压后对每个文件调用 `validate_file_content_type()`  
2. 不合规文件跳过 + 记录 `batch_import_error` AuditLog  
3. 不合规文件 > 50% → 整个 ZIP 拒绝 |

---

## 【资源耗尽】类漏洞

### KB-V4.2-BATCH-004: 无批量上传限流——API 级资源耗尽

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-004 |
| **风险等级** | 🔴 CRITICAL |
| **漏洞类型** | 资源耗尽 — API 无限流 |
| **攻击 Payload** | 脚本化循环调用：`for i in {1..500}; do curl -X POST /api/v1/documents/ -F "file=@doc.pdf" -F "title=Batch_$i" -F "file_type=pdf"; done` |
| **预期** | 文档上传接口有专属限流（如 10/分钟/user）；批量上传接口有更严格限流 |
| **实际** | `DocumentListCreateView` 无 throttle_classes。`DRF DEFAULT_THROTTLE_CLASSES` 仅限 AnonRateThrottle（100/min）和 UserRateThrottle（未在 KB compose 中配置）。**HR/Admin 可无限调用上传接口** |
| **截图证据** | `knowledge/views.py:30` — `permission_classes = [IsAuthenticated, IsHROrAdmin]`，无 throttle_classes |
| **影响范围** | Celery worker slot 占满 → 正常文档入库阻塞 → DashScope API 限流 → 全系统不可用 |
| **修复建议** | 1. 新增 `DocumentUploadRateThrottle`（如 10/分钟/user）  
2. 批量上传接口 `BatchDocumentUploadView` → 3/分钟/user + 单次 ZIP ≤ 100 文件  
3. 新增 `BULK_UPLOAD_MAX_DOCUMENTS = 100` settings  
4. 新增 `BULK_UPLOAD_TOTAL_SIZE_MB = 500` settings |

---

### KB-V4.2-BATCH-005: Embedding API 并发耗尽——Celery Worker 卡死

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-005 |
| **风险等级** | 🟠 HIGH |
| **漏洞类型** | 资源耗尽 — Embedding API 卡死 |
| **攻击 Payload** | 上传 100 个 5MB PDF → 每个平均 50 chunks → 5000 个 DashScope API 调用 → 10 worker 并行 → 每个调用 ~1-2s → 总计 2+ 小时 |
| **预期** | 单次批量入库 ≤ 100 文件；Embedding API 调用有总上限；Celery task timeout 充足 |
| **实际** | `CELERY_TASK_TIME_LIMIT = 300s`（5 分钟）。单文档入库约 30s，100 文件可能需要 2+ 小时。gevent -c 10 可并行 10 个 task，但 `time.sleep(0.5)` 每 5 次调用会阻塞 |
| **截图证据** | `config/settings/base.py:150` — `CELERY_TASK_TIME_LIMIT = 300`；`embedding.py:274` — `time.sleep(0.5)` rate limiting |
| **影响范围** | Celery worker 长时间占用 → 新任务排队 → 用户体验卡顿 |
| **修复建议** | 1. 批量入库应使用 `batch_ingest_document` Celery task（含整个 ZIP 的入库流程）  
2. Task timeout 提升至 `CELERY_TASK_TIME_LIMIT = 1800`（30 分钟）仅对批量 task  
3. 新增 `MAX_CHUNKS_PER_BATCH = 5000` 限制  
4. Embedding batch 限流改为 Redis-based distributed rate limit |

---

### KB-V4.2-BATCH-006: 解析后内容大小无限制——内存溢出

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-006 |
| **风险等级** | 🟠 HIGH |
| **漏洞类型** | 资源耗尽 — 内存溢出 |
| **攻击 Payload** | 上传含大量嵌入图片的 PDF → Docling 解析提取所有文本 → 50MB PDF 可能产生 2GB+ 纯文本 |
| **预期** | 解析后文本大小有上限（如 10MB per document）；超出则截断或拒绝 |
| **实际** | `DocumentParser.parse()` 无返回内容大小限制。`DocumentChunk.content = TextField` 可存任意大小文本。`RecursiveCharacterTextSplitter(chunk_size=500)` 不限制总 chunk 数 |
| **截图证据** | `pipeline.py:45` — `raw_text, page_metadata = self.parser.parse(document.file.path, document.file_type)` 无大小检查 |
| **影响范围** | 内存溢出 → Celery worker crash → 文档入库失败 |
| **修复建议** | 1. 新增 `MAX_EXTRACTED_TEXT_SIZE = 10_000_000`（10MB）在 pipeline 中检查  
2. 超出则截断 + `Document.processing_error = "Extracted text exceeds size limit"`  
3. 新增 `MAX_CHUNKS_PER_DOCUMENT = 500` 限制 |

---

### KB-V4.2-BATCH-007: Celery 连接配置不匹配——全量服务中断

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-007 |
| **风险等级** | 🟡 MEDIUM |
| **漏洞类型** | 资源耗尽 — 配置不匹配 |
| **攻击 Payload** | 无需攻击——自然触发。`.env` 中 `REDIS_URL=redis://:sys_redis_pass_2026@redis:6379/0`，但 `docker-compose.v4.kb.yml` Redis 无密码 |
| **预期** | `.env` 配置与 compose 服务配置一致 |
| **实际** | Celery worker 报 `kombu.exceptions.OperationalError: [Errno 111] Connection refused`；文档上传 POST 返回 500 |
| **截图证据** | `.env:14` — `REDIS_URL=redis://:sys_redis_pass_2026@redis:6379/0`；`docker-compose.v4.kb.yml` Redis 无 `command: redis-server --requirepass` |
| **影响范围** | 所有依赖 Celery 的功能不可用：文档入库、爬虫入库、批量处理 |
| **修复建议** | 1. `docker-compose.v4.kb.yml` Redis 添加 `command: redis-server --requirepass sys_redis_pass_2026`  
2. 或修改 `.env` `REDIS_URL=redis://redis:6379/0`（移除密码，适用于开发环境） |

---

## 【元数据安全】类漏洞

### KB-V4.2-BATCH-008: 文件名特殊字符注入

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-008 |
| **风险等级** | 🟠 HIGH |
| **漏洞类型** | 元数据安全 — 文件名注入 |
| **攻击 Payload** | 上传文件名 `'; DROP TABLE knowledge_document; --.pdf`（SQL 注入 pattern）；或 `test<script>alert(1)</script>.pdf`（XSS pattern） |
| **预期** | 文件名被清洗：移除 SQL 注入 pattern、XSS pattern、路径穿越 pattern |
| **实际** | Django ORM 参数化查询保护 SQL 注入（✅ 安全），但文件名存入 `Document.title` 字段（`CharField(max_length=255)`）未经清洗。前端展示 `title` 可能触发 XSS |
| **截图证据** | `knowledge/serializers.py` — `DocumentSerializer` 的 `title` 字段无 `validators=[]` 清洗 |
| **影响范围** | 存储型 XSS：恶意文件名在前端管理页面渲染时执行 |
| **修复建议** | 1. 新增 `sanitize_title()` validator：移除 `<script>`、`'; DROP`、`../` 等 pattern  
2. 文件名使用 `os.path.basename()` + `slugify()` 清洗  
3. ZIP 内文件名同样清洗 |

---

### KB-V4.2-BATCH-009: PDF Metadata 恶意内容注入

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-009 |
| **风险等级** | 🟡 MEDIUM |
| **漏洞类型** | 元数据安全 — PDF metadata 注入 |
| **攻击 Payload** | 创建 PDF 文件，其 Author/Title metadata 含 `<script>alert(document.cookie)</script>` |
| **预期** | 提取的 PDF metadata 在存入 `DocumentChunk.metadata` (JSONField) 前应被清洗 |
| **实际** | `DocumentParser.parse()` 返回的 `page_metadata` 直接存入 `metadata=chunk.get("metadata", {})`。无 bleach/html 清洗 |
| **截图证据** | `pipeline.py:63` — `metadata=chunk.get("metadata", {})` 直接传入 JSONField |
| **影响范围** | JSONField 中的恶意内容在前端渲染时可能触发 XSS |
| **修复建议** | 1. 新增 `sanitize_metadata()` 函数：bleach 清洗每个 metadata value  
2. `DocumentChunk.metadata` 存入前调用清洗 |

---

## 【去重失效】类漏洞

### KB-V4.2-BATCH-010: 手动上传无去重——数据冗余与向量检索降质

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-010 |
| **风险等级** | 🟠 HIGH |
| **漏洞类型** | 去重失效 — 手动上传无 content_hash |
| **攻击 Payload** | HR-A 上传《入职指南.pdf》；HR-B 上传同一文件改名《指南(副本).pdf》；两个 Document 并存 → 重复 embedding → 检索返回重复结果 |
| **预期** | 系统检测到内容相同 → 提示用户"文档内容已存在" → 用户选择跳过/覆盖 |
| **实际** | `Document` 模型无 `content_hash` 字段。仅 `CrawledDocument` 有 `content_hash`。手动上传链路无任何去重比对 |
| **截图证据** | `knowledge/models.py:32-80` — Document 字段不含 `content_hash`；`crawler/models.py` — CrawledDocument 含 `content_hash` |
| **影响范围** | 数据冗余：重复 embedding → 检索质量降质 → DashScope API 费用浪费 |
| **修复建议** | 1. `Document` 模型添加 `content_hash = CharField(max_length=64, blank=True)`  
2. `ingest_document()` Celery task 入库时计算 SHA256 并比对  
3. 重复 → 返回 `duplicate_detected` 状态 + 用户选择策略  
4. 批量上传时，先计算全批 content_hash → 批量比对 → 增量入库 |

---

### KB-V4.2-BATCH-011: 批量上传策略未定义——重复文件处理歧义

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-011 |
| **风险等级** | 🟡 MEDIUM |
| **漏洞类型** | 去重失效 — 策略未定义 |
| **攻击 Payload** | 无需攻击——自然场景。批量 ZIP 内含 3 个与库内已有内容重复的文件 + 7 个新文件 |
| **预期** | 系统返回明确的批量报告：7 新入库 + 3 跳过(已存在) |
| **实际** | 无批量入库 API → 无批量报告机制。当前单文档上传成功即入库，无比对 |
| **截图证据** | 无 `BatchDocumentUploadView` 或 `batch_ingest` endpoint |
| **影响范围** | 用户无法得知哪些文件重复、哪些入库成功 |
| **修复建议** | 1. 新增 `BatchImportResult` 模型：记录 total_files / success / duplicate_skipped / failed  
2. 批量入库完成后发送 AuditLog `action="document_batch_import"`  
3. 前端展示批量报告 + 重复文件列表 |

---

### KB-V4.2-BATCH-012: Embedding 失败静默退化——零向量污染

| 字段 | 内容 |
|------|------|
| **漏洞 ID** | KB-V4.2-BATCH-012 |
| **风险等级** | 🟡 MEDIUM |
| **漏洞类型** | 去重失效 — 零向量退化 |
| **攻击 Payload** | 上传 100 文件 → DashScope API 限流 → 20 个 chunk 返回零向量 → 检索无法命中 |
| **预期** | Embedding 失败 → 标记 `Document.status = "failed"` + `processing_error` → 用户可见 |
| **实际** | `EmbeddingService.embed_batch()` 失败时返回 `[0.0] * dimension`（零向量），静默退化。DocumentChunk 以零向量入库，`Document.status` 标记为 `active` |
| **截图证据** | `embedding.py:292` — `return [0.0] * dimension`（fallback on error） |
| **影响范围** | 检索质量降质：用户认为文档已入库，实际检索无法命中 |
| **修复建议** | 1. 零向量入库 → 标记 `DocumentChunk.metadata["embedding_failed"] = True`  
2. `PgVectorRetriever._search_pgvector()` 过滤零向量（`embedding_vector IS NOT NULL AND embedding_vector != '[0,...,0]'`)  
3. 失败 chunk 超过 50% → Document.status = "failed" |

---

## 漏洞统计

| 分类 | 数量 | CRITICAL | HIGH | MEDIUM |
|------|------|----------|------|--------|
| 【批量注入】 | 3 | 1 | 2 | 0 |
| 【资源耗尽】 | 4 | 1 | 2 | 1 |
| 【元数据安全】 | 2 | 0 | 1 | 1 |
| 【去重失效】 | 3 | 0 | 1 | 2 |
| **总计** | **12** | **2** | **6** | **4** |

---

> **引用来源**:  
> - [来源: backend/apps/knowledge/models.py §Document]  
> - [来源: backend/apps/knowledge/serializers.py §validate_file()]  
> - [来源: backend/apps/core/validators.py §ALLOWED_MIME_TYPES]  
> - [来源: backend/apps/rag/pipeline.py §ingest()]  
> - [来源: backend/apps/rag/embedding.py §embed_batch()]  
> - [来源: backend/apps/crawler/models.py §CrawledDocument.content_hash]  
> - [来源: backend/config/settings/base.py §CELERY_TASK_TIME_LIMIT]  
> - [来源: .env §REDIS_URL]
