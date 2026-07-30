# Demo Database Snapshot

`knowpilot_demo_seed.sql.gz` — 2026-07-30 演示数据快照（pg_dump, PostgreSQL 16 + pgvector）。

包含清理后的 5 个真实知识库（72 篇已嵌入文档、139 条 wikilink 边、全连通图谱）：

- 星辰科技2026年报审计项目（41 篇审计底稿，主演示空间）
- IFRS 参考库 / 中国会计准则参考库 / IPO 案例参考库 / 公司制度公共参考库

演示账号：`admin@test.ey.com` / `admin123`（超管入口 `/admintest`）。

## 恢复步骤

> ⚠️ 会覆盖目标库全部数据，仅用于初始化演示环境。

```bash
# 1. 启动数据库服务
docker compose up -d db

# 2. 重建空库
docker compose exec -T db psql -U knowpilot -d postgres -c "DROP DATABASE IF EXISTS knowpilot WITH (FORCE)"
docker compose exec -T db psql -U knowpilot -d postgres -c "CREATE DATABASE knowpilot"

# 3. 导入快照（Windows PowerShell 请用: gzip -d -k 后重定向 .sql）
gzip -dc backend/backups/knowpilot_demo_seed.sql.gz | docker compose exec -T db psql -U knowpilot -d knowpilot

# 4. 启动其余服务
docker compose up -d
```

## 重新生成快照

```bash
docker compose exec -T db pg_dump -U knowpilot -d knowpilot --no-owner --no-privileges > backend/backups/knowpilot_demo_seed.sql
gzip -9 backend/backups/knowpilot_demo_seed.sql
```

## 备注

- 快照不含任何 API Key / SECRET_KEY（均在 `.env`，未入库）；含演示账号的密码哈希与测试聊天记录。
- 如不想用快照，也可以在空库上跑 `backend/scripts/seed_real_knowledge.py` 重建知识数据（需 DashScope API Key 做嵌入）。
