# V3 全量套件 flaky hang — 诊断与修法（最终）

> 日期：2026-07-20
> 分支：`codex/v3-audit-fix`（在 b1a999b 之上）
> 状态：根因已用真实 PG 实验证实；修法 = 给 `spaces.0010` 加 `atomic = False`（镜像 `0012`/`0014`/`0015` 既有模式）。

## 一、根因（真实 PG 实验证实，非推测）

hang 不是跨测试"pending deferred 约束残留"，而是 **`spaces.0010` 迁移内部"先 DML 后 DDL 同一事务"与 `spaces.0011` 的 DEFERRABLE INITIALLY DEFERRED ownership trigger 的交互**。

### 实验证据（psql 直接复现）

最小复现（`users_user` / `spaces_knowledgespace(owner FK DEFERRABLE)` / `spaces_spacemembership` + `0011` 风格 ownership constraint trigger）：

```
BEGIN;
INSERT INTO users_user ...;
INSERT INTO spaces_knowledgespace (owner_id) VALUES (NULL);
INSERT INTO spaces_spacemembership ...;
-- backfill_canonical_owners 的 DML：
UPDATE spaces_knowledgespace SET owner_id = 1 WHERE id = 1;   -- owner FK deferred → pending trigger event
-- 0010 的 AlterField（DDL）：
ALTER TABLE spaces_knowledgespace ALTER COLUMN owner_id SET NOT NULL;
-- → ERROR:  cannot ALTER TABLE "spaces_knowledgespace" because it has pending trigger events
ROLLBACK;
```

**对照实验（修法）**：把 backfill 放到自己的事务先提交，DDL 单独事务跑 → 全部成功。

```
-- backfill（autocommit，自己的事务）：
UPDATE spaces_knowledgespace SET owner_id = 1 WHERE id = 1;   -- 立即 commit，deferred FK 在 commit 时 fire
-- DDL（干净事务，无 pending）：
BEGIN; ALTER TABLE ... SET NOT NULL; COMMIT;                  -- OK
```

### 机制

1. `spaces.0011` 在 `spaces_knowledgespace` / `spaces_spacemembership` / `users_user` 上装了 `DEFERRABLE INITIALLY DEFERRED` 的 ownership constraint trigger。
2. 测试 body 在 autocommit 下 `INSERT` user/space/membership → deferred trigger 在每个隐式事务的 commit 时 fire，**不留 pending**。
3. 第一个 ownership 测试 body 里 `executor.migrate([0010])`：`0010` 是 `atomic=True`（默认），把 `RunPython(backfill_canonical_owners)` 的 `UPDATE`（DML）和 `AlterField owner → PROTECT`（`ALTER TABLE`，DDL）放在**同一事务**。UPDATE 让 owner FK 的 deferred 校验入队（pending），随后的 `ALTER TABLE` 被 PG 拒绝（"cannot ALTER TABLE ... pending trigger events"）→ 测试卡在 migrate 调用处。
4. 这解释了"全量偶发、子集必过"：子集跑时触发器/数据组合不同；全量里前序测试留下的表行让 `0010` 在有数据状态下重跑，命中该路径。`provider_circuit_open` 是无关的红鲱鱼日志行。

## 二、修法（治本，不 flaky）

**文件**：`backend/apps/spaces/migrations/0010_ownership_continuity_stage_c.py`

在 `Migration` 类加 `atomic = False`（并附注释说明原因），让 `RunPython(backfill)` 与 `AlterField` 各自在独立事务提交 —— backfill 的 UPDATE 先 commit（deferred FK 在 commit 时 fire），后续 DDL 在无 pending 的干净事务里执行。

这正是 `spaces.0012` / `spaces.0014` / `spaces.0015` / `scenario_templates.0006` 治**同一类**"deferred trigger + DDL"问题已经采用的模式（见这些文件里的 `atomic = False` 注释）。`0010` 是唯一一个在有数据状态下重跑却仍 `atomic=True` 的迁移，漏掉了这个约定。

```python
class Migration(migrations.Migration):
    # atomic = False: 见文件内注释（backfill UPDATE 在 deferred FK 触发器上下文
    # 会排队 pending trigger event，阻塞同一事务内随后的 AlterField ALTER TABLE，
    # 报 "cannot ALTER TABLE ... pending trigger events"）。
    atomic = False
    ...
```

### 为什么治本不 flaky

- 消除的是"DML→DDL 同一事务"这个**产生错误的序列本身**，而不是去追某个留下状态的 culprit 测试。
- 与项目既有 4 处修法同构，行为可预测：生产 `migrate`（空库/正常数据）不受影响；测试里 backfill 与 AlterField 各自原子提交，deferred FK 在两个 commit 点 fire，无 pending 残留。
- `test_stage_c_fails_closed_for_zero_or_multiple_eligible_owners` 语义不破：backfill 仍在 `AlterField` 前跑，0/2 个合格 owner 时 raise `ownership_continuity_stage_c_blocked`，测试的 `assertRaisesRegex` 依旧命中（已实测两个 ownership 测试均过）。

### 不采用的候选

- **A/B（全局或单点 `SET CONSTRAINTS ALL IMMEDIATE`）**：flaky。`SET CONSTRAINTS` 是事务内状态，事务结束即失效；无法在 fixture 级"预防"尚未开始的事务。且 flush 失败导致连接进入 aborted 状态时，IMMMEDIATE 会让 deferred trigger 立即 fire（对不合规数据报错），不是安全的通用 reset。
- **C（grep deferred trigger 逐个 reset）**：治标。culprit 随 run 变化，且漏一个就复发。
- **改 `backfill_canonical_owners` 用 `connection.alias` 不用 `schema_editor`**：函数本来就只用 `schema_editor.connection.alias`，改不改签名对 hang 无影响——hang 是事务边界问题，不是 schema_editor 对象问题。

## 三、验证

- 机制复现 + 修法对照：`psql` 最小复现 ERROR，改分离事务后 OK（见上）。
- `apps.spaces.test_ownership_migrations + apps.spaces.test_join_v2_persistence` → `Ran 12 tests OK`（含两个 ownership stage_c）。
- `apps.spaces.test_ownership_migrations` 单独 → `Ran 2 tests OK`（fails_closed 语义在 atomic=False 下不破）。
- **全量套件 + 修法，第 1 轮 → `Ran 582 tests in 416s OK (skipped=13)` EXIT=0**；**第 2 轮 → `Ran 582 tests in 418s OK (skipped=13)` EXIT=0**：连续两轮干净通过，顺利越过之前必卡的 ownership/provider 区（原现象是该区 `idle in transaction` 卡 ~2.5min；修后不再出现）。
- **回归确认**：`apps.core apps.users apps.spaces`（C1+F1+ownership 已修子集）→ `Ran 231 tests OK`（修法后保持，未改坏）。
- **真实 DB registry**：`spaces_workspacepurgedependency` 36/36 `ready`（`atomic=False` 未破坏生产迁移语义，V3 §5 不变量安全）。

## 四、验证命令（执行者照此复跑）

```bash
# 重置 test DB
docker exec onborading-ai-db-1 psql -U ey_onboarding -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='test_ey_onboarding' AND pid <> pg_backend_pid();"
docker exec onborading-ai-db-1 psql -U ey_onboarding -d postgres \
  -c "DROP DATABASE IF EXISTS test_ey_onboarding;"

# 关键子集（必须保持通过，证明没改坏 C1/F1/ownership）
docker exec onborading-ai-backend-1 python manage.py test \
  apps.core apps.users apps.spaces --settings=config.settings.test --noinput
# 期望: Ran 231 tests OK

docker exec onborading-ai-backend-1 python manage.py test \
  apps.spaces.test_ownership_migrations apps.spaces.test_join_v2_persistence \
  --settings=config.settings.test --noinput
# 期望: Ran 12 tests OK

# 全量（跑 3 轮确认不 flaky）
for i in 1 2 3; do
  docker exec onborading-ai-db-1 psql -U ey_onboarding -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='test_ey_onboarding' AND pid <> pg_backend_pid();"
  docker exec onborading-ai-db-1 psql -U ey_onboarding -d postgres \
    -c "DROP DATABASE IF EXISTS test_ey_onboarding;"
  docker exec onborading-ai-backend-1 python manage.py test \
    --settings=config.settings.test --noinput | tail -3
done
# 期望每轮: Ran 582 tests OK (skipped=13)
```

> 容器名注意：当前 stack 是 `onborading-ai-{db,backend,...}`（不是 `knowpliot-*`）；DB 用户/库是 `ey_onboarding` / `test_ey_onboarding`。
