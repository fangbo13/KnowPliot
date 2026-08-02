# KnowPilot 知识库优化 Spec（科目自主化 · 官方参考库 · 赋能团队模板 · Obsidian 体验）

版本: v1.0 (2026-07-27)
状态: 已批准，实施中

## 1. 背景与目标

当前系统存在四个能力缺口：

1. **科目体系不自主**：知识科目（`TaxonomyDimension`/`TaxonomyTerm`）为组织+业务线共享作用域，由
   `seed_audit_taxonomy` 管理命令离线播种（仅审计线）。创建空间时没有任何科目初始化选项——
   审计线空间被动继承共享科目，项目组无法自建差异化科目，也无法选择"不要科目"。
2. **知识库完全隔离**：RAG 检索强制单一 `space_id` 过滤，无法引用 IFRS 库、中国会计准则库、
   IPO 案例库等权威共享内容，Agent 无法结合本项目情况给出综合答案。
3. **非审计线无匹配模板**：赋能团队等不需要科目的团队缺少对应的空间模板（taxonomy profile）。
4. **编辑体验不及 Obsidian**：缺少分栏实时预览、`[[` wikilink 自动补全、Backlinks 面板、
   以文档为中心的 Local Graph（深度可调）、词级 diff。

## 2. 数据模型变更

### 2.1 空间级科目（apps/knowledge + apps/spaces）

- `TaxonomyDimension` 新增可空 `space` FK（`spaces.KnowledgeSpace`，CASCADE，
  related_name=`taxonomy_dimensions`）。space 非空 = 空间私有维度；space 为空 = 组织/业务线共享维度（现状）。
  - 唯一约束调整：
    - 共享维度：UniqueConstraint(organization, code) WHERE space IS NULL（保持现状语义）；
    - 私有维度：UniqueConstraint(space, code) WHERE space IS NOT NULL。
- `KnowledgeSpace` 新增 `taxonomy_mode` 字段（max_length=20）：
  - `inherit`（默认，存量空间回填）：沿用组织/业务线共享维度，行为完全不变；
  - `space`：仅可见"本空间私有维度 + 组织级维度（business_line 为空且 space 为空，如财年）"；
  - `none`：无科目（赋能团队），维度列表恒为空，上传不做必填校验。

### 2.2 官方参考库（apps/knowledge）

- `ReferenceLibrary`：`space` OneToOne（被认证为参考库的空间）、`name`、`description`、
  `category`（`ifrs`/`cas`/`ipo_cases`/`other`）、`status`（`published`/`unpublished`）、
  `published_by`/`published_at`。仅平台管理员可创建/发布/下架。
- `SpaceLibraryReference`：`space` FK（引用方空间）+ `library` FK、`enabled` Bool、`added_by`。
  UniqueConstraint(space, library)。空间 owner/knowledge_admin 管理。禁止空间引用自身对应的库。

### 2.3 模板 taxonomy profile（apps/scenario_templates）

- `ScenarioTemplate.SCENARIO_CHOICES` 增加 `enablement`（赋能团队）。
- 模板 snapshot 契约新增可选 `taxonomy_profile` 字段：`{"mode": "default_seed"|"custom"|"none", "preset": "audit_default"|null}`。

## 3. API 契约

### 3.1 科目初始化与 CRUD

| 方法 | 端点 | 说明 | 权限 |
| --- | --- | --- | --- |
| POST | `/api/v1/spaces/creation-requests/` | payload 新增可选 `taxonomy_init_mode`（`default_seed`/`custom`/`none`；缺省按模板 profile，再缺省 `custom`） | 现行创建权限 |
| GET | `/api/v1/documents/taxonomy/dimensions/` | 按 `taxonomy_mode` 分流返回 | 空间成员 |
| POST | `/api/v1/documents/taxonomy/dimensions/` | mode=space 时创建空间私有维度（owner/knowledge_admin）；共享维度仍限平台管理员 | 见说明 |
| PATCH | `/api/v1/documents/taxonomy/dimensions/{id}/` | 更新 name/required/sort_order/status（归档）。私有维度限 owner/knowledge_admin；共享维度限平台管理员 | 见说明 |
| PATCH | `/api/v1/documents/taxonomy/terms/{id}/` | 更新 label/sort_order/status（归档），权限同其所属维度 | 见说明 |
| POST | `/api/v1/documents/taxonomy/seed-defaults/` | 事后一键导入默认科目预置（幂等，body: `{"preset": "audit_default"}`），仅 mode=space | owner/knowledge_admin |
| GET | `/api/v1/documents/taxonomy/presets/` | 预置科目目录（供创建向导预览科目树） | 认证用户 |

创建审批（`approve_creation_request`）建空间后：
- `default_seed` → `taxonomy_mode="space"` 并调用 `seed_space_taxonomy(space, preset)` 一次性复制预置为空间私有维度/术语；
- `custom` → `taxonomy_mode="space"`，不播种，空间管理员自建；
- `none` → `taxonomy_mode="none"`。

### 3.2 官方参考库

| 方法 | 端点 | 说明 | 权限 |
| --- | --- | --- | --- |
| GET/POST | `/api/v1/documents/libraries/` | 参考库管理列表 / 认证空间为参考库 | 平台管理员 |
| PATCH | `/api/v1/documents/libraries/{id}/` | 发布 / 下架 / 改名 | 平台管理员 |
| GET | `/api/v1/documents/libraries/catalog/` | 已发布参考库目录 | 认证用户 |
| GET/POST | `/api/v1/documents/library-references/` | 当前空间（X-Space-Id）的引用列表 / 添加引用 | GET 成员；POST owner/knowledge_admin |
| DELETE | `/api/v1/documents/library-references/{id}/` | 移除引用 | owner/knowledge_admin |

### 3.3 跨库检索（RAG）

- `PgVectorRetriever.search` 的 `space_id` 参数扩展为 `space_ids: list[str]`（保留 `space_id` 兼容入参），
  SQL 过滤改为 `dc.space_id IN (...)`；结果行附带 `space_id` 来源。
- `pipeline.answer` 检索前解析：主空间 + 该空间 `enabled=True` 且库 `status=published` 的引用库空间 id 列表。
- Prompt 构建：来自引用库的 chunk 标注 `[参考库: {library.name}]`，system prompt 引导 LLM
  "结合当前项目本地知识与参考库权威内容综合作答，冲突时说明差异"。
- Citations SSE 事件新增 `source_library` 字段（非引用库来源为 null）。
- 隔离保障：仅检索链路放开；文档列表、graph、timeline、dashboard、下载均保持单空间。
  未被引用/已下架/未发布的库绝不进入检索范围。

### 3.4 Obsidian 体验

| 方法 | 端点 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/documents/{id}/backlinks/` | 反链列表：`[{id, title, anchor_text, status, updated_at}]`（同空间） |
| GET | `/api/v1/documents/graph/?center=<doc_id>&depth=1..3` | Local Graph：以文档为中心的 BFS 邻域子图；不带 center 保持全局图 |

wikilink 解析复用现有 `apps/knowledge/links.py`（`[[标题]]` 与 `knowpilot://doc/<uuid>`），
在 PATCH text/ 与版本创建时已同步 `DocumentLink`。

## 4. 权限矩阵

| 操作 | 平台管理员 | 空间 owner/knowledge_admin | 空间成员 |
| --- | --- | --- | --- |
| 共享维度/术语 增改归档 | Y | N | N |
| 空间私有维度/术语 增改归档 | Y | Y | N |
| 导入默认科目（seed-defaults） | Y | Y | N |
| 参考库认证/发布/下架 | Y | N | N |
| 引用库添加/移除 | Y | Y | N |
| 参考库目录浏览 | Y | Y | Y |

## 5. 前端交互

1. **创建向导**（WorkspaceCreationPage）：新增"科目初始化"步骤，三选一卡片：
   - 使用默认科目一次性创建（展示预置科目树预览）；
   - 自定义科目（创建后在科目管理面板自建）；
   - 不需要科目（赋能团队等）。
   模板携带 `taxonomy_profile` 时预填，用户可覆盖。
2. **科目管理面板**（知识库页内，owner/knowledge_admin 可见）：维度/术语树增改归档、"导入默认科目"按钮。
3. **参考库**：平台管理员目录管理页；空间设置中勾选/停用引用库；ChatPage 显示生效引用库 chips，
   引用来自参考库的 citation 加库名徽标。
4. **Obsidian 体验**：
   - MarkdownEditor：编辑/分栏实时预览切换；`[[` 触发空间内文档标题自动补全；
   - BacklinksPanel：文档详情侧栏反链列表；
   - KnowledgeGraphPanel：Local Graph 模式（中心文档 + 深度滑杆 1-3 + 边类型开关），保留全局模式；
   - DiffPreview：词级高亮 + 并排/统一视图切换。

## 6. 验收标准

1. 创建空间选择"默认科目"后，空间内立即可见预置四维度（会计科目/财年/审计阶段/SCOT），且为空间私有可编辑。
2. 创建空间选择"不需要科目"后，维度列表为空，上传文档不再要求必填科目。
3. 存量空间（taxonomy_mode=inherit）行为与升级前完全一致。
4. 平台管理员发布 IFRS 参考库后，空间 owner 勾选引用，Chat 提问可召回参考库内容且 citation 带库名徽标；
   取消引用或库下架后立即不再召回。
5. 未引用空间的内容在任何情况下不会泄漏进检索结果（含 term/category 过滤组合）。
6. `[[` 补全可插入 wikilink，保存后 backlinks 与 Local Graph 的 link 边即时更新。
7. Local Graph depth=1 仅返回中心文档直接邻居；depth=3 返回三跳内子图。
8. 后端 pytest 全绿；前端 `npm run build` 通过；Docker 容器内迁移成功。

## 7. 实施顺序

- Phase 1（A+C）：模型/迁移 → 预置注册表 → taxonomy 视图分流与 CRUD → 创建流程 → enablement 模板。
- Phase 2（B）：参考库模型/API → retriever 多空间 → pipeline 标注与 citations。
- Phase 3（D+前端）：backlinks/local graph 后端 → 前端全部 UI。
- 每阶段完成后在 Docker 容器内执行迁移与测试再进入下一阶段。
