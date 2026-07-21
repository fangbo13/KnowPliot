# V3 实现完成与修通交接 Prompt

> 日期：2026-07-19
> 用途：交新对话（Claude/Codex）修通 + 完成 V3 内测 SPEC 实现（post-v3 的前置）
> 规范：V3 SPEC 三份文件（主 SPEC v3 + delta + 决策日志）
> 现状：V3 实现大量在 `codex/ownership-continuity` 工作树（261 未提交文件），但**真实 PG 上 migrate 崩、backend 起不来**

把下面完整 Prompt 交给下一次对话执行。

```text
你接手 KnowPilot V3 内测 SPEC 的"完成 + 修通"工作。V3 SPEC 设计已完成（3 份文件），实现已大量在 codex/ownership-continuity 工作树（261 未提交文件）但**在真实 PostgreSQL 上 migrate 崩、backend 起不来**。你的任务：修通 PG 迁移 + 补全实现 + 验证。先通读+核查现状，再 TDD 修。

# 仓库与现状
- 仓库：D:/Github/Onborading-AI（GitHub: github.com/fangbo13/Onborading-AI.git；产品名 KnowPilot）
- 当前分支：codex/ownership-continuity（含 ownership 实现 commit 95a4093 + 261 未提交 v3 文件）
- 状态：backend 在真实 PG 上 migrate 崩，起不来；v3 代码大量未提交（丢失风险高）
- ⚠️ 开始前先 `git status` + **建议先 commit 当前 261 文件为 WIP**（避免修复中丢失）

# 必须先完整阅读（权威 V3 SPEC）
1. docs/specs/2026-07-16-knowpilot-optimization-spec.md（V3 主 SPEC，§1-27：§4 ChatTurn/SSE、§5 SSE v2、§6 能力矩阵、§7 模型策略、§10 验收、§11 兼容、§12 API、§13 迁移、§14 交互、§15 性能/隐私、§19-27 新增章节含 §20 GovernedActionRequest 公共原语、§21 create-approval、§22 deletion、§23 taxonomy、§24 access/invitation/notification、§25 platform Knowledge/Templates、§26 第6 BUG modal/throttle、§27 证据矩阵）
2. docs/specs/2026-07-18-knowpilot-internal-beta-spec-delta.md（变更 delta：C-01..14 冲突处理、迁移依赖图、第6 BUG delta）
3. docs/specs/2026-07-18-knowpilot-internal-beta-decision-log.md（D-001..006 已决）
4. docs/superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md（ownership 前置，§20 共享其原语）
5. memory.md、audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md

# 已知阻塞（先修，逐个迭代）
1. **v3 迁移 `%` 转义（0011/0012/0014/0016）**：PL/pgSQL 里有 `RAISE EXCEPTION '...%'` + `var table%ROWTYPE`。Codex 之前用 `%%` 转义。
   - ⚠️ **验证 `%%` 是否有效**：psycopg3 配置 `collapse_double_percent=False`（见 traceback `_split_query(..., collapse_double_percent=False)`），可能**不把 `%%` 当转义 `%`**。
   - 跑 `docker compose exec backend python manage.py migrate` 看最新错误：若仍崩在 0011 `%'` → `%%` 无效，**正确修法是避免 `%`**：`RAISE EXCEPTION '...%' ` → `RAISE EXCEPTION '...' || var::text`（拼接，无 `%`）；`var table%ROWTYPE` → `var record`（无 `%ROWTYPE`）。全文搜 v3 迁移 raw SQL 的 `%` 一律消除。
   - 若已过 0011（崩在更后面）→ 跳到下一条。
2. **scenario_templates.0006 "cannot ALTER TABLE ... pending trigger events"**：迁移内数据操作触发 deferred trigger 后又 ALTER 同表，顺序冲突。修：拆开（先 ALTER 后数据，或分两个迁移），或数据操作前 `SET CONSTRAINTS IMMEDIATE` / 临时禁用 trigger。
3. **可能还有更多 PG-only bug**：每跑一次 migrate 可能暴露新的（trigger/ALTER/条件约束/锁序/`of=("self")`）。逐个修到 migrate 全过。
4. **模型 id qwen3.7-Flash→qwen3.6-flash**：V3 SPEC §7（行 254/401/402/416）+ delta C-02 + 决策日志 D-002 + readiness 实现（apps/core/readiness.py 或 generation_policy 校验）仍写 qwen3.7-Flash；**qwen3.7-Flash 未开通，改 qwen3.6-flash**（fast 档）。deep=qwen3.7-plus 不变。seed_models.py + .env 已对齐（ZCode 改过），backend 起来后重跑 seed_models 会建 qwen3.6-flash profile + 重绑。

# 目标
1. 修通 v3 迁移 → `docker compose exec backend python manage.py migrate`（真实 PG）全过，无报错。
2. backend 起来（gunicorn listening）。
3. 补全 v3 实现（按 SPEC §19-27 + §7 模型策略 + §26 第6 BUG），凡 pending 的补到可验证。
4. 重跑 `seed_models`（创建 qwen3.6-flash profile + 重绑 GovernancePolicy fast=qwen3.6-flash/deep=qwen3.7-plus + 禁用残留 qwen-plus）。
5. 验证：跑 v3 PG 测试套件 + 前端 tsc/build + 浏览器回归 SPEC §10 acceptance。

# 约束
- TDD：每修一个 bug 先写复现测试（PG）。
- PostgreSQL 真实性：所有迁移/约束/锁在真实 PG 验证（`config.settings.test`=PG），SQLite 不能替代（已多次暴露 PG-only bug：chat FOR UPDATE + v3 `%` + trigger/ALTER）。
- §4/§5/§6/§7/§11/§16 不变量不破；§7 不暴露原始 reasoning；§11 兼容期不删（SSE v1/legacy nav/POST /spaces/ adapter/legacy invitation code）。
- §20 GovernedActionRequest 原语与 ownership 共享（lock/impact/idempotency/audit/outbox），`select_for_update(of=("self",))`。
- 业务状态+audit+outbox 同事务提交；`on_commit` 只唤醒 dispatcher。
- 不把 token/密钥/人事原因/provider 信息写日志/测试/提交。
- 不宣称筼筜/生产通过，除非实际完成授权现场验证。

# 迁移依赖图（delta §5，不可打乱）
ownership 前置 → owner partial unique/deferred mirror trigger + test-principal metadata → independent-thinking snapshot → immutable template revision → controlled taxonomy/daily usage → revisioned creation policy → governed request + typed details → single-namespace locator → per-operation idempotency → hashed access code/targeted invitation → actionable notifications → 逐应用 retention FK → purge job/checkpoints → workspace tombstone → 最终 purge guard。

# 第 6 BUG（§26，两条独立）
- modal：transitionName="fade" 缺 CSS/deadline + confirmLoading 拦截关闭 → 修（完整 default motion 或 CSS+finite deadline；idle/pending 均可关；仓库 14 个同模式 Modal 进回归）。
- 导航限流：全局 30/min + 2-worker LocMemCache 不同步 → 换 shared multi-worker limiter（240/min/user、60/10s burst；429 返回 Retry-After；前端不伪装空态；coalescing/abort/sequence guard）。

# 完成后必须更新
- V3 主 SPEC §17 gate / delta / 决策日志状态行（pending → 已实现 + 证据）。
- audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md、memory.md。
- **commit 全部 v3 文件**（避免丢失）。

# 最终交付格式
1. 修通的迁移列表 + 每个 bug 的根因+修法。
2. v3 实现的行为摘要（§19-27 + §7 + §26）。
3. 变更文件 + 迁移列表（按依赖图）。
4. 每条锁定不变量/决策的验证证据。
5. 完整测试结果与真实数量（PG + 前端 + 浏览器）。
6. 未完成的现场门禁，明确标 pending（筼筜 PG 迁移演练、live Redis/provider、production browser UAT、data-hygiene）。
7. commit SHA、分支名、工作树状态。
8. 下一位验收人员可复制执行的命令（不含 token/秘密）。

不要因为某个旧接口存在就判定需求已完成。验收标准：v3 SPEC §10 的每条 acceptance 在真实 PostgreSQL + 浏览器下可复现通过，backend 稳定启动，兼容期回退未被删除、SPEC 不变量未被削弱。
```
