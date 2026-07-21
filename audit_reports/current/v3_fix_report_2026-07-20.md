# KnowPilot V3 修复报告（2026-07-20）

> 分支：`codex/v3-audit-fix`
> 范围：C1 迁移契约 error + F1 §26 modal 泄漏 + 全量套件 ownership flaky hang
> 状态：**全部修复**，全量 PG 套件连续两轮 582 OK，无 hang。

## 一、修复总览

| Bug | 现象 | 修法 | 验证 |
|---|---|---|---|
| C1 | 4 个迁移契约 error（真实 PG） | `mark_registry_ready` 改 `.update()` + `bulk_create`（无 `save()`/信号）+ 7-tuple 契约 + 去 `if updated!=1: raise` | 子集 193/231 OK |
| F1 | §26 modal transitionend 泄漏 | `animations.css` 补 `.fade-*` motion CSS（finite deadline + reduced-motion） | 前端 tsc+vite build OK |
| 全量 hang | ownership stage_c 偶发 hang（全量偶发、子集必过） | `spaces.0010` 加 `atomic = False` | 全量两轮 582 OK |

## 二、全量 flaky hang —— 本次主攻的最后 bug

### 根因（psql 实验证实）

不是跨测试"pending deferred 约束残留"，而是 **`spaces.0010_ownership_continuity_stage_c`（`atomic=True`）把 backfill 的 DML 和 AlterField 的 DDL 放进同一事务**，与 `spaces.0011` 的 `DEFERRABLE INITIALLY DEFERRED` ownership trigger 冲突。

时序：
1. `spaces.0011` 在 `spaces_knowledgespace / spaces_spacemembership / users_user` 上装了 deferred ownership constraint trigger。
2. 第一个 ownership 测试 body `executor.migrate([0010])`：`0010` 单事务内先 `RunPython(backfill_canonical_owners)` 执行 `UPDATE spaces_knowledgespace SET owner_id=...`（DML，owner FK deferred → pending trigger event），随后 `AlterField owner→PROTECT` 执行 `ALTER TABLE ... SET NOT NULL`（DDL）。
3. PG 拒绝 DDL：`cannot ALTER TABLE "spaces_knowledgespace" because it has pending trigger events` → 测试卡在 migrate 调用处。
4. 全量偶发、子集必过：子集触发器/数据组合不同；全量前序测试留下的表行让 `0010` 在有数据状态下重跑，命中该路径。`provider_circuit_open` 是无关红鲱鱼日志行。

### 实验证据

最小复现（psql，users/space/membership + 0011 风格 ownership trigger）：

```
BEGIN;
INSERT INTO users_user ...;
INSERT INTO spaces_knowledgespace (owner_id) VALUES (NULL);
INSERT INTO spaces_spacemembership ...;
UPDATE spaces_knowledgespace SET owner_id = 1 WHERE id = 1;          -- DML，deferred FK 入队
ALTER TABLE spaces_knowledgespace ALTER COLUMN owner_id SET NOT NULL; -- DDL
-- → ERROR: cannot ALTER TABLE "spaces_knowledgespace" because it has pending trigger events
ROLLBACK;
```

对照（修法）：backfill 独立事务先提交，DDL 干净事务执行 → 全部成功。

### 修法

`0010` 加 `atomic = False`，让 backfill 与 AlterField 各自原子提交：backfill 的 UPDATE 先 commit（deferred FK 在 commit 时 fire），后续 DDL 在无 pending 的干净事务执行。

与 `spaces.0012` / `0014` / `0015` / `scenario_templates.0006` 治**同一类**问题**同构**（这些文件已有 `atomic=False` 注释）。`0010` 是唯一漏掉该约定的迁移。

### 为什么不采用 SET CONSTRAINTS / 逐个 culprit reset / 改 backfill 签名

- **`SET CONSTRAINTS ALL IMMEDIATE`（全局或单点）**：事务内状态，事务结束即失效，无法在 fixture 级"预防"尚未开始的事务 → 只部分管用、flaky（前一 session 已踩坑）。
- **逐个 culprit 测试 reset**：culprit 随 run 变化，漏一个就复发。
- **改 `backfill_canonical_owners` 不用 `schema_editor`**：函数本来就只用 `schema_editor.connection.alias`，hang 是事务边界问题不是 schema_editor 对象问题。

## 三、修改代码地址备忘

### 本次（全量 hang）唯一代码改动

- **`backend/apps/spaces/migrations/0010_ownership_continuity_stage_c.py`**
  `Migration` 类加 `atomic = False` + 注释（约 line 48–61）。只改迁移事务边界，不改 `backfill_canonical_owners` 逻辑，不改任何不变量。

### 前一 session 已修（C1 + F1，已在 b1a999b，别动）

- `backend/apps/knowledge/migrations/0011_workspace_retention_contract.py` — `mark_registry_ready`: `.update()` + `bulk_create` + 7-tuple
- `backend/apps/scenario_templates/migrations/0007_workspace_retention_contract.py` — 同上（1 model）
- `backend/apps/chat/migrations/0018_workspace_retention_contract.py` — 同上（10 chat models）
- `backend/apps/audit/migrations/0015_workspace_retention_contract.py` — 同上（audit.AuditLog）
- `backend/apps/scenario_templates/test_v3_template_migration.py` — 去 `serialized_rollback=True`
- `backend/apps/knowledge/test_workspace_retention_migration.py` — tearDown test-side re-seed
- `backend/apps/scenario_templates/test_workspace_retention_migration.py` — tearDown test-side re-seed
- `backend/apps/spaces/migrations/0016_workspace_deletion_stage_c.py` — **保持原始**（不加守卫/re-seed）
- `frontend/src/styles/animations.css` — `.fade-*` motion CSS

## 四、验证结果（全部真实 PG，`--settings=config.settings.test`）

| 验证 | 结果 |
|---|---|
| psql 最小复现 | 当前代码 ERROR → 修法后 OK |
| ownership + join_v2 子集 | `Ran 12 tests OK` |
| ownership 单独（fails_closed 语义） | `Ran 2 tests OK` |
| **全量 + 修法 第 1 轮** | `Ran 582 tests OK (skipped=13)` / 416s |
| **全量 + 修法 第 2 轮** | `Ran 582 tests OK (skipped=13)` / 418s |
| 回归 apps.core+users+spaces | `Ran 231 tests OK`（未改坏 C1/F1/ownership） |
| 真实 DB registry | `spaces_workspacepurgedependency` 36/36 `ready` |

### 环境注意

- 容器名是 `onborading-ai-{db,backend,celery-worker,frontend}`（**不是** `knowpliot-*`）。
- DB：user/db = `ey_onboarding`，test 库 = `test_ey_onboarding`。
- backend 容器 bind-mount host `backend/` → `/app`，改 .py 即时生效；但 gunicorn reloader 会竞争（改文件时若有后台测试在跑会污染结果）。

## 五、不变量安全确认

- 只改迁移事务边界（`atomic=False`），不改 V3 生产代码语义（§4/§5/§6/§7/§11/§16 不变量不破）。
- 真实 PG `migrate` 全过；真实 DB registry 36/36 ready。
- `test_stage_c_fails_closed_for_zero_or_multiple_eligible_owners` 语义在 `atomic=False` 下不破：backfill 仍在 AlterField 前跑，0/2 合格 owner 时照 raise `ownership_continuity_stage_c_blocked`，`assertRaisesRegex` 命中（已实测）。
