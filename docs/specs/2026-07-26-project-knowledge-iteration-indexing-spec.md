# KnowPilot 项目组级知识库迭代与索引系统 Spec

> 文档版本：v1.0
> 日期：2026-07-26
> 状态：已确认设计（Design Approved）
> 范围：项目组（工作区/space）级知识库的迭代更新系统 + AI 检索防幻觉索引系统
> 基线：以当前代码库实际实现为基准（backend/apps/knowledge、rag、spaces、chat、users）
>
> 关联文档：`docs/specs/project_team_knowledge_template_index_spec.md` 为早期产品视角草案（Draft），
> 本文档是其工程落地版本——凡两者冲突处以本文档为准；该草案中的项目创建向导、
> Tax/Deals/Consulting 模板骨架等内容不在本期范围。

---

## 0. 摘要与已确认决策

在现有底座（space 级检索硬隔离、文档版本链、混合检索 + 置信度拒答）之上，补齐五块能力：

1. **业务线发现层隔离**：注册业务线决定可见/可加入的工作区，检索仍保持 space 硬隔离；
2. **审计业务受控元数据 taxonomy**：会计科目 × FY × 审计阶段 × SCOT，标签维度而非目录树；
3. **知识迭代审批门禁**：空间级可配置，未审批不入 AI 索引 + 更新人水印；
4. **六层防幻觉索引策略**：准入 → 生效 → 新鲜度 → 检索 → 生成 → 评估闭环；
5. **可视化一期**：Local Graph、时间轴/更新热力、管理仪表盘（fork/分支列为二期预留）。

已与产品负责人确认的四项关键决策：

| 决策点 | 结论 |
|---|---|
| 业务线隔离语义 | **发现层隔离**——业务线决定用户能看到/申请加入哪些工作区；检索只在当前工作区内进行，space 硬隔离不放松 |
| 审计维度建模 | **受控元数据维度**——科目/FY/阶段/SCOT 是文档标签，可任意组合透视，不做目录树层级 |
| 审批门禁 | **空间级可配置**——`direct_publish` / `require_review` 二选一，默认 `require_review` |
| 可视化一期范围 | Local Graph + 时间轴/更新热力 + 管理仪表盘；fork/分支继承为二期预留 |

### 0.1 现状底座（不重复建设）

| 能力 | 现有实现 | 位置 |
|---|---|---|
| 空间检索硬隔离 | 检索 SQL 强制 `dc.space_id` 过滤 + `status='active'` + 生效期窗口 | `apps/rag/retriever.py` |
| 文档版本链 | `version` / `parent_document` / `superseded` 状态机、原子回滚、diff 预览 | `apps/knowledge/models.py`、`views.py` |
| 混合检索 | 向量(pgvector HNSW) + 全文(FTS) → RRF 融合 → 可解释重排 → 单文档限 2 块 | `apps/rag/hybrid.py` |
| 防幻觉基线 | 四档置信度、低置信硬拒答、citation 强制前置、注入清洗 | `apps/rag/pipeline.py`、`guardrails.py` |
| 业务线模型 | `BusinessLine`、`space.business_line` FK、`visibility=business_line` 枚举（未消费） | `apps/spaces/models.py` |
| 空间角色 | `SpaceMembership` 五档角色，含 `reviewer`（未使用） | `apps/spaces/models.py` |
| 摄取流水线 | IngestionJob 持久化 + Celery 重试 + 去重(content_hash) | `apps/knowledge/ingestion.py`、`apps/rag/services.py` |

### 0.2 现状差距（本 spec 要解决的）

1. 业务线三处存在但互不贯通：`user.service_line` 是字符串、检索/发现层完全不感知业务线；
2. 无审批流：reviewer 角色已定义但文档没有 `pending_review/approved` 状态机，任何人改了直接进索引；
3. 无审计业务 taxonomy：会计科目、FY、SCOT 概念完全不存在；
4. 无更新人水印/贡献者追溯（只有首版 `uploaded_by`）；
5. `freshness_score` 恒为 1.0，旧知识不衰减，`stale` 状态纯手工无自动化；
6. 无知识图谱/时间轴/仪表盘可视化。

---

## 1. 业务线发现层隔离

### 1.1 目标

用户注册时选择的业务线（Assurance/Tax/Consulting/S&T/Core）决定其能**发现和申请加入**
哪些工作区，从源头避免审计人员误入税务项目组知识库。检索层继续只在"当前激活工作区"内进行，
这是防幻觉的根基，任何情况下不放松。

### 1.2 数据模型变更

- `users.User` 新增 `business_line = FK(spaces.BusinessLine, null=True, on_delete=SET_NULL)`；
- 数据迁移：按 `service_line` 字符串 code 映射回填（五个 code 与 `seed_taxonomy.py` 的
  `SERVICE_LINES` 完全一致：assurance/consulting/tax/strategy_transactions/core）；
- `service_line` CharField 保留作过渡兼容（注册表单继续写两处，读取以 FK 优先）。

### 1.3 行为规则

| 场景 | 规则 |
|---|---|
| 空间发现列表（join_policy=global） | `visibility=business_line` 的空间仅对 `user.business_line == space.business_line` 的用户可见、可申请 |
| `visibility=organization` 空间 | 不受业务线限制（组织全员可见） |
| `visibility=private` 空间 | 维持现状（仅成员可见） |
| access code / 邀请加入 | **跨线逃生门**：显式授权即视为合法，可跨业务线加入（保持现有机制不变） |
| Org Admin / 超管 | 可管理跨线豁免、查看全部空间 |
| 检索 | 零改动——`PgVectorRetriever`/`HybridRetriever` 继续强制 `space_id` 过滤 |

### 1.4 管理员视角

- 平台控制台增加业务线维度报表：各业务线空间数、成员数、跨线成员清单
  （复用 `AuditLog.business_line_id` 已有维度，无需新审计字段）；
- 空间创建/编辑表单中 `visibility=business_line` 选项开始真正生效（此前为死枚举）。

---

## 2. 审计业务受控元数据 Taxonomy

### 2.1 设计原则

**标签维度，不是目录树。** 同一份文档可以同时属于 `FY26 + 应收账款 + 年审 + 收入循环`，
用户按任意维度组合透视导航。目录树方案会随财年增长爆炸、且单文档无法跨维度归属，已否决。

### 2.2 新数据模型（backend/apps/knowledge）

```
TaxonomyDimension                      # 受控维度定义
├── id: UUID
├── organization: FK(Organization)
├── business_line: FK(BusinessLine, null=True)   # 空 = 组织级通用维度
├── code: Slug                        # e.g. "account", "fiscal_year", "audit_phase", "scot"
├── name: Char                        # e.g. "会计科目"
├── is_hierarchical: Bool             # 科目=True, FY=False
├── required: Bool                    # 上传时是否强制选择
├── sort_order: Int
└── status: active | archived

TaxonomyTerm                           # 维度下的受控词
├── id: UUID
├── dimension: FK(TaxonomyDimension)
├── parent: FK(self, null=True)       # 层级支持（科目：流动资产 > 货币资金）
├── code: Slug                        # e.g. "accounts_receivable", "fy26"
├── label: Char                       # e.g. "应收账款"
├── sort_order: Int
└── status: active | archived
    约束：unique(dimension, code)

DocumentTag                            # 文档 ↔ 词 多对多
├── id: UUID
├── document: FK(Document)
├── term: FK(TaxonomyTerm)
├── tagged_by: FK(User, null=True)
└── created_at
    约束：unique(document, term)

TermOwnership                          # 科目负责人（可选启用）
├── id: UUID
├── space: FK(KnowledgeSpace)
├── term: FK(TaxonomyTerm)
├── owner: FK(User)                   # 必须是该空间 active 成员
└── created_at
    约束：unique(space, term, owner)
```

### 2.3 审计线预置维度（seed 脚本扩展）

| 维度 code | 名称 | 层级 | 必填 | 预置词示例 |
|---|---|---|---|---|
| `account` | 会计科目 | 是 | 是 | 货币资金、应收账款、存货、固定资产、无形资产、应付账款、收入、成本费用、所得税、权益 |
| `fiscal_year` | 财年 | 否 | 是 | FY24、FY25、FY26、FY27 |
| `audit_phase` | 审计阶段 | 否 | 否 | planning（计划）、interim（中期审计）、year_end（年审）、completion（完成阶段） |
| `scot` | SCOT 流程 | 否 | 否 | 收入循环、采购与付款循环、薪酬循环、存货与成本循环、资金循环、财报编制流程 |

其他业务线各自定义维度模板（税务：税种/年度/法规版本；咨询：行业/方法论）。
`ScenarioTemplate` 应用时（audit/tax/consulting 场景）自动预置对应维度与词表；
每年新增 FY 词条为管理员一键操作，不产生任何结构性迁移。

### 2.4 与检索的贯通

- ingest 时（`RAGPipeline.ingest` / `ingest_text_content`）在 `DocumentChunk.metadata`
  冗余写入 term codes：`{"terms": ["fy26", "accounts_receivable", "revenue_cycle"]}`；
- 文档标签变更后无需重嵌入，仅同步更新其 chunks 的 metadata（一条 UPDATE，向量不变）；
- 检索过滤见 §4 L4。

### 2.5 用户视角 UI（KnowledgeBasePage 改造）

- 左侧多维筛选面板：科目 × FY × 阶段 × SCOT 复选组合，实时过滤文档表格；
- 上传/新建/编辑时的标签选择器（`required=True` 维度强制选择，否则不允许提交）；
- "我负责的科目"快捷视图：`TermOwnership` 命中的 term 一键过滤 + 陈旧/待审批徽标；
- 文档表格新增"标签"列（Tag 组件按维度着色）。

---

## 3. 知识迭代审批门禁 + 更新人水印

### 3.1 空间级审批策略

- `KnowledgeSpace` 新增 `review_policy = Char(choices=["direct_publish", "require_review"], default="require_review")`；
- 存量空间迁移默认值取 `direct_publish`（不改变既有空间行为，避免上线即卡审批）；
  新建空间默认 `require_review`；
- 空间设置页（owner/knowledge_admin 可改）暴露该开关，变更写 AuditLog。

### 3.2 文档状态机扩展

`Document.STATUS_CHOICES` 增加 `pending_review`、`rejected`：

```
                    require_review 空间
draft ──提交──► pending_review ──批准──► active（此刻才 chunk+embed 入索引）
                     │
                     └──驳回──► rejected（可修改后重新提交）

                    direct_publish 空间
draft ──发布──► processing ──► active        # 现有流程不变
```

关键不变量：
- **`pending_review` / `rejected` / `draft` 状态的文档永远没有可检索 chunk**——
  批准动作才触发 `enqueue_document_ingestion`（或版本切换事务内的 `ingest_text_content`）；
- 版本迭代：`DocumentVersionCreateView` 在 require_review 空间下创建的新版本落
  `pending_review`，**旧 active 版本继续服务检索**，直到新版本获批准才被标 `superseded`
  并删除旧 chunks（复用现有原子版本切换事务，只是把触发点从"创建"移到"批准"）；
- `superseded` / `expired` / `stale` 语义不变。

### 3.3 ReviewRequest 模型

```
ReviewRequest
├── id: UUID
├── space: FK(KnowledgeSpace)          # 冗余，便于审批队列按空间过滤
├── document: FK(Document)             # 待批准的具体版本
├── submitted_by: FK(User)
├── reviewer: FK(User, null=True)      # 认领/指派后填充
├── diff_summary: JSON                 # 提交时的行级 diff 快照（复用 preview-diff 逻辑）
├── conflict_hints: JSON               # L1 冲突检测结果（见 §4）
├── decision: pending | approved | rejected
├── comment: Text
├── decided_at: DateTime(null)
└── created_at / updated_at
    约束：CheckConstraint(reviewer != submitted_by)   # 职责分离，与工作区创建审批同一政策基因
    约束：每个 document 至多一条 pending 的 ReviewRequest
```

审批权限：空间内 `reviewer` / `knowledge_admin` / `owner` 角色可批准/驳回；
超管保留绕过通道（与工作区审批的超管绕过机制一致）。

### 3.4 通知与审计

- 通知（复用 `apps/notifications`）：提交 → 通知空间 reviewers + 该文档 term 负责人；
  批准/驳回 → 通知提交人；
- `AuditLog.ACTION_CHOICES` 增加：`document_review_submit`、`document_review_approve`、
  `document_review_reject`。

### 3.5 更新人水印与贡献者追溯

- `Document` 新增 `updated_by = FK(User, null=True, on_delete=SET_NULL)`——
  版本创建者（版本链中每个 Document 行记录自己的作者）；`uploaded_by` 保留为该版本上传人语义不变；
- 序列化器输出 `contributors`：沿 `parent_document` 版本链回溯去重的 `{user, version, date}` 列表；
- 前端水印展示 `v{N} · {更新人} · {日期}`，出现在四处：文档列表行、版本管理 Drawer、
  diff 预览头部、chat 引用卡片；
- citation 数据结构（`RAGPipeline._build_citations`）增加 `version`、`updated_by_name`、
  `updated_at` 三个字段——AI 每条引用都自带水印，回答可追溯到"谁在什么时候写的哪个版本"。

---

## 4. 防幻觉索引系统（六层）

> 核心思路：幻觉不是单点问题，必须在知识生命周期每一层设闸。
> 已有能力标注（已有），新增能力标注（新增）。

### L1 准入层——错的进不来

- （已有）content_hash SHA256 去重，重复文件直接拒绝；
- （已有）审批门禁（§3）：未经复核的内容不产生向量；
- （新增）**冲突检测**：提交审批时异步任务对新版本 chunks 与本空间既有 active 文档做
  相似度扫描（复用 pgvector，top-5 相似 chunk 且 score > 0.85），结果写入
  `ReviewRequest.conflict_hints`；审批界面提示"内容与《X》高度重叠，可能冲突或应替代它"，
  reviewer 可在批准同时一键将旧文档标记 `superseded` 或 `stale`。

### L2 生效层——过期的不服务

- （已有）`superseded` 排除、`effective_from/to` 日期窗口过滤、未来版本调度；
- （新增）**FY 维度感知降权**：查询中识别出 FY 实体（如"FY26"）时，携带其他 FY 标签的
  文档在重排序中乘以 0.6 降权系数（不硬排除——历史财年知识仍可显式查询）。

### L3 新鲜度层——旧的自动衰减

- （新增）启用 `freshness_score`（现恒为 1.0）：
  `freshness = 0.5 ** (days_since_updated / half_life_days)`，半衰期空间可配
  （`KnowledgeSpace.settings["freshness_half_life_days"]`，默认 365）；
  重排权重公式不变（fused 55% + evidence 35% + freshness 10%），只是 freshness 开始真实取值；
- （新增）**stale 自动化**：Celery Beat 定时任务扫描超过 N 天（空间可配，默认 540 天）
  未更新且未复核的 active 文档 → 自动置 `stale` + 通知 term 负责人；
  负责人"确认仍有效"操作可重置计时（记录 `last_reviewed_at`，Document 新增该字段）；
- （新增）stale 文档不移出索引但检索降权（freshness 减半），citation 上带
  "内容可能过期"徽标，让用户对答案证据的新鲜度有知情权。

### L4 检索层——找得准

- （新增）`RetrievalFilters` 增加 `term_codes: tuple[str, ...]`，SQL 过滤
  `dc.metadata @> '{"terms": [...]}'::jsonb`（GIN 索引支持）；
- （新增）**轻量查询理解**：正则 + 空间词表匹配 query 中的 FY/科目/SCOT 实体
  （如"FY26 应收账款函证怎么做"→ 命中 fy26 + accounts_receivable），
  命中即注入 term 加权（重排序中同 term chunk 加 0.1 分）而非硬过滤，避免召回归零；
- （已有）RRF 融合 + 单文档限 2 块的多样性约束保持不变。

### L5 生成层——答得有据

- （已有）低置信硬拒答、citation 前置、prompt 明令"仅基于上下文、必须引用、绝不编造"；
- （新增）prompt 增加冲突处理规则："若上下文文档之间存在冲突，明确指出冲突，
  并优先引用版本较新/生效中的文档"；
- （新增）citation 带版本号与水印（§3.5），回答中的引用编号与 citation 一一对应（现有机制保留）。

### L6 评估闭环层——缺口看得见

- （新增）管理仪表盘聚合（数据源均已存在：quality SSE 事件落库的置信度、
  feedback/knowledge_gap 审计动作）：
  - 拒答率、置信度分布按空间/按周趋势；
  - feedback 与 knowledge_gap 按 taxonomy 维度聚合 →"哪个科目/SCOT 的知识缺失或陈旧"；
  - 形成迭代闭环：**用户提问暴露缺口 → 定位到科目负责人 → 补充/更新 → 审批入索引 → 拒答率下降**。

---

## 5. 可视化（一期）

### 5.1 Local Graph（知识图谱）

- API：`GET /api/v1/spaces/{space_id}/knowledge/graph/`，返回：
  - 节点：文档 `{id, title, terms, freshness, status, version, chunk_count}`；
  - 边（三类，带 type 与 weight）：
    1. `term`——共享同一 taxonomy term（科目/SCOT 优先，FY 边默认关闭避免全连接）；
    2. `link`——文档 markdown `text_content` 中的显式链接/`[[wiki link]]` 解析（ingest 时提取存表 `DocumentLink(source, target, anchor_text)`）；
    3. `similar`——chunk embedding 相似度 top-k 文档对（离线任务预计算，score > 0.8）；
- 前端：力导向图（react-force-graph，轻量、与 React 18 兼容；不引入重量级 G6）；
  节点大小 = 被引用次数（DocumentLink 入度 + chat citation 次数），颜色 = 新鲜度渐变；
  点击节点高亮邻居 + 右侧栏文档预览；支持按维度过滤子图（选中"应收账款"只看该科目局部图）；
- 页面位置：知识库页新增 "图谱" Tab（`/workspace/:spaceId/knowledge` 内，
  遵守知识库与工作空间管理分离原则，不进管理控制台布局）。

### 5.2 时间轴 / 更新热力

- 空间级：按月聚合的版本活动热力条（类 GitHub contribution graph），
  数据源 `Document.created_at` 按版本行聚合，一条聚合查询即可；
- 文档级：版本链时间线（数据已有：version/parent_document/created_at/updated_by），
  每个节点显示水印，点击任意两版本可看 diff（复用 DiffPreview 组件）；
- FY 视角：时间轴可按 `fiscal_year` 标签分泳道，直观看到 FY25 → FY26 的知识演进断层。

### 5.3 管理仪表盘（admin 视角）

单页四区块（空间管理侧，owner/knowledge_admin/reviewer 可见）：
1. **审批队列待办**：pending ReviewRequest 列表 + 冲突提示徽标 + 一键进入 diff 审批；
2. **覆盖度矩阵**：term × 文档数/平均新鲜度 热力格——一眼看出"存货科目 FY26 还没有任何知识"；
3. **陈旧预警**：stale 文档、30 天内 `effective_to` 到期文档列表，可直接指派给 term 负责人；
4. **质量指标**（L6）：拒答率趋势、置信度分布、knowledge_gap 科目排行。

### 5.4 二期预留：Fork / 分支继承（本期只定义概念，不实现）

- 场景：FY26 年审结束 → 一键将选定文档集 fork 到 FY27（新版本链起点，
  `forked_from` 溯源 FK，标签自动替换 fy26 → fy27，状态落 draft 待更新确认）；
- 与现有版本链正交：版本链是"同一文档的时间演进"，fork 是"跨财年的谱系复制"；
- 差异对比视图：FY27 文档与其 forked_from 源的 diff。

---

## 6. 双视角旅程

### 6.1 管理员视角（owner / knowledge_admin / org admin）

1. （组织级）维护业务线维度词表：新增 FY27 词条、调整科目层级、归档废弃 SCOT；
2. （空间级）设置审批策略 `require_review`、新鲜度半衰期、stale 阈值；
3. 指派科目负责人（TermOwnership）：把"应收账款"指给张三、"存货"指给李四；
4. 处理审批队列：看 diff + 冲突提示 → 批准（自动入索引）/ 驳回（附意见）；
5. 仪表盘监控：覆盖度矩阵找知识空白、陈旧预警派单、拒答热点定位缺口科目；
6. （平台级）业务线报表：各线空间数、跨线成员审查。

### 6.2 用户视角（member / 项目组审计员）

1. 注册选业务线（Assurance）→ 只能发现/申请本线的项目组工作区；跨线需邀请码；
2. 加入项目组空间 → 知识库页按 科目 × FY × 阶段 × SCOT 筛选浏览；
3. 认领/被指派负责科目 → "我负责的科目"视图集中管理，收到陈旧提醒；
4. 更新知识：在线 Markdown 编辑或上传文件 → 强制打标签（科目+FY）→ 提交审批；
5. 审批通过 → 新版本带水印 `v3 · 张三 · 2026-07-26` 进入 AI 索引，旧版本自动 superseded；
6. chat 提问"FY26 应收账款函证流程" → AI 命中 FY/科目实体加权检索 →
   引用卡片显示来源文档 + 版本 + 更新人水印 + 新鲜度徽标；证据不足时明确拒答；
7. 图谱 Tab 探索科目知识关联，时间轴查看知识演进与断层。

---

## 7. 数据模型变更清单

| 模型 | 变更 | 说明 |
|---|---|---|
| `users.User` | 新增 `business_line` FK | service_line 字符串保留过渡 |
| `spaces.KnowledgeSpace` | 新增 `review_policy` | 存量迁移默认 direct_publish，新建默认 require_review |
| `knowledge.Document` | status 增加 `pending_review`/`rejected`；新增 `updated_by` FK、`last_reviewed_at` | 状态机扩展见 §3.2 |
| `knowledge.TaxonomyDimension` | 新建 | §2.2 |
| `knowledge.TaxonomyTerm` | 新建 | §2.2 |
| `knowledge.DocumentTag` | 新建 | §2.2 |
| `knowledge.TermOwnership` | 新建 | §2.2，可选启用 |
| `knowledge.ReviewRequest` | 新建 | §3.3，含 reviewer != submitted_by 约束 |
| `knowledge.DocumentLink` | 新建 | §5.1，markdown 显式链接解析结果 |
| `knowledge.DocumentChunk` | `metadata` 冗余 terms + GIN 索引 | 无需重嵌入 |
| `audit.AuditLog` | ACTION 增加 3 个 review 动作 | §3.4 |

## 8. API 变更清单（均挂现有前缀）

| 方法与路径 | 用途 | 权限 |
|---|---|---|
| `GET/POST /api/v1/documents/taxonomy/dimensions/` | 维度 CRUD | knowledge.manage（写）/ read（读） |
| `GET/POST /api/v1/documents/taxonomy/terms/` | 词表 CRUD（按 dimension 过滤） | 同上 |
| `PUT /api/v1/documents/{id}/tags/` | 覆盖式设置文档标签 | knowledge.manage |
| `GET/POST /api/v1/spaces/{id}/term-owners/` | 科目负责人指派 | 空间 owner/knowledge_admin |
| `POST /api/v1/documents/{id}/submit-review/` | 提交审批（生成 ReviewRequest + diff 快照 + 触发冲突检测） | 空间成员（可写） |
| `GET /api/v1/spaces/{id}/review-queue/` | 审批队列（按 decision 过滤） | reviewer/knowledge_admin/owner |
| `POST /api/v1/reviews/{id}/approve/` | 批准（原子版本切换 + 入索引） | 同上，且 != 提交人 |
| `POST /api/v1/reviews/{id}/reject/` | 驳回（附意见） | 同上 |
| `PATCH /api/v1/spaces/{id}/`（扩展） | review_policy / 新鲜度参数设置 | owner/knowledge_admin |
| `GET /api/v1/spaces/{id}/knowledge/graph/` | Local Graph 节点边 | knowledge.read |
| `GET /api/v1/spaces/{id}/knowledge/timeline/` | 空间级活动聚合 | knowledge.read |
| `GET /api/v1/spaces/{id}/knowledge/dashboard/` | 覆盖度/陈旧/质量聚合 | reviewer/knowledge_admin/owner |
| `POST /api/v1/documents/{id}/confirm-fresh/` | 负责人确认仍有效（重置 stale 计时） | term 负责人/knowledge_admin |
| 空间发现相关（扩展现有 endpoint） | 业务线过滤 | 现有权限不变 |

## 9. 分期实施计划

| Phase | 内容 | 依赖 |
|---|---|---|
| **Phase 1** | 业务线打通（User FK + 发现层过滤）；taxonomy 四模型 + seed + 打标 UI + 筛选面板；审批流（review_policy + 状态机 + ReviewRequest + 队列页）；水印（updated_by + contributors + 四处前端展示） | 无 |
| **Phase 2** | 防幻觉索引增强：freshness 启用、stale 自动化任务、term_codes 检索过滤 + GIN 索引、查询理解、冲突检测、citation 版本化、FY 降权 | Phase 1（taxonomy） |
| **Phase 3** | 可视化三件套：Local Graph（DocumentLink 解析 + 相似度预计算 + 力导向图）、时间轴、管理仪表盘 | Phase 1/2（数据源） |
| **Phase 4（预留）** | fork/分支继承、业务线共享知识池（二级检索来源）、跨空间图谱 | Phase 1-3 |

每个 Phase 完成标准：后端单测通过 + Docker 重建前端镜像后 browser-use 浏览器可视化验证通过
（项目规则强制），未通过验证不得标记完成。

## 10. 风险与对策

| 风险 | 对策 |
|---|---|
| 存量空间被审批流卡住 | 存量迁移 review_policy 默认 direct_publish，仅新空间默认 require_review |
| 强制打标降低上传意愿 | 仅 required=True 维度强制（科目+FY），批量上传支持 ZIP 级统一预设标签 |
| 冲突检测误报打扰 reviewer | 仅作提示（conflict_hints），不阻断审批；阈值 0.85 可配 |
| 查询理解误过滤导致召回归零 | 实体命中只加权不硬过滤（L4 设计决策） |
| 图谱边计算开销 | similar 边离线预计算 + 结果缓存；term/link 边为纯关系查询 |
| pending 版本期间旧版本继续服务 | 明确为设计意图（可用性优先），审批界面显著提示"当前线上仍为 v{N-1}" |
