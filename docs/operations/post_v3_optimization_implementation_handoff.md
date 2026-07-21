# Post-V3 优化实现交接 Prompt

> 日期：2026-07-19
> 用途：交新对话（Claude/Codex）实现 post-v3 优化（非 V3）
> 规范：`docs/superpowers/specs/2026-07-19-post-v3-rag-efficiency-kb-versioning-design.md`
> 基线：`fix/v1.74.1-acceptance-bugs` / `82231f5`（排 V3 稳定之后）

把下面完整 Prompt 交给下一次对话执行。

```text
你接手 KnowPilot "后 V3 优化"的实现工作。SPEC 设计已完成（一份文件），现在把 pending 的设计落地为代码+迁移+测试。先通读+思考+写实施计划，再 TDD 实现；不擅自缩小需求、不走捷径。

# 仓库与基线
- 仓库：D:/Github/Onborading-AI（GitHub: github.com/fangbo13/Onborading-AI.git；产品名 KnowPilot）
- 规范基线：fix/v1.74.1-acceptance-bugs / commit 82231f5（含验收 bug 修复 + 爬虫清理）
- 前置：**V3 内测 SPEC 须先稳定**（v3 迁移在真实 PG 跑通、backend 起、§7 思考开关+模型策略实现）——本 post-v3 工作在其之上。若 V3 未稳，先确认 V3 状态再动手。
- 分支：用独立 codex/post-v3-optimization 分支（off V3-stable），不混 V3。

# 必须先完整阅读（权威规范）
1. docs/superpowers/specs/2026-07-19-post-v3-rag-efficiency-kb-versioning-design.md —— 本 post-v3 SPEC（你要实现的）。五部分：
   - **Part 1**（已确认、可实施）：知识库版本化内容编辑 + 差异预览 + 创建流（多格式上传 + 输入框 + `text_content` 规范 MD + `Document.file` nullable + a1 旧版只留文本+元数据、chunks 只留当前版在 live 索引 + 生效期 a+b 立即/排期 + 回滚重算）。
   - **Part 2**（调研性、measure-first gate 未过前不实现）：RAG 效率问题盘点 + 解法路线（规则路由 + semantic cache + adaptive；不上 tool-calling）。**本批不实现 Part 2 的优化代码**，只先加 metrics（`retrieval_result_count`/`query_near_dup`/`cache_hit`/`routing_decision`），跑一周量化 ROI，确认后再建。
   - **Part 3**：思考期"内心独白"显示（reasoning-phase display，复用 `chatStore` 的 `streamPhase`/`SafeProcessingPhase`，无计时、无原始 CoT，SSE `phase` 发渐进安全标签，思考开关 on 时启用）。
   - **Part 4**：中英文区 / AI 答复语言（查询语言自动检测为主 + 用户 `language_preference` 覆盖 + 空间 `default_language`(auto/zh/en) 兜底；system prompt 改"Respond in {resolved_language}"动态指令，不硬编码 en；KB 内容语言不驱动答复语言）。
   - **Part 5**：横切约束。
2. docs/specs/2026-07-16-knowpilot-optimization-spec.md（V3 主 SPEC，§4/§5/§6/§7/§11/§16 本工作须遵守）
3. docs/superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md（Part 1 版本化共享其 governed-action/锁/审计原语，若已实现则复用）
4. SPEC.MD、memory.md、audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md

# 目标
把 post-v3 SPEC 从"仅规范、pending"实现为"代码+迁移+测试+证据"：
- **本批实现**：Part 1（KB 版本化编辑+创建流+diff）、Part 3（思考内心独白显示）、Part 4（中英文区/答复语言）。
- **本批只加 metrics 不建优化**：Part 2 的 retrieval_result_count/query_near_dup/cache_hit/routing_decision 指标（measure-first gate）。
- **不实现 Part 2 的路由/缓存代码**，直到 metrics 量化 ROI。

# 已锁定决策（直接落实，不再评估）
- Part 1：方案 A（内联文本编辑+版本化+diff）；binary 编辑提取文本、原文件保留；旧版 a1（保留 text_content+元数据，chunks 只留当前版在 live 索引、删除旧版 chunks、回滚重算）；生效期 a+b（立即默认+排期）。
- Part 3：无计时数字；不流原始 CoT（SPEC §7/§15.2 红线）；思考开关 on 时启用渐进安全相位。
- Part 4：答复语言解析顺序——查询语言检测（主）→ 用户 language_preference 覆盖 → 空间 default_language 兜底；不硬编码 en。

# 关键依赖与顺序
- **Part 1（KB 版本化）**：相对独立（KB 路径，非 chat），可与 V3 并行；迁移 `Document.text_content`（additive nullable→回填→non-null）+ `Document.file` nullable + version/superseded status；在 V3 迁移序列之后。
- **Part 3（思考内心独白）**：依赖 V3 §7 思考开关 + §5 SSE phase 已实现；在其之上加渐进安全相位标签 + 前端面板。
- **Part 4（中英文区）**：依赖 `apps/rag/prompt_builder.py`（现 `SYSTEM_PROMPT_EN` 硬编码 "Respond in English"，行 19）+ `apps/chat/views.py:1040` `language=getattr(user,"language_preference","en")`；改 system prompt 动态化 + 加查询语言检测 + `KnowledgeSpace.default_language` 字段。
- 迁移依赖图：V3 序列之后 → `Document.text_content`+`file nullable`+superseded status（Part 1）→ `KnowledgeSpace.default_language`（Part 4）。

# 约束（不可违反）
- TDD：先写复现测试（版本切换、diff 不落库、检索只命中当前生效版 chunks【防"干扰"核心不变量】、排期生效、回滚、并发版本竞争；思考 on/off 内心独白显隐、无原始 reasoning 断言；中英文查询→对应语言答复、pref 覆盖、空间兜底）。
- PostgreSQL 真实性：所有条件约束/索引/`select_for_update(of=("self",))`/迁移在真实 PG 验证（`config.settings.test`=PG），SQLite 不能替代（本仓库 v3 迁移已两次暴露 PG-only bug：`%` 转义 + trigger/ALTER；照 `apps/chat/test_pg_session_locking.py` 模式写 PG 回归）。
- §4/§5 固定安全相位、§6 四级能力矩阵+scope 隔离、§7 不暴露原始 reasoning、§11 兼容期不删、§16 单空间检索隔离。
- 数据保留（§10）：旧版 text_content+元数据不随版本切换删除（审计留存）。
- 审计/幂等/并发：版本创建/回滚带 Idempotency-Key + audit + 行锁。
- 兼容期保留：既有 `reindex`/`PATCH 元数据`/`GET chunks`/`POST /spaces/` adapter 等不删（§11）。
- Part 3：**不流原始 reasoning_content**（§7/§15.2 红线）；只发安全相位标签。
- Part 4：**不硬编码 en**；KB 内容语言不驱动答复语言。

# 模型 id 注意（V3 SPEC 域，影响 Part 3）
- 可用模型：fast=**qwen3.6-flash**（已开通）、deep=**qwen3.7-plus**（已开通）；**qwen3.7-Flash 未开通、弃用**。
- 若 V3 SPEC §7/C-02/D-002仍写 qwen3.7-Flash，先改 qwen3.6-flash（否则 readiness 会拦、Part 3 思考开关无可用 fast 模型）。
- embedding = text-embedding-v4（1024 维，env 驱动，不变）。

# 验证
- 后端：先跑改动范围测试，再跑完整套件（`--settings=config.settings.test`=PG）。注意容器内 SQLite 子集有 8 个环境性失败（repo 根文件缺失 + .env QWEN_CHAT_MODEL 覆盖），非回归，勿误判。
- 前端：vitest、tsc --noEmit、i18n（zh/en）、生产 build。
- Ruff（changed files）/Django check/makemigrations --check/git diff --check。
- 真实 Chromium 浏览器回归：KB 内联编辑+diff 预览+版本切换+回滚；思考 on 显内心独白渐进面板、off 不显、无原始 CoT；中英文查询→对应语言答复；reduced-motion。
- Part 1 检索不变量：旧版 chunks 零命中（防干扰）——必须 PG 验证。

# 完成后必须更新
- post-v3 SPEC 各 Part 实现状态（pending → 已实现 + 证据）。
- audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md、memory.md。
- 如有迁移演练，新增不含秘密的审计报告。

# 最终交付格式
1. 实际实现的行为摘要（Part 1/3/4 + Part 2 metrics）。
2. 变更文件 + 迁移列表（按依赖图）。
3. 每条锁定不变量/决策的验证证据。
4. 完整测试结果与真实数量（PG + 前端 + 浏览器）。
5. 未完成的现场门禁，明确标 pending（Part 2 优化代码待 measure-first gate；筼筜 PG/live provider/browser UAT）。
6. commit SHA、分支名、工作树状态。
7. 下一位验收人员可复制执行的命令（不含 token/秘密）。

不要因为既有 `reindex`/`PATCH`/`POST /spaces/` 接口存在就判定需求已完成。验收标准：post-v3 SPEC Part 1/3/4 的每条 acceptance 在真实 PostgreSQL + 浏览器下可复现通过，兼容期回退未被删除、SPEC 不变量未被削弱；Part 2 优化代码未实现（measure-first gate 未过）。
```
