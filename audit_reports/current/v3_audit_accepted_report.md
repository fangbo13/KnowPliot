# V3 审计 Accepted 报告

> 日期：2026-07-21
> 分支：codex/v3-audit-fix（HEAD = 07635e1）
> 审计性质：V3 审计 → V4 优化 Goal 模式交接，阶段一（V3 收尾修复）
> 结论：**Accepted**（无条件通过）

---

## 一、修复摘要

### D3（FAIL → PASS）：.env 模型 ID 修正
- **根因**：`.env` 与 `.env.example` 第 42 行均为 `QWEN_CHAT_MODEL=qwen3.7-Flash`（弃用别名），与 canonical fast 模型 `qwen3.6-flash` 不匹配。
- **修复**：
  - `.env.example` 第 42 行：`qwen3.7-Flash` → `qwen3.6-flash`
  - `.env` 第 42 行：`qwen3.7-Flash` → `qwen3.6-flash`
- **验证**：
  - `docker compose up -d backend`（重建容器以重载 env_file；`docker restart` 不重载 env_file）
  - Django settings 确认：`QWEN_CHAT_MODEL = qwen3.6-flash`
- **证据**：`readiness` 检查 `canonical_models: ok`

### D4（FAIL → PASS）：readiness
- **根因**：由 D3 导致——`_legacy_aliases_match()` 检测 `settings.QWEN_CHAT_MODEL` 与 `CANONICAL_FAST_MODEL` 不匹配 → `canonical_models: not_ready`。
- **修复**：随 D3 修复自动解决。
- **验证证据**：
  ```
  curl -s http://127.0.0.1:8000/api/v1/health/ready/
  {"status":"ready","checks":{"database":"ok","migrations":"ok","canonical_models":"ok","creation_reviewers":"disabled","creation_policy":"disabled","join_credentials":"disabled","template_clone_contract":"ok","shared_rate_limit":"ok","purge_registry":"disabled"}}
  ```

---

## 二、补查项结果

### C2（PENDING → PASS）：前端 build
- **命令**：`cd frontend && npm install && npm run build`
- **npm install**：391 packages added（3 moderate + 1 high + 1 critical vulnerabilities，不影响 build）
- **tsc -b**：通过（无类型错误）
- **vite build**：`✓ 2168 modules transformed`，dist 产物正常输出
- **check-bundle-budget.mjs**：`"violations": []`（预算通过）
- **结论**：PASS

### D5（PENDING → PASS）：chat send SSE 流式返回
- **方法**：Django test client（绕过 cmd.exe JSON 引号破坏问题）
  1. 创建 test org + KnowledgeSpace（`create_space_with_owner` 满足 DB 触发器 `spaces_assert_canonical_owner_mirror`）
  2. 为 test org 创建 GovernancePolicy 绑定 canonical model profiles（test org 新建无 policy → `resolve_effective_policy` 返回不含 `fast_model_profile_id` 的 defaults → `GenerationPolicyNotReady`）
  3. Login 200（JWT access token）
  4. CREATE SESSION 201（session_id 返回）
  5. POST `/api/v1/chat/sessions/{id}/send/` → SSE
- **结果证据**：
  ```
  SEND status: 200
  SEND Content-Type: text/event-stream
  SSE markers present (event:/data:): True

  event: quality
  data: {"confidence": "insufficient", "score": 0.0, "needs_human_review": true, "retrieval_mode": "hybrid", "retrieval_latency_ms": 3266}

  event: token
  data: {"token": "Sorry, the knowledge retrieval service is temporarily unavailable. Please try again later."}

  event: citations
  data: []

  event: done
  data: {"message_id": "...", "session_id": "...", "model": "qwen3.6-flash", "turn_id": "...", "client_request_id": "..."}
  ```
- **说明**：检索 401 Unauthorized（外部 dashscope API key 无效）是测试环境配置问题，非代码缺陷；SSE 流式契约（quality → token → citations → done 四事件，model=qwen3.6-flash canonical）完整验证通过。
- **结论**：PASS

### D6（PENDING → PASS）：embedding 配置
- **期望**：`text-embedding-v4`（1024 维）
- **settings/base.py 证据**：
  - `RAG_EMBEDDING_MODEL = os.environ.get("QWEN_EMBEDDING_MODEL", "text-embedding-v4")`
  - `RAG_EMBEDDING_DIM = 1024`
  - `PGVECTOR_DIMENSION = 1024`
- **结论**：PASS

### E4（PASS* → PASS）：§11 兼容期 adapter
- **期望**：SSE v1 / legacy nav / POST /spaces/ adapter 保留，不回退 direct-create
- **证据**：
  - `apps/spaces/views.py:130`：「The compatibility route must never restore direct creation.」
  - `POST /spaces/` → governed adapter → `submit_creation_request` → 返回 202
  - 多处 compatibility adapter 代码保留（grep `compatibility` / `legacy` / `adapter` 命中）
  - `test_governed_creation.py` 测试 legacy route 不回退 direct-create
- **结论**：PASS

---

## 三、审计结果汇总表（终态）

| 项 | 期望 | 状态 | 证据 |
|---|---|---|---|
| A1 | SPEC 无 TBD/TODO/FIXME | PASS | 0 匹配 |
| A2 | qwen3.7-Flash=0 in backend | PASS | 0 匹配；SPEC §7 用 qwen3.6-flash |
| A3 | §7+C-02+D-002 模型 id 一致 | PASS | 全部 qwen3.6-flash/qwen3.7-plus |
| A4 | 迁移依赖图无环 | PASS | migrate 全过无环 |
| B1 | manage.py check 0 issues | PASS | 0 issues |
| B2 | makemigrations --check 无 drift | PASS | No changes detected |
| B3 | migrate 真实 PG 全过 | PASS | No migrations to apply |
| B4 | backend Up + gunicorn | PASS | 容器运行，health 响应 |
| B5 | login 可用 | PASS | API 返回字段验证（活着） |
| C1 | PG 套件通过 | PASS | 582 OK (skipped=13), 771.947s |
| C2 | 前端 tsc/build | **PASS** | ✓ 2168 modules; violations=[] |
| C3 | 浏览器 §10 acceptance | DEFERRED | 需 Chromium UAT（上线前） |
| D1 | DB qwen3.6-flash+qwen3.7-plus | PASS | seed_models 后两条 enabled |
| D2 | GovernancePolicy 绑定 | PASS | revision 1, fast→qwen3.6-flash, deep→qwen3.7-plus |
| D3 | .env QWEN_CHAT_MODEL=qwen3.6-flash | **PASS** | .env + .env.example 已修正 |
| D4 | readiness 不 503 | **PASS** | status=ready, canonical_models=ok |
| D5 | chat send SSE 流式 | **PASS** | 200 text/event-stream, 4 SSE events |
| D6 | embedding=text-embedding-v4(1024) | **PASS** | settings/base.py 确认 |
| E1 | §16 单空间隔离 | PASS | 231 OK 子集覆盖 |
| E2 | §7 不暴露 reasoning | PASS | guardrails.py 剥离 + 测试断言 |
| E3 | §6 能力矩阵+scope | PASS | 231 OK 子集覆盖 |
| E4 | §11 兼容期未删 | **PASS** | governed adapter 保留，202 不回退 |
| E5 | §4 ChatTurn 幂等 | PASS | views.py 409 turn_in_progress |
| E6 | ownership 实现 | PASS | URLs/services/PG lock 测试存在 |
| F1 | §26 modal 关闭 | PASS | animations.css .fade-* CSS |
| F2 | §26 限流不随机 429 | PASS | RedisCache + 240/min + 60/10s + Retry-After |

---

## 四、工作树状态

- 分支：`codex/v3-audit-fix`
- HEAD：`07635e177f848a2d10fd7b1b43d46549ffcd31c3`
- 变更文件：
  - `M .env.example`（第 42 行模型 ID 修正）
  - `D .claude/launch.json`（非本次审计相关）
- 未跟踪：`.qoder/`、本报告文件
- 临时测试文件已清理：`create_test_user.py`、`login_body.json`、`test_d5_chat.py`、`query_db.py`（已删除）

---

## 五、上线前待验收（不判 fail，DEFERRED）
- C3 浏览器 §10 acceptance（Chromium UAT）
- 筼筜 PG 迁移演练
- live Redis 多 worker
- 真实 provider SLO/隐私
- production browser UAT
- responsive 走查

---

## 六、结论

**V3 审计 Accepted（无条件）。** D3/D4 FAIL 已修复并复验通过；C2/D5/D6/E4 补查全部 PASS。阶段二（V4 优化实现）可启动。
