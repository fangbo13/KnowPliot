# KnowPilot V3 独立验收审计报告

> 审计日期：2026-07-20（Asia/Shanghai）
> 审计角色：独立审计/验收（非实现角色），只读，不改代码/迁移/.env/SPEC
> 审计依据：`docs/operations/v3_audit_handoff.md` A1–F2 清单 + V3 三份 SPEC + ownership 设计
> 仓库：`D:/KnowPliot`（remote `github.com/fangbo13/KnowPliot.git`）—— 注：任务写 `D:/Github/Onborading-AI`/`Onborading-AI.git`/分支 `codex/ownership-continuity` 在本机均不存在；内容全在 `D:/KnowPliot` 的 `codex/v4-optimization` 分支（见 §"仓库/分支核对"）
> 分支：`codex/v4-optimization` @ `097d3c225e05b47abdf31670f87bf699dde468ef`
> 工作树：clean（无未提交；V3 已持久化，"261 未提交"风险已解除）
> Docker 栈：`knowpliot-{db,redis,backend,celery-worker,frontend}` 全 Up（db/redis healthy），project dir `D:\KnowPliot`，运行栈 = HEAD（含 v4-part4 additive）

## 0. 结论

**Accepted-with-conditions（有条件通过）。**

V3 的核心在真实 PostgreSQL 上跑通：迁移全 applied、backend 稳定服务、真实 chat send SSE 流式经 `qwen3.6-flash` 调通 DashScope、模型配置正确（fast=qwen3.6-flash/deep=qwen3.7-plus/embedding=text-embedding-v4(1024)）、SPEC 不变量 §4/§6/§7/§11/§16 + ownership 未削弱、§26 限流（Redis shared + Retry-After）已修。

但有 **2 个阻塞条件**未清零，不构成 clean Accepted：

1. **C1（迁移契约测试残留）**：PG 全量套件 `Ran 581 tests, FAILED (errors=4, skipped=13)`。4 个 error 全在迁移契约测试（`workspace_retention_migration` ×3、`v3_template_migration` ×1），根因是 `knowledge/migrations/0011 mark_registry_ready` 的 purge registry 校验 + `django_content_type (admin,logentry)` 在 `serialized_rollback` 下的 PG 严格唯一冲突。这正好是 v1.74.2 修复链（`fc8be81`→`bf9c2bb`"clear PG test-suite cascade migration-contract"）在清的级联——清了 stage_a/c、0016 purge guard、deferred-trigger，但**残留 4 个**。
2. **F1（§26 modal 修复未全覆盖）**：复现文件 `SpaceSwitcher.tsx` 已用 `getModalTransitionName()`（默认 motion / reduced-motion 禁过渡）修通，共享 `ConfirmDialog` 原语也已用默认 motion；但 **12 个业务 Modal 仍硬编码 `transitionName="fade"`**（AdminTemplatesPage×6、AdminCodesPage×2 含访问码弹窗、SpaceManagementPage×2、AdminBusinessLines×1、AdminAnnouncements×1），全仓无 `.fade-enter/.fade-leave/.fade-appear` CSS、无 `deadline`——按 §26.2 根因分析（spec:2598-2604）这些 Modal 的 transitionend 泄漏仍未消除。§26 契约（spec:2606）要求 14 个同模式 Modal 全部进回归。且无 Built-Chromium 证据（spec:2620-2623 强制要求）。

另 2 个非阻塞观察：C2 host 构建受平台不匹配阻塞（Linux node_modules on Windows host，非源码缺陷）；C3 无 playwright，§10 浏器 acceptance 未复现（按 handoff 列为上线前待验收）。

**按既定门禁：Conditional → 停下报告，不进阶段二（V4 优化），交回修 V3 后复审。**

---

## 仓库/分支核对（与任务描述的差异）

| 任务描述 | 本机实际 |
|---|---|
| 仓库 `D:/Github/Onborading-AI`（`Onborading-AI.git`） | 不存在；唯一仓库 `D:/KnowPliot`（`KnowPliot.git`，同 owner fangbo13，KnowPilot=Onborading-AI 现名） |
| 分支 `codex/ownership-continuity` | 本机 + origin 均无此分支；V3 工作在 `codex/v4-optimization`（含 ownership `95a4093` + V3 实现 + v4-part4 additive） |
| V3 文件 261 未提交 | 工作树 clean，V3 已全部 commit |

审计在 `codex/v4-optimization` @ HEAD 进行。v4-part4（`097d3c2`，双语答复语言 + migration `0017_default_language`）是 additive：未改 V3 SPEC 文档、未削 §4/§5/§6/§7/§11/§16 不变量；A1-A4 结果与 V3-stable 一致。HEAD 含 v4-part4 的 migration 0017（已 applied）。

V3-stable 候选 = `bf9c2bb`（最后一个 v1.74.2 修复，v4-part4 之前）。

---

## A. SPEC 设计审计

- **A1 完整性**：`rg "TBD|FIXME|待定|未定|placeholder"` 三份 spec → 唯一匹配 `spec.md:1528` 的 "pending final review" gate 行（handoff 明确豁免）。`rg "TODO"` 主 spec → 0。**PASS**。
- **A2 模型 id**：`rg "qwen3.7-Flash"` backend 代码 → **0**（真清零）；docs 10 处但**全是禁止/不可用语境**（"未开通/不得作为可用模型/unavailable"）或 handoff 自述。literal "grep=0" 未满足，但语义正确、实现无缺陷。**PASS（附注：spec 文档保留禁止性提及，符合规范写法）**。
- **A3 一致性**：§7（spec:401-418）fast=qwen3.6-flash/deep=qwen3.7-plus；delta C-02（spec-delta:73-76）一致；决策日志 D-002（decision-log:13-25）一致。§19-27 ↔ delta §3 九项逐条对应（§20 governed action / §21 create-approval / §22 deletion / §23 taxonomy / §24 access-invitation / §25 platform / §26 bugs / §27 evidence matrix）。C-01..C-14 交叉核对无自相矛盾（C-04 vs C-07 不同表不同流；C-06 vs C-14 deletion/SET_NULL 互补；C-03/C-08/C-11 单一 ownership 写入路径一致）。**PASS**。
- **A4 迁移依赖图**：delta §5（spec-delta:170-177）15 节点线性链，12 个 anchor 顺序全保留、无环、无断链。**PASS**（附注：spec 图是 12-anchor 的严格超集，多 3 个中间节点——owner mirror partial unique/deferred trigger+test-principal metadata、immutable template revision、revisioned creation policy；不构成偏差）。

## B. 可启动性（真实 PG）

- **B1** `docker exec knowpliot-backend-1 python manage.py check` → `System check identified no issues (0 silenced)`（仅 SECRET_KEY 28 字节 RuntimeWarning，非 check 错误）。**PASS**。
- **B2** `makemigrations --check --dry-run` → `No changes detected`（无 drift）。**PASS**。
- **B3** `migrate` → `No migrations to apply`（clean no-op，无 `%` 崩溃）。**PASS**。
- **B4** backend 容器 `Up 12h`，gunicorn 日志 "Booting worker"/"Control socket listening"，`:8000` 服务（`/`→404、`/api/v1/auth/token/` GET→405 路由在）。**PASS**。
- **B5** token 端点可达；shell mint JWT for `audit_admin`（token_len=277）成功 → auth 机制可用。password-based login 未跑（无文档化测试密码）。**PASS（附注）**。

迁移 applied 状态（`showmigrations` 真实 PG）：全部 `[X]` 无 pending，含 V3 关键 spaces 0009-0016（ownership stage_a/c、invariant_hardening、internal_beta_taxonomy、governed_workspace_requests、workspace_join_v2、deletion stage_a/c）、scenario_templates 0006/0007、users 0004/0005、0017（v4-part4）。

迁移 `%` bug 核验（rg + `grep -cF`）：spaces 0011-0016 六文件 `%%`/`ROWTYPE`/`%` 全 0；全仓 `%%`/`ROWTYPE` 0。

## C. 测试

- **C1 PG 套件**：`manage.py test --settings=config.settings.test --noinput` → `Ran 581 tests in 634.6s, FAILED (errors=4, skipped=13)`。564 passed / 4 errored / 13 skipped。**CONDITIONAL**（详见 §"失败项复现"）。
- **C2 前端**：typecheck `node ./node_modules/typescript/bin/tsc --noEmit` exit 0（源码 type-clean）✓；`tsc -b` exit 0 ✓；**vite build 在 Linux 容器（node:20）内成功** `✓ built in 48.86s`（完整 dist/assets 清单：index/MessageBubble/KnowledgeBasePage/AdminTemplatesPage 等）✓；i18n `All i18n keys present (90 source files)` ✓。vitest `350 tests, 8 failed, 342 passed` —— 8 个 failure 全在 `src/utils/__tests__/dateGroup.test.ts`，**时区相关**（测试硬编码 Asia/Shanghai UTC+8 期望，但 `node:20` 容器默认 UTC：`2025-12-31T16:00Z` 期望 `2026-01`（UTC+8=元旦）却收到 `2025-12`（UTC））；以 `TZ=Asia/Shanghai` 重跑复核中。host 上 vite/vitest 失败仅因 node_modules 装的是 Linux 平台 rollup native binding（host Windows 平台不匹配，非源码）。**PASS（build+typecheck+i18n 确证；vitest 8 个为 TZ 环境不匹配，待 TZ 复核）**。
- **C3 浏览器 §10**：无 playwright/cypress（`tests/*.mjs` 为 node UAT 脚本，无浏览器自动化框架）。§10 acceptance（modal 关闭/reduced-motion、切页限流、role journey、create-approval/delete 两阶段、思考开关、中英文答复、share/source/responsive）未在真实 Chromium 复现。按 handoff 列为**上线前待验收**（不判 fail）。C3 浏器级用 curl 做了部分（见 E3/D5）。

## D. 模型与 provider 配置

- **D1** `SELECT name,model_id,enabled FROM spaces_modelprofile` → `qwen3.6-flash`(enabled) + `qwen3.7-plus`(enabled)，无 qwen3.7-Flash，无残留 qwen-plus。**PASS**。
- **D2** `governancepolicy revision=1` JOIN modelprofile → fast_model=qwen3.6-flash(enabled) / deep_model=qwen3.7-plus(enabled)。**PASS**。
- **D3** backend 容器 env `QWEN_CHAT_MODEL=qwen3.6-flash`（DASHSCOPE_API_KEY 已 set，不打印值）。**PASS**。
- **D4** readiness 不拦：D5 chat send 返回 HTTP 200（非 503 model_policy_not_ready）。**PASS**。
- **D5** 实时 chat send（`POST /api/v1/chat/sessions/e929cdc3.../send/`，audit_admin，fast，no thinking）→ `HTTP 200`，0.9s，SSE 流式 `quality`→`token`→`citations`→`done`，`done` event 含 `"model":"qwen3.6-flash"` → fast=qwen3.6-flash 调通 DashScope。答案为 RAG 安全兜底（`retrieval_mode:hybrid, latency 281ms, results=0` → Audit Test Space 无文档 → "insufficient info, contact HR"，无幻觉）。SSE 无 `reasoning_content`。**PASS**。
- **D6** `knowledge_documentchunk.embedding_vector` = `vector(1024)`；env `QWEN_EMBEDDING_MODEL=text-embedding-v4`。**PASS**。

## E. SPEC 不变量未削弱

- **E1 §16 单空间隔离**：DB 仅 1 个 space（Audit Test Space，无知识文档），运行时跨空间 curl 不可行；隔离由 C1 的 `apps/spaces` 隔离测试 + retrieval `results=0`（不跨空间取数）佐证。**PASS（运行时受限，依赖 C1 隔离测试）**。
- **E2 §7 不暴露原始 reasoning**：`stream_events.py:30` `_FORBIDDEN_KEYS = {chain_of_thought, raw_reasoning, reasoning_content, ...}`（剥离列表）；`guardrails.py:140` 检测剥离；`test_chat_generation_policy.py:250` `assertNotIn("reasoning_content", logs)`。D5 SSE 实测无 `reasoning_content`。**PASS**。
- **E3 §6 能力矩阵 + scope**：`audit_user`→`/api/v1/admin/users/`=**403 permission_denied**；`audit_user`→`/api/v1/auth/me/`=200；`audit_admin`(superuser)→`/api/v1/admin/users/`=200。向上授权否定生效。**PASS**。
- **E4 §11 兼容期未删**：`permissions.py:86/92` "Legacy role labels retained for compatibility"；`views.py:130/187/606` "compatibility route retained / empty-body shape / compatibility period"。legacy 路由/SSE v1/invitation 未删。**PASS**。
- **E5 §4 ChatTurn durable + 幂等**：D5 fresh `client_request_id`→200 创建新 turn；日志历史 `/api/v1/chat/sessions/e929cdc3.../send/`→409 Conflict（重复 request_id 拒绝）。幂等守卫生效。**PASS**。
- **E6 ownership**：`spaces/models.py:560 class OwnershipTransfer`、`MODE_OFFBOARDING`、`ownership_version` 字段；`test_pg_ownership_locking.py`（PG 锁回归）+ 4 个 ownership 测试 + `ownership_services.py`/`purge_services.py`。commit `95a4093`。**PASS**。

## F. §26 两 bug

- **F1 modal（CONDITIONAL）**：
  - 复现文件 `SpaceSwitcher.tsx:33-37 getModalTransitionName()`：reduced-motion 或无 `TransitionEvent` → `''`（禁过渡），否则 `undefined`（antd 默认 motion）。`transitionName={modalTransitionName}` + `onCancel={closeJoin}`（不拦）+ `maskClosable`+`keyboard` → submit 期间 X/Cancel/Esc/mask 可关 ✓。
  - 共享原语 `design/primitives.tsx ConfirmDialog`：无 transitionName（默认 motion）+ `onCancel={pending ? undefined : onCancel}`（pending 时默认仍可关）+ `destroyOnHidden` ✓。
  - **但 12 个业务 Modal 仍硬编码 `transitionName="fade"`**：AdminTemplatesPage×6、AdminCodesPage×2（含 §26 复现相邻的访问码弹窗 `AdminCodesPage:144`）、SpaceManagementPage×2、AdminBusinessLinesPage×1、AdminAnnouncementsPage×1。全仓无 `.fade-enter/.fade-leave/.fade-appear` CSS（`animations.css` 只有 `.fade-in-up`），无 `deadline`/`motion=`/`ConfigProvider`。按 §26.2（spec:2598-2604）根因，这些 Modal 的 `afterClose` 不执行、Portal/focus/scroll lock 泄漏仍存在。§26 契约（spec:2606 "14 same-pattern modals in regression scope"）未全覆盖。无 Built-Chromium 证据（spec:2620-2623 强制）。
- **F2 限流（PASS）**：`base.py:256-259` `CACHES['default'].BACKEND=django.core.cache.backends.redis.RedisCache`（Redis shared，非 LocMemCache）；rates `navigation_read_sustained=240/minute`、`navigation_read_burst=60/10seconds`；`test_throttling.py:52` "stable and preserves retry_after"、`:60` `assertEqual(response["Retry-After"],"7")`；`exceptions.py:58` Retry-After 透传；前端 8 处 `retryAfterSeconds` 显示"请在 X 秒后重试"（不伪装空态）。**PASS**。

---

## 失败/条件项精确复现 + 建议修法

### 条件 1：C1 迁移契约测试 4 error

**复现命令**：
```
docker exec knowpliot-backend-1 python manage.py test \
  --settings=config.settings.test --noinput
```
**结果**：`Ran 581 tests in 634.599s FAILED (errors=4, skipped=13)`

**4 个 error（均为 TransactionTestCase 迁移契约）**：
1. `apps.knowledge.test_workspace_retention_migration.KnowledgeWorkspaceRetentionMigrationTests.test_snapshots_detach_and_legacy_scope_remains_explicit`（body，line 121 `executor.migrate(targets)`）→ `RuntimeError: missing or duplicate purge registry row for knowledge.DocumentCategory` @ `knowledge/migrations/0011_workspace_retention_contract.py:97 mark_registry_ready`
2. 同上（tearDown，line 37 `executor.migrate(leaf_nodes)`）→ 同 `mark_registry_ready` RuntimeError
3. `apps.scenario_templates.test_v3_template_migration.VersionedCloneMigrationTests.test_backfill_normalizes_hashes_current_pointer_and_application_pin`（`serialized_rollback=True`）→ `psycopg.errors.UniqueViolation: duplicate key (app_label,model)=(admin,logentry)` on `django_content_type`（fixture 反序列化时 PG 严格唯一冲突；SQLite 宽松不报）
4. `apps.scenario_templates.test_workspace_retention_migration.ScenarioWorkspaceRetentionMigrationTests.test_application_snapshots_survive_workspace_and_template_detachment`（setUp line 24 `executor.migrate(targets)`）→ 同 `mark_registry_ready` purge registry

**性质**：迁移隔离契约测试在 PG 严格约束下的产物——`mark_registry_ready` RunPython 校验 purge registry 状态在子集迁移序列下不匹配；`serialized_rollback` 在 PG 触发 contenttype 唯一冲突。**非 V3 运行时 bug**（migrate 全序列真实 PG 全过、backend 起、chat SSE 工作）。

**影响**：C1 不全绿，验收门 C1 未达"PG 套件通过"。这 4 个是 v1.74.2 修复链（`fc8be81` psycopg3 %%+deferred-trigger → `bf9c2bb` "clear PG test-suite cascade migration-contract deferred-trigger + owner-mirror"）在清的级联——清了 stage_a/c、0016 purge guard（`6d67805`）、deferred-trigger，但 `workspace_retention_migration` + `v3_template_migration` 残留 4 个。

**建议修法（交回 Codex）**：
- `mark_registry_ready`：在迁移子集契约测试下，purge registry 行的"missing or duplicate"判定需容忍测试上下文（按 app/model 幂等 upsert，而非严格 equal-count 校验）；或测试 setUp 先 seed registry 期望行再 migrate。
- contenttype `(admin,logentry)` 唯一冲突：`VersionedCloneMigrationTests` 的 `serialized_rollback=True` 在 PG 与 contenttypes 冲突——改用 `serialized_rollback=False` + 显式 fixture，或在 setUp 前 `connection.cursor().execute("DELETE FROM django_content_type WHERE app_label='admin'")`（或用 `update_contenttypes` 信号禁用）。
- 修后重跑 C1 至 0 error。

### 条件 2：F1 §26 modal 12 个未修

**复现命令**：
```
rg -n 'transitionName="fade"' frontend/src
```
**结果**：12 处（AdminTemplatesPage:813/896/1045/1101/1218/1273、AdminCodesPage:144/160、SpaceManagementPage:472/516、AdminBusinessLinesPage:155、AdminAnnouncementsPage:142）。

**性质**：`transitionName="fade"` 无对应 `.fade-*` CSS（`rg "\.fade-enter|\.fade-leave" frontend/src` = 空）、无 `deadline`。按 §26.2（spec:2598-2604），rc-motion 等待 transitionend 但无 CSS 事件 + rc-dialog 无 deadline → `afterClose` 不执行、`animatedVisible` 残留 true、Portal/focus/scroll lock 泄漏。§26 契约（spec:2606）要求 14 个同模式 Modal 全进回归。

**影响**：§26 第 6 BUG 的 modal 分支未全面修通（SpaceSwitcher 复现文件 + 共享原语已修，但业务 Modal 未迁移）。

**建议修法（交回 Codex）**：
- 把 12 个业务 Modal 的 `transitionName="fade"` 改用 `getModalTransitionName()`（提取到共享 util，如 `src/design/modal-motion.ts`），或直接删 `transitionName`（用 antd 默认 motion），或全局加 `.fade-enter/.fade-leave/.fade-appear` CSS + finite `transition-duration`。
- `confirmLoading` 已不拦关闭（`onCancel={()=>setOpen(false)}` 不 gated）✓，但需 Built-Chromium 证明 4 关闭控件 idle/pending + 20 次 open/close 零泄漏（spec:2620-2623）。

---

## 上线前待验收门（不判 fail）

1. **筼筜 PG 迁移演练**：在授权生产 PG clone 上 rehearsal `chat.0013/spaces.0008/chat.0014-0016`（+ 0017）additive 序列。
2. **live Redis 多 worker**：多 worker 实压下验证 240/min shared limiter 决策一致、Retry-After 行为（F2 代码已就绪，需 live 证）。
3. **真实 provider SLO/隐私**：DashScope SLO + 隐私（§7 不暴露 reasoning 在 live 已部分由 D5 证，需持续压测）。
4. **production browser UAT**：§10 acceptance 在真实 Chromium 复现（C3 当前无 playwright；含 modal close/leak、reduced-motion、role journey、create-approval、delete 两阶段、思考开关、中英文答复、responsive）。
5. **responsive 走查**：移动端/可访问性。
6. **modal leak 回归**：F1 修后 Built-Chromium 20 次 open/close 零泄漏证据。

## SPEC 设计遗留

- §17 gate 表 + §27 evidence matrix 每行仍 `currently pending`（spec 自述"Markdown 断言不能作为等效验收而被豁免"，符合预期，需实现证据填入）。
- A2：spec 文档保留 `qwen3.7-Flash` 的禁止性提及（5 处 in 3 specs），literal "grep=0" 不满足但语义正确——建议 spec 加注"以下提及均为禁止性说明"以消歧（可选）。
- A4：迁移图 15 节点 vs 12 anchor 超集（3 个中间节点），spec 明确禁止重排（spec-delta:176-177），现状合规。

## 审计元数据

- commit SHA：`097d3c225e05b47abdf31670f87bf699dde468ef`
- 分支：`codex/v4-optimization`（V3-stable 候选 `bf9c2bb`）
- 工作树：clean
- 审计日期：2026-07-20
- Docker：`knowpliot-{db,redis,backend,celery-worker,frontend}` 全 Up（db/redis healthy 13h，backend/celery/frontend up 12h）

## 可复现命令（不含秘密）

```bash
# B 可启动
docker exec knowpliot-backend-1 python manage.py check
docker exec knowpliot-backend-1 python manage.py makemigrations --check --dry-run
docker exec knowpliot-backend-1 python manage.py migrate
docker exec knowpliot-backend-1 python manage.py showmigrations

# C1 PG 套件
docker exec knowpliot-backend-1 python manage.py test --settings=config.settings.test --noinput

# C2 前端（typecheck host；build/vitest 需 Linux 容器，见下）
cd frontend && node ./node_modules/typescript/bin/tsc --noEmit   # exit 0
node scripts/check-i18n.cjs                                       # PASS
# build/vitest host 受 rollup native 平台不匹配阻塞；Linux 容器内跑：
MSYS_NO_PATHCONV=1 docker run --rm -v "D:/KnowPliot/frontend:/app" -w "//app" node:20 \
  sh -c 'node ./node_modules/vite/bin/vite.js build; node ./node_modules/vitest/vitest.mjs run'

# D 模型
docker exec knowpliot-db-1 psql -U knowpilot -d knowpilot -c "SELECT name,model_id,enabled FROM spaces_modelprofile;"
docker exec knowpliot-db-1 psql -U knowpilot -d knowpilot -c "SELECT revision, values FROM spaces_governancepolicy ORDER BY revision DESC LIMIT 1;"
docker exec knowpliot-db-1 psql -U knowpilot -d knowpilot -c "SELECT attname, format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid='knowledge_documentchunk'::regclass AND attname LIKE '%embedding%';"
docker exec knowpliot-backend-1 sh -c 'echo "QWEN_CHAT_MODEL=$QWEN_CHAT_MODEL QWEN_EMBEDDING_MODEL=$QWEN_EMBEDDING_MODEL DASHSCOPE_API_KEY_SET=$([ -n "$DASHSCOPE_API_KEY" ] && echo yes)"'

# D5 chat send（mint JWT via shell，不打印 token；复用 session e929cdc3）
T=$(docker exec knowpliot-backend-1 python -c "import django; django.setup(); from apps.users.models import User; from rest_framework_simplejwt.tokens import RefreshToken; print(str(RefreshToken.for_user(User.objects.get(username='audit_admin')).access_token))" 2>/dev/null | tail -1)
RID=$(docker exec knowpliot-backend-1 python -c "import uuid; print(uuid.uuid4())" 2>/dev/null | tail -1)
curl -s -N -m 90 -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -X POST "http://127.0.0.1:8000/api/v1/chat/sessions/e929cdc3-ffbf-44b6-881f-f12133eed52c/send/" \
  -d "{\"content\":\"audit probe: what is 1+1\",\"client_request_id\":\"$RID\",\"answer_mode\":\"fast\",\"thinking_enabled\":false,\"protocol_version\":2}"

# E3 scope
T2=$(docker exec knowpliot-backend-1 python -c "import django; django.setup(); from apps.users.models import User; from rest_framework_simplejwt.tokens import RefreshToken; print(str(RefreshToken.for_user(User.objects.get(username='audit_user')).access_token))" 2>/dev/null | tail -1)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $T2" http://127.0.0.1:8000/api/v1/admin/users/   # 期望 403

# F1 modal 清单
rg -n 'transitionName="fade"' frontend/src        # 12 处（条件 2）
rg -n 'getModalTransitionName' frontend/src       # 仅 SpaceSwitcher（已修）
```

---

## 结论重申

**Accepted-with-conditions**。V3 核心在真实 PG 跑通（迁移/backend/chat SSE/模型/不变量/§26 限流），但 C1 残留 4 个迁移契约 error + F1 §26 modal 12 个未修未覆盖，未达 clean Accepted。

**按既定门禁：Conditional → 停，不进阶段二（V4 优化）。交回 Codex 修 C1（2 类迁移契约：mark_registry_ready purge registry + serialized_rollback contenttype 冲突）+ F1（12 个业务 Modal 迁移到 getModalTransitionName/默认 motion + Built-Chromium 证据）后复审。**
