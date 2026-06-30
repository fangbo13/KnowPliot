# KnowPilot V6.0 优化功能设计文档

> 版本：V6.0 → V6.x 规划
> 来源：`SPEC.MD`、`KnowPilot.md`、本次 V6.0 多空间改造落地实现
> 用途：在多空间平台已落地的基础上，定义下一阶段的功能补全、性能、检索质量、安全合规与体验优化，给出设计、实现要点、涉及文件、工作量与验收标准。

---

## 0. 当前已落地（V6.0 基线）

为避免重复，本节先确认 V6.0 已交付的能力（优化项均以此为前提）：

- **多空间数据模型**：`Organization / BusinessLine / KnowledgeSpace / SpaceMembership / InviteCode / OrganizationMembership`；`Document / DocumentChunk / ChatSession / Message / Citation / Feedback` 均带 `space` 外键并完成存量回填。
- **服务端权限**：空间角色（owner / knowledge_admin / reviewer / member / guest）+ 平台/组织/业务线管理员（super_admin / org_admin / business_admin），权限矩阵在 `apps/spaces/permissions.py`；文档管理改用 `SpaceDocumentPermission`。
- **数据隔离**：文档 / 会话 / 检索 / 引用按 `space_id` 隔离；RAG 检索带 `space_id` 过滤；切换空间清空上下文。
- **空间 API + 前端**：列表/创建/切换/`join`(访问码)/成员/邀请码；前端 `SpaceSwitcher` + `SpaceManagementPage`；`X-Space-Id` 请求头全链路。
- **审计**：空间相关动作 + `permission_denied` 入库。
- **爬虫**：功能下线（路由/任务/前端/权限码全部移除，历史表保留）。
- **测试**：`apps/spaces/tests.py` 18 项（隔离 / 访问码不越权 / 角色矩阵 / org-business admin / 文档权限 / 爬虫下线）全绿。

> 仍存在的已知缺口（本设计文档逐项给出方案）：场景模板未实现；首字延迟与 Redis 命中率；检索仅向量、无 BM25/rerank；反馈闭环与知识质量看板未做；空间级配额/限流缺失；`space` 外键暂为 nullable；浏览器端到端未自动化。

---

## 1. 优化项总览与优先级

| 编号 | 优化项 | 类别 | 优先级 | 预估工期 |
| --- | --- | --- | --- | --- |
| OPT-1 | 场景模板中心（一键建空间 + 场景化提示/检索/快捷问题） | 功能补全 | **P0** | 5 d |
| OPT-2 | Query Embedding 缓存 + 检索/首字性能 | 性能 | **P0** | 2.5 d |
| OPT-3 | 混合检索（BM25 + 向量）+ Rerank + 来源多样性 | 检索质量 | P1 | 4 d |
| OPT-4 | 知识反馈闭环 + 低置信复核队列 + 知识盲点分析 | 功能补全 | P1 | 4 d |
| OPT-5 | 空间级配额与限流（文档数/存储/问答速率） | 安全/成本 | P1 | 2 d |
| OPT-6 | 文档机密级别 + 鉴权下载 + 过期/陈旧治理 | 安全合规 | P1 | 3 d |
| OPT-7 | 数据隔离强化（space 非空约束 + Postgres RLS 兜底） | 安全 | P2 | 2 d |
| OPT-8 | 管理后台可观测性（RAG 质量/摄取队列/按空间用量） | 可观测 | P2 | 3 d |
| OPT-9 | 前端体验（空间选择页 / 最近空间 / 深链 / 跨空间搜索 / 移动端） | UX | P2 | 3 d |
| OPT-10 | 并发与稳定性（会话级 Redis 锁 / 流式 / gunicorn 调优） | 性能/可靠性 | P1 | 2 d |
| OPT-11 | 测试与 CI（pytest 依赖 / 隔离回归 / 前端 E2E / 流水线） | 工程质量 | P1 | 2.5 d |

路线图建议见 §13。

---

## 2. OPT-1 场景模板中心（SPEC §M3）

### 目标
让"复制到一百个团队"成立：管理员从模板 5 分钟内开出一个新业务空间，自动带上该场景的提示策略、检索过滤、推荐文档分类、快捷问题与默认角色。

### 设计
- 新增模型 `ScenarioTemplate`（`apps/spaces` 或新 `apps/templates`）：
  - `id, name, scenario_type, version, description`
  - `prompt_policy`(JSON：系统提示模板、语气、引用要求、拒答策略)
  - `retrieval_policy`(JSON：top_k、相似度阈值、类别过滤、是否启用 BM25)
  - `quick_questions`(JSON 列表，按语言)
  - `default_roles`(JSON：建空间时预置成员角色)
  - `answer_format / compliance_warnings`
  - `is_system`(内置不可改) / `created_by`
- `KnowledgeSpace.template` 外键（已预留 SPEC，可补字段 `template_id` + `settings` 覆盖）。
- API（SPEC §6.2）：`GET /templates/`、`POST /templates/{id}/apply/`（按模板建空间）、`GET /templates/{id}/versions/`。
- Seed 命令 `seed_templates`：内置 KnowPilot.md 的 9 个场景（入职/项目组 AI/方法论/准则问答/跨准则比较/风险识别/底稿/独立性/意见决策）。
- 前端：创建空间弹窗增加"从模板创建"下拉；Chat 顶部快捷问题改为读 `space.settings.quick_questions || template.quick_questions`（替换 `quick_actions` 的硬编码入职问题）。
- 提示装配：`prompt_builder.build()` 接受 `space.settings.prompt_policy` 注入场景化系统提示。

### 涉及文件
`apps/spaces/models.py`、新 `templates` 视图/序列化器/urls、`apps/rag/prompt_builder.py`、`apps/chat/views.py:quick_actions`、`frontend/src/api/spaces.ts`、`SpaceSwitcher.tsx`、`ChatPage`/`WelcomeScreen`。

### 验收
- 从模板建空间 < 5 分钟；模板修改不影响既有空间（版本化）；Chat 显示场景化快捷问题；提示策略生效且可被空间级 `settings` 覆盖。

---

## 3. OPT-2 Query Embedding 缓存 + 首字性能（P0）

### 背景
历史审计与记忆指出：首字慢 = DashScope embedding/LLM 延迟 + Redis 近零命中率（26%）。每次提问都重新 embed query。

### 设计
- 在 `EmbeddingService.embed(query)` 前加 Redis 缓存：key = `emb:v4:{sha256(text)}`，value = 向量（msgpack/json），TTL 7 天。命中即省去一次 DashScope 往返。
- 空间维度无需进 key（同文本同向量），但**检索结果不缓存**（结果与 space/权限相关）。
- 监控命中率（埋点 `emb_cache_hit/miss`），目标 > 60%。
- 首字优化：检索阶段与"已建立连接/searching"事件并行；`citations` 事件已重置前端 30s 计时器（V4.6 已做）。

### 涉及文件
`apps/rag/embedding.py`、`config/settings/base.py`（缓存配置）、可选 `apps/core` 加一个 redis helper。

### 验收
- 重复/相似 query 首字延迟下降；`emb_cache` 命中率可观测；无跨空间数据通过缓存泄露（仅缓存 query 向量，不缓存文档/结果）。

---

## 4. OPT-3 混合检索 + Rerank（SPEC §M6）

### 目标
准则条款类问题（精确引用）召回更准；降低"答非所问"。

### 设计
- 在 pgvector 向量召回基础上叠加 Postgres 全文检索（`to_tsvector`/`websearch_to_tsquery`，或 `pg_trgm`），对 `knowledge_documentchunk.content` 建 GIN 索引，**同样带 `space_id` 过滤**。
- 融合排序：RRF（Reciprocal Rank Fusion）合并向量与 BM25 两路结果。
- 可选 rerank：调用 DashScope rerank 模型（或本地 cross-encoder）对 top-N 重排，取 top-K。
- 来源多样性：同一 document 命中过多时降权，保证引用覆盖面。
- 由 OPT-1 模板 `retrieval_policy.enable_hybrid` 控制开关。

### 涉及文件
`apps/rag/retriever.py`（新增 `_search_hybrid`）、迁移（GIN 索引）、`apps/rag/config.py`。

### 验收
- 准则/编号类查询命中率提升；隔离不破（BM25 路径同样 `space_id` 过滤，已有测试需扩展覆盖混合路径）。

---

## 5. OPT-4 反馈闭环与知识质量（SPEC §M11）

### 设计
- 复用 `Feedback`（已带 space），新增 `status`(open/triaged/resolved)、`reviewer`、`flag_reason`。
- API：`POST /messages/{id}/feedback/`（已存在，扩展类型：incorrect/outdated/missing_source）、`GET /spaces/{id}/feedback/`（复核队列，reviewer 权限）、知识盲点：`GET /spaces/{id}/insights/`（按空间统计未答/低置信/高引用/从未被检索文档）。
- 陈旧提醒：`Document.effective_to` 到期标记 stale 并默认排除检索。
- 前端：`MessageBubble` 反馈细化；Space Management 增"复核队列"标签页。

### 验收
- 标记的回答可追溯到 session/question/answer/citations/检索元数据；reviewer 可处理并标记 resolved；知识管理员看到高/零引用文档列表。

---

## 6. OPT-5 空间级配额与限流

### 设计
- `KnowledgeSpace.settings` 增 `quota`：`max_documents`、`max_storage_mb`、`chat_rate_per_min`。
- 上传前校验空间文档数/存储；问答用按空间维度的 DRF Throttle（scope = `chat:{space_id}`）。
- 平台默认值 + 空间覆盖；超额返回明确错误码与审计。

### 涉及文件
`apps/knowledge/views.py`、`apps/chat/views.py`（自定义 throttle）、`apps/spaces/serializers.py`。

### 验收
- 单空间无法耗尽全局资源；超额提示清晰；不同空间限流互不影响。

---

## 7. OPT-6 文档机密级别 + 鉴权下载 + 治理

### 设计
- `Document.confidentiality`(public/internal/restricted) + 下载需 `document.download` 空间权限（guest 无）。媒体已走 `AuthenticatedMediaMiddleware`，叠加空间+机密级校验。
- restricted 文档：仅 owner/knowledge_admin 可下载；guest 答案中引用不展示原文下载链接。
- 过期/陈旧：`effective_to` 到期自动 `stale`，检索默认排除 + 看板提醒。

### 验收
- 未授权用户无法通过 `/media/` 直链拿到受限文档；引用展示遵守机密级别。

---

## 8. OPT-7 数据隔离强化（纵深防御）

### 设计
- 数据稳定后将 `space` 外键迁移为 `NOT NULL`（分两步：先回填确保无 null，再 `AlterField`，大表用 `--no-input` 低峰执行）。
- 兜底：对 `knowledge_document/documentchunk/chat_*` 启用 Postgres Row-Level Security（按 `app.current_space` 会话变量），即使应用层漏过滤也不会跨空间返回数据。
- DB 层 `CHECK`/索引：`(space_id, status)` 复合索引优化按空间列表。

### 验收
- 人为去掉某个视图的 `space` 过滤后，RLS 仍阻止跨空间数据返回（新增"防御性"测试）。

---

## 9. OPT-8 管理后台可观测性（SPEC §M10）

### 设计
- `GET /admin/metrics/` 扩展：按空间的活跃用户/会话/问答数/引用覆盖率；RAG 质量（检索 P50/P95、生成延迟、无答率、低置信率）；摄取队列与失败任务（可重试）。
- 前端 AdminDashboard 增"按空间"维度与质量图表。

### 验收
- 管理员能定位坏答案来自检索/陈旧源/提示/模型/缺知识；失败 Celery 任务可见可重试。

---

## 10. OPT-9 前端体验

### 设计
- 独立**空间选择页**（无默认空间或首次登录时）：按业务线分组、搜索、最近空间、`join` 入口、（管理员）建空间。
- Chat 顶栏显式展示当前空间名 + 切换；深链 `/?space=<code>` 打开即校验权限。
- **跨空间搜索**：仅对具备多空间权限的角色开放（默认单空间，避免来源泄露，SPEC §12.3）。
- 移动端：切换/加入/引用抽屉适配。

### 验收
- 无默认空间走选择页；深链权限再校验；跨空间搜索仅对授权角色可见。

---

## 11. OPT-10 并发与稳定性

### 设计
- **会话级 Redis 锁**（`chat/views.py` 现有 TODO SYS-V4.1-007）：`chat:session_lock:{session_id}`，防止同会话并发流写坏状态（gunicorn 多 worker 下必需）。
- gunicorn 线程/worker 按压测调参；DB 连接池已开（CONN_MAX_AGE=60）。
- embedding 批量化、断路器阈值随监控回调。

### 验收
- 多标签/多会话并发不串流、不报错；压测下首字与吞吐达标。

---

## 12. OPT-11 测试与 CI

### 设计
- 镜像加 `[dev]` 依赖（pytest/pytest-django）或统一用 `manage.py test`；当前后端无 pytest，靠 Django runner。
- 扩充隔离回归：混合检索路径、配额、机密下载、RLS 防御性用例。
- 前端 E2E（Playwright）：登录→切换空间→会话/文档按空间隔离→访问码加入→空间管理。
- GitHub Actions：后端 `migrate`+`test`、前端 `tsc`+`vitest`+`build`。

### 验收
- CI 绿；隔离与权限关键路径有自动化回归；E2E 覆盖空间核心流。

---

## 13. 路线图建议

- **迭代 A（P0，约 1.5 周）**：OPT-1 场景模板 + OPT-2 Embedding 缓存。直接兑现"一次部署无限复制"与首字提速两大卖点。
- **迭代 B（P1，约 2 周）**：OPT-3 混合检索 + OPT-4 反馈闭环 + OPT-5 配额限流 + OPT-10 会话锁 + OPT-11 CI。提升答案质量、成本可控与工程质量。
- **迭代 C（P1/P2，约 1.5 周）**：OPT-6 机密治理 + OPT-8 可观测 + OPT-9 体验 + OPT-7 隔离强化。补齐合规、运营与纵深防御。

## 14. 风险与回退

- **模板影响既有空间**：模板版本化 + 空间 `settings` 覆盖，模板变更不回写已建空间。
- **缓存一致性**：仅缓存 query 向量（确定性映射），不缓存检索结果/文档内容，避免跨空间泄露；可一键清空 `emb:*`。
- **`space` 置非空**：分两步迁移并先校验零 null；保留回退（恢复 nullable）。
- **RLS 误伤**：先以"影子模式"在测试库验证，灰度开启；应用层过滤保持不变作为第一道防线。
- **隔离回归**：每个涉及检索/列表的优化都必须新增"跨空间不可见"测试，作为合并门槛。
