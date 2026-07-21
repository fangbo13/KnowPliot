# V3 SPEC 与实现审计交接 Prompt

> 日期：2026-07-19
> 用途：Codex 完成 V3 后，由新对话**独立审计** V3 SPEC+实现是否真完成/成功（核查门）
> 性质：**审计/验收，不改代码**；通过后才进 V4 优化（`post_v3_optimization_implementation_handoff.md`）
> 规范：V3 SPEC 三份文件 + ownership 设计

把下面完整 Prompt 交给下一次对话执行（审计角色，不是实现角色）。

```text
你接手 KnowPilot V3 的**独立审计/验收**工作。Codex 声称 V3 已完成，但你不信任自述——独立核查 V3 SPEC（设计）+ 实现（代码/迁移/测试）是否真完成、真在真实 PostgreSQL 上跑通、SPEC 不变量是否未被削弱。**只审计、出报告，不改代码**（发现问题精确报告，交回修复）。

# 仓库与现状
- 仓库：D:/Github/Onborading-AI（GitHub: github.com/fangbo13/Onborading-AI.git；产品名 KnowPilot）
- 当前分支：codex/ownership-continuity（含 ownership commit 95a4093 + V3 实现）
- 先 `git status` + `git log --oneline -5`：确认 V3 文件**已 commit**（不是 261 未提交；若仍大量未提交→记录为"未持久化"风险，审计降级）
- Docker 服务须运行（db/redis/backend/celery/frontend）；若 backend 起不来→审计直接 fail（migrate 未通）

# 必读（审计依据）
1. docs/specs/2026-07-16-knowpilot-optimization-spec.md（V3 主 SPEC，§1-27，重点 §4/§5/§6/§7/§10/§11/§12/§13/§16/§19-27）
2. docs/specs/2026-07-18-knowpilot-internal-beta-spec-delta.md（delta：C-01..14、迁移依赖图、第6 BUG）
3. docs/specs/2026-07-18-knowpilot-internal-beta-decision-log.md（D-001..006）
4. docs/superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md
5. memory.md、audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md

# 审计清单（逐项出证据：命令 + 输出摘要 + pass/fail）

## A. SPEC 设计审计
- A1 完整性：grep TBD/TODO/待定/未定/placeholder/FIXME——除"pending final review"外应无未定项。
- A2 模型 id：全文搜 `qwen3.7-Flash`——**应为 0**（必须已改 qwen3.6-flash；qwen3.7-Flash 未开通）。fast=qwen3.6-flash、deep=qwen3.7-plus、embedding=text-embedding-v4(1024)。
- A3 一致性：§7 模型策略 + delta C-02 readiness + 决策日志 D-002 三处模型 id 一致；§19-27 与 delta §3 新增章节对应；C-01..14 冲突处理无自相矛盾。
- A4 迁移依赖图（delta §5）：ownership 前置 → thinking snapshot → taxonomy → governed request → locator → idempotency → access/invitation → notifications → retention FK → purge → tombstone → purge guard——顺序无环、无断链。

## B. 实现可启动性（真实 PG，非 SQLite）
- B1 `docker compose exec backend python manage.py check`→0 issues。
- B2 `docker compose exec backend python manage.py makemigrations --check --dry-run`→"No changes detected"（无 drift）。
- B3 `docker compose exec backend python manage.py migrate`→**全过、无报错**（重点查 v3 迁移 0011-0016 的 `%` 转义 + scenario_templates.0006 trigger/ALTER 是否修通；任一崩→fail）。
- B4 backend 容器 `Up` + gunicorn listening（`docker logs onborading-ai-backend-1 | grep "Listening at"`）。
- B5 `curl -s http://127.0.0.1:8000/api/v1/auth/token/`（login）可登录。

## C. 测试（真实 PG + 前端）
- C1 后端 PG 套件：`docker compose exec backend python manage.py test --settings=config.settings.test`→通过（记录 X/Y passed）。注意 SQLite 子集有 8 个环境性失败（repo 根文件缺失 + .env QWEN_CHAT_MODEL 覆盖 qwen-plus），**PG 套件不应有这些**；若 PG 套件 fail，逐个查是否 v3 实现 bug。
- C2 前端：`cd frontend && npm run typecheck && npm run build`→通过；vitest + i18n 通过。
- C3 真实 Chromium 浏览器回归 SPEC §10 acceptance（modal 关闭/reduced-motion、切页限流不再随机 429、role journey user/guest/workspace/scoped governance/platform、create-approval 流、delete-workspace 两阶段+键入确认、思考开关 on/off + 内心独白显隐、中英文查询→对应语言答复、share/source/responsive）。

## D. 模型与 provider 配置
- D1 `docker exec onborading-ai-db-1 psql -U knowpilot -d knowpilot -c "SELECT name,model_id,enabled FROM spaces_modelprofile;"`→有 **qwen3.6-flash**（fast, enabled）+ qwen3.7-plus（deep, enabled）；**无 qwen3.7-Flash**；残留 qwen-plus 应 disabled。
- D2 GovernancePolicy 绑定 fast=qwen3.6-flash + deep=qwen3.7-plus（`SELECT revision,values FROM spaces_governancepolicy ORDER BY revision DESC LIMIT 1;`）。
- D3 .env `QWEN_CHAT_MODEL=qwen3.6-flash`（不是 qwen3.6-flash 之外）。
- D4 readiness 不拦：`resolve_generation_policy(space,'fast').model_id == 'qwen3.6-flash'`（不 503 model_policy_not_ready）。
- D5 实时 chat send（curl，owner）→ SSE 流式返回（不 500/503）；fast 用 qwen3.6-flash 调通 DashScope。
- D6 embedding=text-embedding-v4（1024），query+doc+pgvector 维度一致。

## E. SPEC 不变量未被削弱（抽查）
- E1 §16 单空间检索隔离：跨空间 chunk 不互漏（apps/spaces/tests.py 隔离测试 + 实时 curl 两空间不交叉）。
- E2 §7 不暴露原始 reasoning：grep SSE/日志/测试无 reasoning_content；思考开关 on 时只显安全相位、无 CoT 原文。
- E3 §6 四级能力矩阵 + scope 隔离 + 向上授权否定：curl 跨 scope `/admin/users/`→403（scoped admin）。
- E4 §11 兼容期未删：SSE v1/legacy nav/POST /spaces/ adapter/legacy invitation code 仍在。
- E5 §4 ChatTurn durable + 幂等：重复 client_request_id→409 turn_in_progress（不重复创建）。
- E6 ownership：OwnershipTransfer/Offboarding 实现（commit 95a4093）+ PG 锁回归通过。

## F. 第 6 BUG（§26）修通
- F1 modal：访问码加入弹窗 X/Cancel/Esc/mask 均可关闭；confirmLoading 不拦截；仓库 14 个同模式 Modal 无 transitionend 泄漏。
- F2 导航限流：多 worker 快速切页不再随机 200/429；429 返回 Retry-After；前端不伪装空态。

# 产出：审计报告
格式：
1. **结论**：Accepted / Accepted-with-conditions / Rejected。
2. **逐项证据**：A1-F2 每项 pass/fail + 命令 + 输出摘要。
3. **若 Rejected/Conditional**：精确失败项 + 复现步骤 + 影响 + 建议修法（交回 Codex 修）。
4. **上线前待验收（不判 fail）**：筼筜 PG 迁移演练、live Redis 多 worker、真实 provider SLO/隐私、production browser UAT、responsive 走查。
5. **SPEC 设计遗留**（若有）：如"pending final review"、5 处 qwen3.7-Flash 是否已清零等。
6. commit SHA、分支、工作树状态、审计日期。

# 审计纪律
- **不改任何代码/迁移/.env/SPEC**（只读 + 跑只读命令 + 跑测试）。发现问题→报告，不修。
- 真实 PostgreSQL 证据为准（SQLite 结果不替代；容器内 SQLite 子集的 8 个环境性失败不算 v3 回归）。
- 不信任自述——每个 pass 须有命令+输出证据。
- Accepted 才可进 V4 优化（`docs/operations/post_v3_optimization_implementation_handoff.md`）；Conditional/Rejected→交回 Codex 修后再复审。

# 验收标准（Accepted 的门槛）
- SPEC 设计完整一致（A1-A4 全 pass，qwen3.7-Flash 清零）。
- migrate 真实 PG 全过 + backend 起 + login 可用（B1-B5）。
- PG 测试套件 + 前端 build 通过（C1-C2）；§10 浏览器 acceptance 可复现（C3）。
- 模型配置正确（D1-D6，fast=qwen3.6-flash 调通）。
- 不变量未削弱（E1-E6）。
- §26 两 bug 修通（F1-F2）。
- V3 文件已 commit（非 261 未提交）。

任一不满足→Conditional/Rejected + 精确失败项。
```
