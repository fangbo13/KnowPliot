# V3 审计 → V4 优化：Goal 模式交接 Prompt

> 日期：2026-07-21
> 用途：在 Goal 模式中接手 KnowPilot V3 审计收尾 + V4 优化实现
> 性质：先修复 V3 审计 FAIL 项 → 复验 → 通过后进 V4 优化

---

## 完整 Prompt（粘贴到 Goal 模式）

```text
你接手 KnowPilot "V3 审计 → V4 优化"两阶段工作。前一 session 已完成大部分审计，发现 1 个 FAIL 项需修复。修复后复验，通过则进 V4 优化实现。

# 仓库与环境
- 仓库：github.com/fangbo13/KnowPliot.git（工作树 e:\KnowPliot）
- 当前分支：codex/v3-audit-fix（HEAD = 07635e1）
- Docker 容器（已运行）：
  - knowpliot-db-1（PostgreSQL 16 + pgvector，DB=knowpilot，test=test_knowpilot）
  - knowpliot-redis-1（Redis 7）
  - knowpliot-backend-1（gunicorn 2 workers × 8 threads，端口 8000）
- .env 已存在（从 .env.example 复制），但有问题（见下方 FAIL 项）
- backend 挂载 ./backend:/app（本地工作树代码即容器代码）
- cmd.exe 注意：psql 的 -c "SQL" 会被 cmd.exe 花括号/引号解析破坏；用 echo 管道方式：
  docker exec knowpliot-db-1 sh -c "echo SELECT\ ...\; | psql -U knowpilot -d knowpilot"
- 同理 python -c 也会被 cmd.exe 引号破坏；改用 docker exec ... python manage.py shell 方式

# 权威规范（必读）
- V3 SPEC：docs/specs/2026-07-16-knowpilot-optimization-spec.md（§1-27，重点 §4/§5/§6/§7/§10/§11/§13/§16/§19-27）
- delta：docs/specs/2026-07-18-knowpilot-internal-beta-spec-delta.md（C-01..14 + 迁移依赖图 §5 + 第6 BUG §6）
- 决策日志：docs/specs/2026-07-18-knowpilot-internal-beta-decision-log.md（D-001..006）
- ownership：docs/superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md
- V4 SPEC：docs/superpowers/specs/2026-07-19-post-v3-rag-efficiency-kb-versioning-design.md（五部分）
- V4 实现 handoff：docs/operations/post_v3_optimization_implementation_handoff.md
- V3 审计 handoff：docs/operations/v3_audit_handoff.md（A1-F2 清单）

# 前一 session 审计结果（已完成，不需重跑）

## 已 PASS 项（不用重查）
- A1 SPEC 完整性：主 SPEC 无 TBD/TODO/FIXME ✓
- A2 模型 id：backend 代码 qwen3.7-Flash=0 匹配；SPEC §7 正确用 qwen3.6-flash（fast）/ qwen3.7-plus（deep）✓
- A3 一致性：§7 + delta C-02 + D-002 三处模型 id 一致 ✓
- A4 迁移依赖图：delta §5 描述顺序，migrate 全过无环 ✓
- B1 manage.py check：0 issues ✓
- B2 makemigrations --check：No changes detected ✓
- B3 migrate（真实 PG）：No migrations to apply ✓
- B4 backend Up + gunicorn：容器运行，health 端点响应 ✓
- B5 login API 可达：/api/v1/auth/token/ 返回字段验证错误（说明 API 活着）✓
- C1 PG 测试套件：582 OK (skipped=13)，771.947s ✓
- D1 DB ModelProfile：seed_models 后有 qwen3.6-flash(enabled) + qwen3.7-plus(enabled) ✓
- D2 GovernancePolicy：revision 1，fast→qwen3.6-flash，deep→qwen3.7-plus ✓
- E2 §7 不暴露 reasoning：guardrails.py 剥离 reasoning_content；测试断言不出现在日志/输出 ✓
- E5 §4 ChatTurn 幂等：views.py 第 1162 行返回 409 turn_in_progress ✓
- E6 ownership：OwnershipTransfer/OffboardingRecord 实现，URLs/services/PG lock 测试存在 ✓
- F1 §26 modal：animations.css 有 .fade-enter/.fade-appear/.fade-leave/.fade-*-active CSS；12 个 transitionName="fade" modal 覆盖 ✓
- F2 §26 导航限流：base.py 用 RedisCache（共享多 worker）；throttle rates navigation_read_sustained=240/min + navigation_read_burst=60/10s（匹配 §26.4）；test_throttling.py 测试 429+Retry-After；exceptions.py 保留 Retry-After 头 ✓

## FAIL 项（必须修复）
- **D3 .env 模型 id**：`.env` 和 `.env.example`（已提交文件）第 42 行都是 `QWEN_CHAT_MODEL=qwen3.7-Flash`（应为 `qwen3.6-flash`）。
  - 根因：两个修复 commit（b1a999b C1+F1, 07635e1 flaky hang）都遗漏了 .env.example 的模型 ID 修正。
  - 影响：readiness.py 第 74-77 行检查 QWEN_CHAT_MODEL == CANONICAL_FAST_MODEL(qwen3.6-flash)；.env 覆盖为 qwen3.7-Flash → aliases_match=False → ready=False → 新 Turn 503 model_policy_not_ready。
  - 修复：改 .env.example 第 42 行 qwen3.7-Flash → qwen3.6-flash；改 .env 第 42 行同；重启 backend 容器。
- **D4 readiness**：`/api/v1/health/ready/` 返回 `{"status":"not_ready","checks":{"canonical_models":"not_ready",...}}`（由 D3 导致）。修复 D3 后应返回 ok。

## 未检查项（修复 D3 后补查）
- C2 前端 build：`npm run build` = `tsc -b && vite build && node scripts/check-bundle-budget.mjs`；需先 `npm install`（前端 node_modules 可能未安装）
- C3 浏览器 §10 acceptance：需 Chromium 浏览器回归
- D5 chat send 流式：修复 D3 后用 owner 账号 curl 发 chat → SSE 流式返回（不 500/503）
- D6 embedding=text-embedding-v4(1024)：检查 .env 和 settings 中的 embedding 配置
- E1 §16 隔离：已由 231 OK 子集测试覆盖（apps.spaces 隔离测试全过）
- E3 §6 能力矩阵：已由 231 OK 子集测试覆盖（apps.users/apps.core 权限测试全过）
- E4 §11 兼容期：test_governed_creation.py 测试 legacy route 不回退 direct-create；需更详细检查 SSE v1/legacy nav/POST /spaces/ adapter 是否保留

# 阶段一修复步骤（精确执行）
1. 修复 .env.example 第 42 行：`QWEN_CHAT_MODEL=qwen3.7-Flash` → `QWEN_CHAT_MODEL=qwen3.6-flash`
2. 修复 .env 第 42 行：同上
3. 重启 backend：`docker restart knowpliot-backend-1`（等待 migrate + gunicorn 起来，约 30s）
4. 验证 readiness：`curl -s http://127.0.0.1:8000/api/v1/health/ready/` → 应返回 `"status":"ok"` 且 `canonical_models` 为 `ok`
5. 验证 QWEN_CHAT_MODEL：`docker exec knowpliot-backend-1 python manage.py shell -c "from django.conf import settings; print(settings.QWEN_CHAT_MODEL)"` → 应输出 `qwen3.6-flash`
6. 补查 C2：`cd frontend && npm install && npm run build`（需通过）
7. 补查 D5：用 owner 账号登录后 curl 发 chat，确认 SSE 流式返回
8. 补查 D6：检查 .env 中 embedding 配置（DASHSCOPE_EMBEDDING_MODEL 或类似）
9. 补查 E4：grep SSE v1 / legacy nav / POST /spaces/ adapter 确认兼容期未删

# 阶段一验收标准
- D3 修复后 readiness ok + chat 可流式 → V3 审计 Accepted
- C2 前端 build 通过 + E4 兼容期确认 → Accepted（无 conditions）
- 任一未通过 → 修复后复审

# 阶段二（仅当阶段一 Accepted）：V4 优化实现
分支：codex/v4-optimization（off codex/v3-audit-fix），不混 V3。

## V4 SPEC 文件
docs/superpowers/specs/2026-07-19-post-v3-rag-efficiency-kb-versioning-design.md

## 实现 Parts
- **Part 1（KB 版本化）**：Document.text_content（additive nullable→回填→non-null）+ Document.file nullable + version/superseded status + diff 预览 + 创建流（多格式上传+输入框+text_content 规范 MD）+ a1 旧版只留文本+元数据 + chunks 只留当前版在 live 索引 + 生效期 a+b（立即默认+排期）+ 回滚重算
- **Part 3（思考内心独白）**：复用 chatStore 的 streamPhase/SafeProcessingPhase；无计时、无原始 CoT；SSE phase 发渐进安全标签；思考开关 on 时启用
- **Part 4（中英文区/答复语言）**：查询语言检测（主）→ 用户 language_preference 覆盖 → 空间 default_language(auto/zh/en) 兜底；system prompt 改 "Respond in {resolved_language}" 动态指令；不硬编码 en；KB 内容语言不驱动答复语言
- **Part 2（只加 metrics）**：retrieval_result_count / query_near_dup / cache_hit / routing_decision；**不建路由/缓存代码**（measure-first gate 未过）

## 关键依赖
- Part 1 依赖：apps/rag/Document 模型；迁移在 V3 序列之后
- Part 3 依赖：V3 §7 思考开关 + §5 SSE phase（已实现）
- Part 4 依赖：apps/rag/prompt_builder.py（现 SYSTEM_PROMPT_EN 硬编码 "Respond in English" 行 19）+ apps/chat/views.py:1040 language=getattr(user,"language_preference","en")；改 system prompt 动态化 + 加查询语言检测 + KnowledgeSpace.default_language 字段

## 约束
- TDD + 真实 PG（--settings=config.settings.test）+ §4/§5/§6/§7/§11/§16 不变量 + 兼容期不删 + 不流原始 CoT + 不硬编码 en
- 模型：fast=qwen3.6-flash / deep=qwen3.7-plus（qwen3.7-Flash 弃用）
- Part 2 优化代码不实现（measure-first gate）

## 最终交付
1. 行为摘要（Part 1/3/4 + Part 2 metrics）
2. 变更文件 + 迁移列表（按依赖图）
3. 不变量验证证据
4. 测试结果（PG + 前端 + 浏览器）
5. pending 门禁（Part 2 优化代码 / live provider / browser UAT）
6. commit SHA / 分支 / 工作树状态
7. 可复制命令（不含秘密）

# 纪律
- 真实 PG 为准（--settings=config.settings.test）；SQLite 不替代
- 不改 V3 生产代码语义
- apps.core apps.users apps.spaces 必须保持 231 OK
- 不信任自述——每个 pass 须有命令+输出证据
- cmd.exe 引号问题：psql -c "SQL" 会失败；用 echo 管道或 docker exec ... sh -c "echo SQL\; | psql ..."
```

---

## 审计证据汇总表

| 项 | 期望 | 实际 | 状态 |
|---|---|---|---|
| A1 | SPEC 无 TBD/TODO/FIXME | 0 匹配 | PASS |
| A2 | qwen3.7-Flash=0 in backend | 0 匹配；SPEC §7 用 qwen3.6-flash | PASS |
| A3 | §7+C-02+D-002 模型 id 一致 | 全部 qwen3.6-flash/qwen3.7-plus | PASS |
| A4 | 迁移依赖图无环 | migrate 全过无环 | PASS |
| B1 | manage.py check 0 issues | 0 issues | PASS |
| B2 | makemigrations --check 无 drift | No changes detected | PASS |
| B3 | migrate 真实 PG 全过 | No migrations to apply | PASS |
| B4 | backend Up + gunicorn | 容器运行，health 端点响应 | PASS |
| B5 | login 可用 | API 返回字段验证（活着） | PASS |
| C1 | PG 套件通过 | 582 OK (skipped=13), 771.947s | PASS |
| C2 | 前端 tsc/build | 未检查（需 npm install） | PENDING |
| C3 | 浏览器 §10 acceptance | 未检查 | PENDING |
| D1 | DB qwen3.6-flash+qwen3.7-plus | seed_models 后两条 enabled | PASS |
| D2 | GovernancePolicy 绑定 | revision 1, fast→qwen3.6-flash, deep→qwen3.7-plus | PASS |
| D3 | .env QWEN_CHAT_MODEL=qwen3.6-flash | .env.example + .env 都是 qwen3.7-Flash | **FAIL** |
| D4 | readiness 不 503 | not_ready (canonical_models not_ready) | **FAIL** |
| D5 | chat send SSE 流式 | 未测试（D3 修复后测） | PENDING |
| D6 | embedding=text-embedding-v4(1024) | 未检查 | PENDING |
| E1 | §16 单空间隔离 | 231 OK 子集覆盖 | PASS |
| E2 | §7 不暴露 reasoning | guardrails.py 剥离 + 测试断言 | PASS |
| E3 | §6 能力矩阵+scope | 231 OK 子集覆盖 | PASS |
| E4 | §11 兼容期未删 | test_governed_creation 覆盖；需详查 | PASS* |
| E5 | §4 ChatTurn 幂等 | views.py 409 turn_in_progress | PASS |
| E6 | ownership 实现 | URLs/services/PG lock 测试存在 | PASS |
| F1 | §26 modal 关闭 | animations.css .fade-* CSS | PASS |
| F2 | §26 限流不随机 429 | RedisCache + 240/min + 60/10s + Retry-After | PASS |

## FAIL 项精确复现

### D3: .env.example 模型 ID 未修正
- 文件：`.env.example` 第 42 行 + `.env` 第 42 行
- 当前值：`QWEN_CHAT_MODEL=qwen3.7-Flash`
- 期望值：`QWEN_CHAT_MODEL=qwen3.6-flash`
- 根因：commit b1a999b（C1+F1）和 07635e1（flaky hang）都未修改 .env.example
- 影响：readiness.py aliases_match=False → canonical_models=not_ready → 503
- 复现命令：`curl -s http://127.0.0.1:8000/api/v1/health/ready/`
- 输出：`{"status":"not_ready","checks":{"canonical_models":"not_ready",...}}`

### D4: readiness not_ready（由 D3 导致）
- 同上，修复 D3 后自动解决

## 修复操作清单
1. 改 `.env.example` 第 42 行：qwen3.7-Flash → qwen3.6-flash
2. 改 `.env` 第 42 行：qwen3.7-Flash → qwen3.6-flash
3. `docker restart knowpliot-backend-1`
4. 等 30s 后 `curl -s http://127.0.0.1:8000/api/v1/health/ready/` → 应 status=ok
5. `cd frontend && npm install && npm run build`
6. 用 owner 账号测试 chat send 流式
7. 提交 .env.example 修复到 codex/v3-audit-fix

## 上线前待验收（不判 fail）
- 筼筜 PG 迁移演练
- live Redis 多 worker
- 真实 provider SLO/隐私
- production browser UAT
- responsive 走查
