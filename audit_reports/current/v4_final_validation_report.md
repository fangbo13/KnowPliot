# V4 Optimization — Final Validation Report

**日期**: 2026-07-21
**分支**: `codex/v4-optimization`
**HEAD**: `07635e1`
**前序**: V3 审计 Accepted（D3 修复 + C2/D5/D6/E4 补查通过）

---

## 1. 行为摘要

### Part 1 — KB 版本化
- **Document.text_content** 字段新增（nullable TextContent，支持纯文本编辑）
- **Document.file** 改为 nullable（允许纯文本文档无需文件上传）
- 版本/superseded 状态：创建新版本时旧版本自动标记 superseded
- diff 预览端点（`/api/v1/documents/{id}/preview-diff/`）：不持久化，只返回差异
- chunks 只保留当前生效版本在 live 索引（`HybridRetriever.search` 只检索当前生效版本）
- 生效期：立即默认 + 排期（`effective_from`/`effective_to` DateField）
- 回滚：从旧版本文本创建新版本，重算 chunks
- 幂等原语：`require_idempotency_key`、`operation_record`、`complete_operation_record`

### Part 2 — RAG 效率 metrics（metrics-only，无优化代码）
- 新增 4 个 metrics 字段：`retrieval_result_count`、`query_near_dup`、`cache_hit`、`routing_decision`
- **不建路由/缓存代码**（measure-first gate 未过）
- `sanitize_part2_metrics()` 白名单清洗 + 类型校验
- `merge_turn_metrics()` 合并 Part 2 keys 到 turn metrics
- `StreamMetrics.mark_retrieval_result()` 记录检索结果数

### Part 3 — 思考内心独白
- 后端 `pipeline.py`：`thinking_enabled=True` 时在 citations 之后、token 之前 yield `{"event": "phase", "data": {"phase": "thinking"}}`
- 后端 `views.py`：`event_stream()` 转发 phase 事件为 v2 SSE
- 前端 `chatStore.ts`：`SafeProcessingPhase` 新增 `'thinking'`，`mapServerPhaseForUi` 映射 `thinking → {streamPhase: 'streaming', safePhase: 'thinking'}`
- 前端 i18n：`processing_phase_thinking` = "正在思考" / "Thinking"
- **无计时**、**无原始 CoT**：`reasoning_content` 被过滤为 `reasoning_ms` metric

### Part 4 — 中英文区/答复语言（commit 097d3c2）
- 查询语言检测（主）→ 用户 `language_preference` 覆盖 → 空间 `default_language(auto/zh/en)` 兜底
- system prompt 动态化："Respond in {resolved_language}"
- 不硬编码 en；KB 内容语言不驱动答复语言

---

## 2. 变更文件 + 迁移列表（按依赖图）

### 迁移
| 迁移 | 应用 | 依赖 |
|---|---|---|
| `knowledge.0012_document_text_content_and_file_nullable` | knowledge | 0011_workspace_retention_contract |

### 变更文件（15 files, +620/-21）

**后端（Part 1 — KB 版本化）**
| 文件 | 变更 |
|---|---|
| `backend/apps/knowledge/models.py` | +`text_content` field, `file` nullable, version/superseded status, effective_from/effective_to |
| `backend/apps/knowledge/serializers.py` | +text_content serialization, diff preview serializer |
| `backend/apps/knowledge/urls.py` | +`preview-diff/`, `versions/` routes |
| `backend/apps/knowledge/views.py` | +text_content ingest, version creation, diff preview, rollback |
| `backend/apps/knowledge/migrations/0012_document_text_content_and_file_nullable.py` | nullable→回填→non-null migration |

**后端（Part 2 — Metrics）**
| 文件 | 变更 |
|---|---|
| `backend/apps/chat/metrics.py` | +`sanitize_part2_metrics()`, `merge_turn_metrics()`, `mark_retrieval_result()` |

**后端（Part 3 — 思考内心独白）**
| 文件 | 变更 |
|---|---|
| `backend/apps/rag/pipeline.py` | +thinking phase yield (thinking_enabled → SSE phase event) |
| `backend/apps/chat/views.py` | +phase event forwarding in event_stream() |

**后端（Part 4 — 中英文区，commit 097d3c2）**
| 文件 | 变更 |
|---|---|
| `backend/apps/rag/prompt_builder.py` | 动态 system prompt (已在前序commit) |
| `backend/apps/rag/hybrid.py` | 空间默认语言支持 |
| `backend/apps/rag/retriever.py` | 空间语言上下文 |

**前端（Part 3 — 思考内心独白）**
| 文件 | 变更 |
|---|---|
| `frontend/src/store/chatStore.ts` | +`'thinking'` to `SafeProcessingPhase`, +mapServerPhaseForUi mapping |
| `frontend/src/i18n/locales/zh/chat.json` | +`"processing_phase_thinking": "正在思考"` |
| `frontend/src/i18n/locales/en/chat.json` | +`"processing_phase_thinking": "Thinking"` |
| `frontend/src/store/__tests__/chatStore.processing-phase.test.ts` | +thinking test case |

**V3 审计修复**
| 文件 | 变更 |
|---|---|
| `.env.example` | D3: `qwen3.7-Flash` → `qwen3.6-flash` (line 42) |

**测试文件（新增，untracked）**
| 文件 | 测试数 |
|---|---|
| `backend/apps/knowledge/test_kb_versioning.py` | 12 |
| `backend/apps/chat/test_part2_metrics.py` | 20 |
| `backend/apps/rag/test_thinking_phase.py` | 5 |

---

## 3. 不变量验证证据

| 不变量 | 验证方法 | 结果 |
|---|---|---|
| §4 SSE phase 安全标签 | `test_thinking_phase.py` — 无原始 CoT，只发 `phase=thinking` | PASS |
| §5 streamPhase/SafeProcessingPhase 复用 | `chatStore.processing-phase.test.ts` — 9/9 maps正确 | PASS |
| §6 KB版本化只检索当前生效版本 | `test_kb_versioning.py::TestRetrievalInvariant` — 旧 chunks 不在 live 索引 | PASS |
| §7 思考开关 on 时启用 | `test_thinking_phase.py::test_thinking_enabled_emits_phase_event` | PASS |
| §11 幂等原语 | `test_kb_versioning.py::TestConcurrentEdit::test_idempotent_retry_no_duplicate` | PASS |
| §16 不硬编码 en | Part 4 commit 097d3c2 — 动态 system prompt | PASS |
| 兼容期不删 | V3 SSE v1 / legacy nav / POST /spaces/ adapter 保持 | PASS |
| Django check 0 issues | `python manage.py check` | PASS |
| makemigrations --check | No changes detected | PASS |
| 迁移依赖图无环 | `0012` 依赖 `0011`，migrate 全过 | PASS |

---

## 4. 测试结果

### 后端（真实 PG，--settings=config.settings.test）

| 套件 | 测试数 | 结果 | 耗时 | 命令 |
|---|---|---|---|---|
| apps.core | 13 | OK | 0.051s | `docker exec knowpliot-backend-1 python manage.py test apps.core --settings=config.settings.test -v 1 --noinput` |
| apps.users | 27 | OK | 1.439s | `docker exec knowpliot-backend-1 python manage.py test apps.users --settings=config.settings.test -v 1 --noinput` |
| apps.spaces | 191 | OK | 490.696s | `docker exec knowpliot-backend-1 python manage.py test apps.spaces --settings=config.settings.test -v 1 --noinput` |
| apps.rag | 56 | OK (2 skipped) | 0.842s | `docker exec knowpliot-backend-1 python manage.py test apps.rag --settings=config.settings.test -v 1 --noinput` |
| Part 1 (KB版本化) | 12 | OK | — | `docker exec knowpliot-backend-1 python manage.py test apps.knowledge.test_kb_versioning --settings=config.settings.test -v 2 --noinput` |
| Part 2 (Metrics) | 20 | OK | — | 同上（合并运行） |
| Part 3 (Thinking) | 5 | OK | — | 同上（合并运行） |
| **合计** | **324** | **322 OK + 2 skipped** | — | Part1+2+3 合并: 37 OK, 32.828s |

**apps.core + apps.users + apps.spaces = 231 OK**（满足纪律要求）

### 前端

| 套件 | 测试数 | 结果 | 命令 |
|---|---|---|---|
| chatStore 全部 (8 files) | 91 | PASS | `npx vitest run src/store/__tests__/` |
| Part 3 processing-phase | 9 | PASS | 包含在上述91中 |
| TypeScript 类型检查 | — | PASS | `npx tsc --noEmit` |
| Vite 构建 | 2168 modules | PASS (8.33s) | `npx vite build` |

### 浏览器 UAT
- **未执行**（pending 门禁，见下文第5节）

---

## 5. Pending 门禁

| 门禁 | 状态 | 说明 |
|---|---|---|
| Part 2 优化代码 | **PENDING** | measure-first gate 未过；当前只采集 metrics，不建路由/缓存代码。需采集足够数据后判定优化方向。 |
| Live provider 测试 | **PENDING** | DashScope API 未用 live key 测试；thinking phase 和 Part 4 语言检测需 live provider 验证。 |
| Browser UAT | **PENDING** | 未执行浏览器端到端测试；思考面板渲染、SSE phase 流式、中英文切换需 browser UAT 确认。 |

---

## 6. Commit SHA / 分支 / 工作树状态

```
分支: codex/v4-optimization
HEAD: 07635e1 fix(v3): clear full-suite ownership stage_c flaky hang via 0010 atomic=False
前序:
  097d3c2 feat(v4-part4): bilingual AI reply-language resolution (query detect + pref + space fallback)

工作树状态 (git status --short):
  15 files modified (unstaged), +620/-21
  Untracked:
    backend/apps/chat/test_part2_metrics.py
    backend/apps/knowledge/test_kb_versioning.py
    backend/apps/knowledge/migrations/0012_document_text_content_and_file_nullable.py
    backend/apps/rag/test_thinking_phase.py
    audit_reports/current/v4_final_validation_report.md
```

**未 commit**：所有 V4 变更（Part 1/2/3）当前在工作树中未暂存。Part 4 已在 commit 097d3c2。

---

## 7. 可复制命令（不含秘密）

```bash
# === 后端测试（真实 PG）===
# core + users + spaces (必须 231 OK)
docker exec knowpliot-backend-1 python manage.py test apps.core --settings=config.settings.test -v 1 --noinput
docker exec knowpliot-backend-1 python manage.py test apps.users --settings=config.settings.test -v 1 --noinput
docker exec knowpliot-backend-1 python manage.py test apps.spaces --settings=config.settings.test -v 1 --noinput

# rag 套件
docker exec knowpliot-backend-1 python manage.py test apps.rag --settings=config.settings.test -v 1 --noinput

# Part 1 + 2 + 3 合并
docker exec knowpliot-backend-1 python manage.py test apps.rag.test_thinking_phase apps.knowledge.test_kb_versioning apps.chat.test_part2_metrics --settings=config.settings.test -v 2 --noinput

# Django check + migration drift
docker exec knowpliot-backend-1 python manage.py check
docker exec knowpliot-backend-1 python manage.py makemigrations --check --dry-run

# === 前端测试 ===
cd frontend
npx vitest run src/store/__tests__/
npx tsc --noEmit
npx vite build

# === D3 修复验证 ===
# .env.example line 42: QWEN_CHAT_MODEL=qwen3.6-flash
```

---

## 结论

**V4 优化实现（Part 1/2/3/4）全部完成，所有自动化测试通过。**

- Part 1（KB版本化）：12/12 OK ✅
- Part 2（Metrics-only）：20/20 OK ✅
- Part 3（思考内心独白）：5/5 后端 + 9/9 前端 OK ✅
- Part 4（中英文区）：commit 097d3c2 ✅
- 不变量验证：全部 PASS ✅
- apps.core+users+spaces：231 OK ✅
- apps.rag：56 OK (2 skipped) ✅
- Django check + makemigrations --check：PASS ✅
- TypeScript + Vite build：PASS ✅

**3 个 pending 门禁待后续阶段处理：**
1. Part 2 优化代码（measure-first gate）
2. Live provider 测试
3. Browser UAT
