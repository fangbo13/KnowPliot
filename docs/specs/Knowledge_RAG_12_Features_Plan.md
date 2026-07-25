# KnowPilot 知识库（Knowledge & RAG）12 项功能完善计划

> 版本：保守版（Conservative）
> 定位：**以"功能描述 + 预期结果"为主**。仅在已对照当前代码 **100% 核实**的地方写入实现约束事实；不确定的实现细节不臆断，留待执行阶段结合代码确认。
> 背景风险：**当前无多余备份分支，任何破坏性错误都是灾难级的**。执行时必须遵守文末《安全交付要求》。
> 运行方式：**代码通过 Docker 启动**（`docker-compose.yml`，`config.settings.docker`）。

---

## 0. 通用前提（均已对照代码核实）

以下为跨功能共享的既有事实，各功能条目不再重复：

- 后端版本化端点**已实现**（`backend/apps/knowledge/views.py`，`urls.py`）：
  - `PATCH /documents/{id}/text/`（暂存 text_content，不触发版本切换）
  - `POST /documents/{id}/preview-diff/`（返回行级差异，响应字段名为 `diff`，另含 `stats`）
  - `POST /documents/{id}/versions/`（创建新版本，原子重分块+重嵌入）
  - `POST /documents/{id}/rollback/`（回滚到版本链上的目标版本）
- `versions/` 路由**目前只有 POST，没有 GET**（无版本历史列表端点）。
- `DocumentSerializer` 已暴露 `text_content / version / effective_from / effective_to`；**未包含 `parent_document`**；**`status` 为只读**（不能用 PATCH 修改状态）。
- `POST /documents/{id}/versions/` 与 `POST /documents/{id}/rollback/` **强制要求 `Idempotency-Key`（UUID）请求头**，缺失/非 UUID 直接 400。前端已有成熟写法：`headers: { 'Idempotency-Key': crypto.randomUUID() }`（见 `frontend/src/api/spaces.ts`）。
- `X-Space-Id` 空间头由 axios 拦截器（`frontend/src/api/client.ts`）**自动注入**，新接口无需手动添加。
- 只读 Markdown 渲染组件位于 `frontend/src/components/chat/markdown.tsx`（导出 `MarkdownView`）；无可编辑编辑器。
- 批量导入端点**已实现**：`POST /documents/batch/upload/`（ZIP）、`GET /documents/batch/result/{id}/`（`backend/apps/knowledge/batch_views.py`）。
- `templates/` 路由映射的是**答案模板** `AnswerTemplateListView`，**并非文档模板**。
- Word/PDF→Markdown 能力（`DocumentParser` 的 `export_to_markdown`，`backend/apps/rag/pipeline.py`）**目前仅在文档 ingestion 内部使用**，未对外暴露独立端点。
- 前端 `documentApi`（`frontend/src/api/documents.ts`）当前仅 11 个方法，**缺少全部版本化与批量方法**。

### Docker 运行时硬约束（已核实，务必遵守）

- **后端**：源码 bind-mount（`./backend:/app`）+ gunicorn `--reload` → **改后端代码热重载即可，无需重建镜像**；`--workers 2 --threads 8 --timeout 120`。
- **同步长任务风险**：任何在 HTTP 请求内同步执行、耗时可能 **>120s** 的操作会被 gunicorn 杀掉返回 502，并占用有限的 worker 线程。
- **前端**：镜像内 `vite build` → nginx 服务 `dist`。**前端任何改动必须 `docker compose build frontend` 重建镜像后才生效**，且 BuildKit 使用已提交/暂存的源码，**改动需先 `git add`/提交**。
- **Celery worker 可用**（`-c 4`，与后端同镜像、共享 `media_volume`），适合承载耗时任务。
- **数据库**：PostgreSQL 16 + pgvector（非 SQLite），版本重嵌入走 pgvector 原生写入，测试须在该环境进行。
- 本计划不改动数据模型，**无新增迁移**；后端启动会自动 `migrate`。

---

## 1. 前端 API 客户端缺失版本化端点方法

**功能描述**：后端四个版本化端点已就绪，但 `frontend/src/api/documents.ts` 的 `documentApi` 未提供对应调用方法（缺 `editTextContent`、`previewDiff`、`createVersion`、`rollbackVersion`）。

**预期结果**：前端可完整调用四个版本化端点；其中创建版本与回滚请求**自动携带 `Idempotency-Key` 头**，不会因缺头返回 400，也不会重复提交。

**已核实约束**：`createVersion`/`rollbackVersion` 必须带 `Idempotency-Key`；`X-Space-Id` 自动注入无需处理。

---

## 2. 前端知识库页面缺失版本管理 UI

**功能描述**：`frontend/src/pages/admin/KnowledgeBasePage.tsx` 目前仅有文档列表、上传、元数据（标题/分类）编辑、归档、重建索引、下载。缺少：内联 Markdown 编辑、差异预览、正文预览、版本历史列表、版本创建/回滚入口、从文本创建入口。

**预期结果**：管理员可在知识库页面内完成"查看正文 → 编辑 Markdown → 预览差异 → 创建版本 → 查看版本历史 → 回滚"的完整操作，写操作受既有 `knowledge.manage` 权限门禁约束。

**已核实约束**：写操作需 `canManage`；具体承载形式（抽屉/弹窗/子页面）为设计选择，执行阶段确定，不在本计划中锁定。

---

## 3. 后端缺少版本历史列表端点（GET versions/）

**功能描述**：`versions/` 仅映射到只实现 POST 的 `DocumentVersionCreateView`，无法列出某文档的历史版本。

**预期结果**：新增 `GET /documents/{id}/versions/`，返回该文档版本链的列表（含版本号、状态、生效起止、创建时间等），作为前端版本历史界面与回滚目标选择的数据来源。

**已核实约束**：版本链通过 `parent_document` 自引用维系；回滚逻辑已按链遍历实现，可复用同类遍历方式。

---

## 4. 前端 Document 接口类型缺少版本化字段

**功能描述**：页面内 `Document` 接口仅含 7 个字段，缺 `text_content / version / parent_document / effective_from / effective_to`，导致 TypeScript 层丢弃后端已返回的版本化数据。

**预期结果**：前端类型包含上述版本化字段，列表可展示版本号/生效期，编辑器可读取 `text_content`。

**已核实约束**：后端 `DocumentSerializer` 已返回 `text_content/version/effective_from/effective_to`；**`parent_document` 目前不在序列化输出中**——如需前端展示血缘，需要么由功能③的版本列表接口提供，要么在序列化器 `fields` 追加 `parent_document`（只读、无迁移）。此取舍在执行阶段确认。

---

## 5. 前端缺少可编辑的 Markdown 编辑器组件

**功能描述**：现有 `markdown.tsx` 只有只读 `MarkdownView`，没有支持输入、实时预览与格式工具栏的可编辑编辑器。

**预期结果**：提供一个可编辑 Markdown 组件：文本输入 + 实时预览（复用 `MarkdownView`）+ 基础格式工具栏，供内联编辑与从文本创建复用。

**已核实约束**：应复用现有 `MarkdownView` 的渲染与 XSS 白名单；颜色须用 CSS 变量以支持亮/暗双模式（遵循暗色对比度规范）。

---

## 6. 前端缺少 Diff 预览组件

**功能描述**：`preview-diff` 返回结构化行级差异，但前端无组件渲染，用户保存版本前无法预览变更。

**预期结果**：提供差异展示组件，按差异类型（未变/新增/删除/替换）以不同颜色区分渲染，并展示统计信息。

**已核实约束**：后端响应字段为 `diff`（数组），每块含 `tag`（`equal/replace/delete/insert`）、`old_lines`、`new_lines` 等；颜色须用 CSS 变量保证暗色对比度。

---

## 7. 缺少端到端文档创作流程

**功能描述**：当前仅支持"上传文件→解析→分块嵌入"单向流程，缺少"从文本创建（无文件）→ 编辑 → 预览差异 → 创建版本 → 版本历史 → 回滚"的连续创作闭环。

**预期结果**：用户无需上传文件即可创建文本文档并走完整版本化流程，各步骤有即时反馈；创建/回滚这类重操作有明确的进行中状态提示。

**已核实约束**：后端支持无文件的 `text_content` 创建（`DocumentSerializer` 在无 file 时默认 `file_type=md`）；但现有 `uploadDocument` 强制以 FormData 追加 file，从文本创建需另走 JSON 请求体的创建路径。**创建版本/回滚在请求内同步重嵌入，受 gunicorn 120s 限制**——大文档需做大小提示或长任务处理。

---

## 8. 缺少 Markdown 文档模板下载端点

**功能描述**：无文档模板端点（`templates/` 是答案模板）。页面提示推荐 MD 格式，但用户无模板可参考。

**预期结果**：新增文档模板获取端点，返回预定义的 Markdown 模板（如政策文档、FAQ 等）；前端可下载或一键填入编辑器。

**已核实约束**：`templates/<uuid:pk>/` 使用 UUID 转换器，`templates/md/` 之类字面量路径不与其冲突。为在 Docker 镜像中稳定可用，模板内容建议以后端常量提供（或确保随镜像打包）。

---

## 9. 缺少独立的 Word/PDF→Markdown 转换端点

**功能描述**：转换能力仅在 ingestion 内部使用，用户上传 Word/PDF 后无法单独获取转换后的 Markdown 文本用于编辑。

**预期结果**：在允许的文件大小范围内，用户上传 Word/PDF 后可**同步**获得对应 Markdown 文本，用于内联编辑与后续版本化；超出大小上限的文件被明确拒绝（不进入解析），转换过程不影响服务稳定性。

**方案决策（已确认）**：首版采用**同步转换 + 严格大小限制**；异步（Celery + 前端轮询）列为后续增强，非本次交付内容。
- 理由：同步方案改动面小、失败模式良性（超大文件仅返回"文件过大/超时"，**非破坏、可重试**）；异步的唯一实质收益（规避 gunicorn 120s 超时）可用大小上限直接规避。在**无备份分支**的前提下，更少的新代码 = 更低的风险。
- 同步实现护栏（均在已核实事实范围内）：
  1. 转换端点设**更保守的文件大小上限**（复用 `validate_document_size`，内联转换用更低阈值），超限直接返回清晰错误，不进入解析。
  2. 复用现有 `DocumentParser`，**纯转换、不落库、无副作用**；结束清理临时文件。
  3. 解析失败/不支持类型返回明确错误，**绝不留半成品状态**。
  4. 允许范围内（典型 Office 文档数 MB）转换在 gunicorn 120s 内可完成。
- 后续升级触发条件：当需转换大体积/扫描版 PDF（Docling OCR 很重）或批量转换时，再上 Celery 异步 + 结果存 Redis（带 TTL）+ 轮询，作为独立增强，不影响已交付部分。

---

## 10. i18n 缺失版本化与文档编辑相关翻译键

**功能描述**：`en/common.json` 与 `zh/common.json` 缺少版本化、差异、Markdown 编辑、模板、批量导入等相关翻译键（现有 `kb_` 键仅覆盖基础操作）。

**预期结果**：所有新增 UI 文本均走 i18next，中英文完整覆盖，`npm run check:i18n` 通过。

**已核实约束**：已存在部分 `kb_` 键（如 `kb_edit/kb_diff/kb_diff_original/kb_diff_current/kb_no_diff/kb_update_*`），新增键需避免与其重复；中英文须同步新增。

---

## 11. 前端缺少批量上传 UI（后端已有端点）

**功能描述**：后端批量上传/结果查询端点已就绪，但 `documentApi` 无 `batchUpload`/`getBatchResult` 方法，页面无 ZIP 上传入口与结果展示。

**预期结果**：用户可上传 ZIP 批量导入文档，并查看导入统计与明细（成功/重复跳过/失败）。

**已核实约束**：后端接口为 `POST /documents/batch/upload/`（FormData，字段含 ZIP）与 `GET /documents/batch/result/{id}/`。

---

## 12. 前端 archiveDocument 与 deleteDocument 实现重复

**功能描述**：`documents.ts` 中 `archiveDocument` 与 `deleteDocument` 实现完全相同，均为 `DELETE /documents/{id}/`。

**预期结果**：归档与删除语义清晰区分——归档为可恢复的软归档，删除为永久删除（且对被引用文档有保护）。

**已核实约束（对原始描述的修正）**：经核实，后端 `DocumentDetailView.destroy()` **默认执行软归档**（置 `status='archived'`），仅 `?hard=true` 才硬删除（被引用时返回 409）。因此**当前"归档"行为其实是安全的软归档**，真正的语义缺口在于"删除"并未真正删除。推荐修正：`archiveDocument` 保持软归档（DELETE），`deleteDocument` 改为 `DELETE ...?hard=true` 实现真正删除。**不要**用 PATCH 修改 `status`（该字段只读，会被静默忽略）。

---

## 安全交付要求（因无备份分支，强制）

1. **开工前先创建备份分支**（如 `backup/kb-12-features-<日期>`），确保有可回退点。
2. **逐个功能小步提交**，每完成一项即提交，便于精确回退；严禁一次性大改。
3. **不重构**版本创建/回滚的原子事务（`_create_version_atomically`），避免破坏一致性保证。
4. **验证在 Docker 环境内进行**：
   - 后端：改动后依赖 `--reload` 热重载；在容器内运行 `ruff check .`、`mypy .`、`pytest`、`python manage.py check`、`migrate --check`。
   - 前端：改动后需 `git add` 并 `docker compose build frontend` 重建镜像，再运行 `lint`/`typecheck`/`test`/`check:i18n`/`build` 验证。
5. **优先后端、后前端**：先补 GET versions/、模板、转换端点并验证，再做前端对接，避免前端对接未完成的接口。
6. 每项功能以本计划中的**预期结果**作为验收标准。

## 建议实施顺序（低风险优先）

③（GET versions）→ ⑧（模板端点）→ ⑨（转换端点，同步+严格大小限制）→ ①（API 方法）→ ④（类型）→ ⑩（i18n）→ ⑤（编辑器）→ ⑥（Diff）→ ②（页面版本 UI）→ ⑦（端到端流程）→ ⑪（批量 UI）→ ⑫（归档/删除修正）
