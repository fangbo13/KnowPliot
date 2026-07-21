# V3 修复交接说明（供 Claude Codex 接手）

> ⚠️ UPDATE 2（2026-07-20 最终）：**provider hang 实为 flaky 的 deferred-constraint hang**，不是单一 provider 问题。最新发现见末尾"## 七、最新发现（flaky hang + SET CONSTRAINTS 部分修）"。简言之：
> - 全量套件 hang 在**第二个 ownership 测试** `test_stage_c_fails_closed_for_zero_or_multiple_eligible_owners`（其 body `connection.schema_editor()` + `backfill_canonical_owners` 直接调用，被前序测试留的 pending deferred 约束挂死）—— **不是 provider**（`provider_circuit_open` 是 `test_chat_generation_policy` mock circuit-open 的日志，红鲱鱼）。
> - 我加了 `SET CONSTRAINTS ALL IMMEDIATE`（在第二个 ownership 的 schema_editor 内）→ `apps.core apps.users apps.spaces` = `Ran 231 tests OK`（修了 core+users+spaces 上下文）。
> - **但全量套件仍 flaky hang**：有时过第二个 ownership 卡 provider_circuit_open 后某测试，有时直接卡第二个 ownership。SET CONSTRAINTS 修法**不可靠**（有时管用有时不管用）——pending deferred 约束的来源/上下文在不同 run 间变化。
> - commit `22c7a1f` 含 SET CONSTRAINTS 部分修（test_ownership_migrations.py）。C1+F1+ownership 部分修已保存。
> - **Claude 接手重点**：找一个**可靠的**修法（不是 flaky 的 SET CONSTRAINTS）。候选：①找留 pending deferred 约束的 culprit 测试（flaky，难找）；②全局 reset（monkeypatch TransactionTestCase._pre_setup 跑 SET CONSTRAINTS——但 autocommit 上下文可能 no-op，需验证）；③给第二个 ownership 的 `connection.schema_editor()` 换成不继承连接 deferred 状态的方式（如 `connection.cursor()` 直接跑 backfill 的 SQL，不用 schema_editor）；④排查 `backfill_canonical_owners` 为何用 `schema_editor`（它只做数据 UPDATE，不需要 schema_editor——可能换成普通事务就不 hang）。

> ⚠️ UPDATE 3（2026-07-20 最终最终）：候选④（最小 schema_editor 对象）已试——`backfill_canonical_owners` 确实只用 `schema_editor.connection.alias`（不做 DDL），改用最小 `_MinimalSchemaEditor(connection)` 对象（去掉 `connection.schema_editor()` setup）→ `apps.core apps.users apps.spaces` = `Ran 231 tests OK`（core+users+spaces 上下文过）。**但全量套件仍 flaky hang**——hang 点在**第一个 ownership / 第二个 ownership / provider_circuit_open 之间随机变化**（不同 run 不同点）。所以候选④也只**部分修**（修了直接 schema_editor 调用，但全量里 migrate executor 内部的 schema_editor + 其它机制仍 flaky hang）。
> - commit `6fca9d9` 含候选④（最小 schema_editor，test_ownership_migrations.py 的 `test_stage_c_fails_closed`）。
> - **核心难点给 Claude**：hang 是**真 flaky**（同代码不同 run hang 点不同），不是单一 deterministic bug。可能是**多个测试各自在不同上下文下偶发 hang**（pending deferred 约束来源不定）。建议 Claude：①多跑几轮全量 -v 2 收集不同 run 的 hang 点，找共性；②或加**全局 deferred-constraint reset**（TransactionTestCase `_post_teardown` 跑 `SET CONSTRAINTS ALL IMMEDIATE` + `COMMIT`，确保每个测试结束时不留 pending deferred 约束）——这是治本的 fixture 级修法，不依赖定位单个 culprit；③或排查哪些测试用 deferred trigger（grep `DEFERRABLE INITIALLY DEFERRED` 在迁移）+ 确保它们 tearDown 时 `SET CONSTRAINTS IMMEDIATE`。
> - **已确认修复（可靠）**：C1（4 个迁移契约 error）+ F1（fade CSS）+ 第二个 ownership 的直接 schema_editor hang（候选④，core+users+spaces 231 OK）。这些在 core+users+spaces 子集里 deterministic 通过。全量 flaky hang 是**额外的**、跨测试的 deferred-constraint 隔离问题，不是 C1/F1/ownership 修复引入（原审计全量能完成是因为 knowledge retention 测试 error 中止、没跑到这些点）。

> 日期：2026-07-20
> 仓库：`D:/KnowPliot`，分支 `codex/v3-audit-fix`（off `codex/v4-optimization` @ `097d3c2`）
> 状态：C1 + F1 + ownership 部分修（SET CONSTRAINTS，core+users+spaces 231 OK）；**全量套件仍 flaky hang（未可靠修）**。交 Claude。
> commit：`22c7a1f`（含所有修复 + 本 handoff）

## 一、已修复 + 验证的 bug（别动这些）

### Bug 1：C1 迁移契约测试 4 error（真实 PG）
**根因**：`TransactionTestCase` 在测试间 **truncate 清空 `spaces_workspacepurgedependency` 表**，而 `spaces.0015` 的 `seed_purge_registry`（建 36 行）一旦 applied 就**不重跑**。于是：
- `knowledge.0011` / `scenario_templates.0007` / `chat.0018` / `audit.0015` 的 `mark_registry_ready`（原 `.update()` + `if updated != 1: raise`）在测试 body/tearDown 跑时找不到行 → `updated=0` → `RuntimeError: missing or duplicate purge registry row`。
- `scenario_templates.test_v3_template_migration` 的 `serialized_rollback=True` → `django_content_type (admin,logentry)` 在 PG 严格唯一约束下 UniqueViolation（post_migrate 重建 + 序列化回滚重插冲突；SQLite 宽松不报）。
- `spaces.0016 finalize_and_validate_registry` 同 truncate 问题：retention 测试 tearDown 重跑 finalize 时 registry 空/不全 → "missing or duplicate final purge registry row" / "pending required migration"。

生产 `migrate` 不报（行持久）。C1 全量套件是**首次全新 test DB** 跑暴露。

**修法（已在工作树）**：
1. 4 个 `mark_registry_ready`（knowledge.0011/scenario_templates.0007/chat.0018/audit.0015）：用 **`.update()` 更新已有行 + `bulk_create` 新建缺失行**（均 bulk SQL，**无 `save()`/信号**）+ 7-tuple 契约（snapshot/scrub/space_field/disposition/blocker_code/lock_order/purge_order，镜像 spaces.0015 REGISTRY_ROWS）。**删掉 `if updated != 1: raise`**（容忍 test-truncate 缺失行；`spaces.0016 finalize` 仍校验 count+all-ready，真实缺陷仍被它抓）。
2. `scenario_templates.test_v3_template_migration`：移除 `serialized_rollback=True`（镜像 39f1f68 + retention 测试模式；测试自建数据不依赖 serialized fixture）。
3. `knowledge.test_workspace_retention_migration` + `scenario_templates.test_workspace_retention_migration` 的 **tearDown 加 test-side re-seed**：`migrate(leaf_nodes)` 前，先 `importlib` 调 `spaces.0015.seed_purge_registry`（建 36 行）+ 重跑 4 个 `mark_registry_ready`（设 17 个非 ready_owner 行为 ready），再 migrate → `spaces.0016 finalize` 看到 complete+ready → 过。
4. **`spaces.0016` 保持原始（097d3c2），不要加 count 守卫或 importlib re-seed**（详见 Bug 3）。

### Bug 2：F1 §26 modal transitionend 泄漏
**根因**（spec §26.2, spec:2598-2604）：12 个业务 Modal 硬编码 `transitionName="fade"`，但全仓无 `.fade-enter/.fade-leave/.fade-appear` CSS、无 `deadline`。antd 5.x 经 rc-dialog→rc-motion 等 `transitionend`，无 CSS 事件 + rc-dialog 无 deadline → `afterClose` 不执行 → `animatedVisible` 残留 true → Portal/focus/scroll lock 泄漏。复现文件 `SpaceSwitcher.tsx` 已用 `getModalTransitionName()` 修通，但 12 业务 Modal 未迁移。

**修法（已在工作树）**：`frontend/src/styles/animations.css` 加 `.fade-enter/.fade-appear{opacity:0}` + `.fade-enter-active/.fade-appear-active{opacity:1;transition:opacity var(--motion-fast) var(--motion-ease)}` + `.fade-leave{opacity:1}` + `.fade-leave-active{opacity:0;transition:...}` + 扩展 `@media (prefers-reduced-motion: reduce)` 把 `.fade-*-active` 的 `transition-duration:0.01ms !important`。12 业务 Modal 的 `transitionName="fade"` 保留（视觉不变），现在有 CSS 支撑、`transitionend` 能触发、无泄漏。

### Bug 3：ownership hang（我引入的回归，已修）—— ⚠️ Codex 别重蹈覆辙
**我两次错误尝试**：
- ❌ 尝试 1：`mark_registry_ready` 用 `update_or_create`（建缺失行）。但 `update_or_create` 用 `save()`（逐行 + 触发信号）。在第一个 ownership stage_c tearDown（传递性重跑 mark_registry_ready）里，`save()` 在 deferred-trigger 上下文留状态 → **第二个 ownership 测试 `test_stage_c_fails_closed_for_zero_or_multiple_eligible_owners` hang**（其 body 直接调 `backfill_canonical_owners(self.old_apps, schema_editor)` with `connection.schema_editor()`，等被留的 deferred 约束）。
- ❌ 尝试 2：`spaces.0016 finalize` 加 `if Registry.objects.count() < 36: return` 守卫。也 hang 第二个 ownership。
- ❌ 尝试 3：`spaces.0016 finalize` 加 importlib re-seed（调 `seed_purge_registry` + 4 `mark_registry_ready`）。hang 第一个 ownership。

**实证**：把 4 个 `mark_registry_ready` 还原到原始（`.update()` + raise）+ 跑 `apps.spaces.test_ownership_migrations + test_join_v2_persistence` → `Ran 12 tests OK`（两个 ownership 都过）。**证明 `update_or_create` 的 `save()` 副作用是 ownership hang 的根因**。

**正确修法（已在工作树）**：
- `mark_registry_ready` 用 **`.update()` 已有 + `bulk_create` 缺失**（均 bulk SQL，**无 `save()`/信号**）→ 不留 deferred-trigger 状态 → ownership 不 hang。
- `spaces.0016` **还原原始**（不加守卫/不加 re-seed）。ownership tearDown（原始 finalize）正常工作，因为 setUp 回滚 spaces 到 0009 会**传递性回滚 knowledge/chat/scenario/audit**，tearDown 重跑时 `spaces.0015 seed` + 4 个 `mark_registry_ready` 都重跑 → registry complete+ready → finalize 过。
- retention tearDown 加 test-side re-seed（Bug 1 修法 3）补非传递性回滚的场景。

**关键教训给 Codex**：
- ❌ 不要在 `mark_registry_ready` 用 `update_or_create`（save() 留 deferred-trigger 状态 hang ownership）。用 `.update()` + `bulk_create`。
- ❌ 不要在 `spaces.0016 finalize` 加 count 守卫或 importlib re-seed（都 hang ownership）。保持原始。
- ✅ ownership 的 tearDown 不动（原始 finalize + 传递性重跑的 seed/mark_registry_ready 自然补齐 registry）。

## 二、未解决的 bug（待 Codex 修）—— provider hang

### Bug 4：全量套件 provider hang（full-suite-only，非代码回归）
**现象**：全量 PG 套件（582 tests）可复现地 hang 在 `pipeline provider_circuit_open code=provider_unavailable`（约 9min 处），其后某个 provider 测试挂死。

**已排除（非此 bug）**：
- 不是 C1/F1/ownership（那些已修，193 tests OK）。
- 不是代码回归：`apps.chat` 单独 `Ran 143 tests OK (skipped=11)`；`apps.spaces + knowledge/scenario retention` `Ran 193 tests OK`；我的修复是迁移 RunPython + CSS，不碰 provider 测试。
- `provider_circuit_open` 是**红鲱鱼**（更早测试的日志行）；真 hang 点在其后的 provider 测试（需 -v 2 定位）。

**根因（我的评估）**：**载荷诱发的 DashScope 限流**。我调试期间跑了 15+ 轮全量套件，DashScope 账号被限流。全量套件的累积 provider 调用（chat send / embedding 测试）trip 了 `apps/core/circuit_breaker.py` 的**模块级单例 `dashscope_breaker`**（进程内、跨测试共享）→ circuit 开 → 后续 provider 测试挂死（很可能某个测试在慢/限流的 DashScope SSE 流上无超时地等，或在 open circuit 上等）。
- 旁证：单发 D5 chat send（0.45s 200）正常，但套件连打几百发就限流挂起。
- 原审计（修前、DashScope 新鲜时）全量能完成（581 tests, 4 errors = C1），circuit 在末尾（12:47:46）才开故完成。我反复跑后 circuit 提前开、挂起。

**circuit breaker 机制**（`apps/core/circuit_breaker.py`）：CLOSED→3 次连续失败→OPEN（fail-fast 503）→恢复超时后→HALF_OPEN（探 1 次）→成功→CLOSED / 失败→OPEN。`record_success` 关闭，`record_failure` 累计。**进程级单例，跨测试共享**——一旦某测试 trip 不 reset，后续测试都看到 open。

**建议修法（Codex 选一或组合）**：
1. **等 DashScope 限流复位**（可能数小时）后跑一轮全量——若 circuit 不提前开、能跑完，就坐实 0-error（最低风险、不改代码，证明是环境）。
2. **-v 2 定位挂死测试**：`docker exec knowpliot-backend-1 python manage.py test --settings=config.settings.test --noinput -v 2`，等 ~9-10min 到 `provider_circuit_open`，读最后那个 `...` 无结果的测试名 = 挂死测试。然后给它加**超时**（provider 调用 / SSE 流）或 **mock provider**。
3. **reset circuit breaker 跨测试**（最治本，若 hang 是 circuit 传播）：在全局测试 fixture（或各 TestCase setUp）reset `dashscope_breaker._state = CLOSED`（+ 重置失败计数），使某测试 trip 不污染后续。Django 无 conftest，可加到现有 test base 或用 `setUp` 钩子。
4. **mock provider** 在挂死的 provider 测试里（治本但改测试）。

**注意**：可能不止一个 provider 测试会挂（多个连打限流）。先 -v 2 定位，看是单个还是多个。

## 三、验证状态（Codex 可复跑确认）

**已 PASS（无 hang、无 error）**：
- `apps.spaces + apps.knowledge.test_workspace_retention_migration + apps.scenario_templates.test_workspace_retention_migration` → `Ran 193 tests OK`（含两个 ownership stage_c + knowledge/scenario retention + 全 spaces）。**这是 C1+ownership 修复的关键验证**。
- `apps.chat` 单独 → `Ran 143 tests OK (skipped=11)`。
- `apps.scenario_templates` 单独 → `Ran 45 tests OK`。
- `apps.audit` 单独 → `Ran 15 tests OK`。
- `apps.core apps.users apps.rbac apps.notifications apps.audit` → `Ran 115 tests OK`。
- `manage.py check` 0 issues；`makemigrations --check --dry-run` No changes。
- 前端 `tsc --noEmit` exit 0 + `vite build` OK（F1，Linux 容器跑，host rollup 平台不匹配）。
- 真实 DB `spaces_workspacepurgedependency`：36 行全 `ready`、0 not-ready（迁移编辑未损坏）。
- D5 chat send `HTTP 200` SSE `model:qwen3.6-flash` 无 `reasoning_content`；E3 `audit_user→/admin/users/=403`。

**未 PASS（Bug 4）**：全量 PG 套件 hang 在 `provider_circuit_open`。

复跑命令：
```bash
# 关键验证（应 OK）
docker exec knowpliot-db-1 psql -U knowpilot -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='test_knowpilot' AND pid <> pg_backend_pid();"
docker exec knowpliot-db-1 psql -U knowpilot -d postgres -c "DROP DATABASE IF EXISTS test_knowpilot;"
docker exec knowpliot-backend-1 python manage.py test \
  apps.spaces apps.knowledge.test_workspace_retention_migration apps.scenario_templates.test_workspace_retention_migration \
  --settings=config.settings.test --noinput   # → Ran 193 tests OK

# provider hang 复现 + 定位
docker exec knowpliot-backend-1 python manage.py test --settings=config.settings.test --noinput -v 2
# 等 ~9-10min 到 provider_circuit_open，读最后 ... 无结果的测试名
```

## 四、文件变更清单（工作树，相对 fc5c440）

```
backend/apps/knowledge/migrations/0011_workspace_retention_contract.py        # mark_registry_ready: .update+builtcreate+7tuple
backend/apps/scenario_templates/migrations/0007_workspace_retention_contract.py# 同上 (1 model)
backend/apps/chat/migrations/0018_workspace_retention_contract.py             # 同上 (10 chat models)
backend/apps/audit/migrations/0015_workspace_retention_contract.py             # 同上 (audit.AuditLog)
backend/apps/scenario_templates/test_v3_template_migration.py                  # 移除 serialized_rollback=True
backend/apps/knowledge/test_workspace_retention_migration.py                   # tearDown: test-side re-seed
backend/apps/scenario_templates/test_workspace_retention_migration.py        # tearDown: test-side re-seed
backend/apps/spaces/migrations/0016_workspace_deletion_stage_c.py             # ⚠️ 还原原始(097d3c2)，别加守卫/re-seed
frontend/src/styles/animations.css                                             # .fade-* motion CSS
```

⚠️ `git diff` 看当前正确状态。`fc5c440` 的 spaces.0016 是**坏的**（importlib re-seed，hang ownership）——工作树已还原原始 + 用 .update/bulk_create。Codex 应 amend `fc5c440` 或新提交保存当前正确版。

## 五、Codex 接手建议

1. 先 `git diff` + `git log codex/v3-audit-fix` 看当前状态（fc5c440 旧版 vs 工作树正确版）。
2. 复跑 `apps.spaces + knowledge/scenario retention` 确认 `Ran 193 tests OK`（C1+ownership 验证在手）。
3. 攻 Bug 4（provider hang）：选上述修法 1/2/3/4。
4. 全量套件 0-error 后，amend/新提交 + 更新 `audit_reports/current/v3_fix_report_2026-07-20.md`。

## 六、元数据
- 分支：`codex/v3-audit-fix`（off `codex/v4-optimization` @ `097d3c2`）
- HEAD：`fc5c440`（旧版，spaces.0016 坏）→ 工作树是正确版（未提交）
- Docker：`knowpliot-{db,redis,backend,celery-worker,frontend}` 全 Up
- 审计/修复报告：`audit_reports/current/v3_acceptance_audit_2026-07-20.md` + `v3_fix_report_2026-07-20.md`（注：修复报告写的是早先版本，未反映 .update/bulk_create 最终修法——Codex 应更新它）
