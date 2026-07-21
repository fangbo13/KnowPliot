# KnowPilot 后 V3：RAG 效率与知识库版本化编辑 SPEC

> 日期：2026-07-19
> 状态：KB 版本化编辑部分 = 已确认设计、待实现（post-v3）；RAG 效率部分 = 调研路线、measure-first gate 未过前不实现
> 基线：`fix/v1.74.1-acceptance-bugs` / `82231f5`；目标实现排在 V3 内测 SPEC 稳定之后
> 上位：`docs/specs/2026-07-16-knowpilot-optimization-spec.md` v3、`docs/superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md`
> 本文由 brainstorm 阶段产出；实现交 Claude，按本文 + 上位 SPEC 约束执行

本文分五部分：**Part 1** 已确认、可实施的"知识库版本化内容编辑 + 差异预览 + 创建流（多格式上传 + 输入框 + `text_content` 规范 MD）"设计；**Part 2** "RAG 效率问题盘点 + 解法路线"（调研性，measure-first gate 前不实现）；**Part 3** 思考期"内心独白"显示（reasoning-phase display，复用 `streamPhase`，SPEC 兼容，无计时/无原始 CoT）；**Part 4** 中英文区 / AI 答复语言（bilingual，查询语言检测 + 空间 `default_language` + 用户偏好，不再硬编码 en）；**Part 5** 横切约束。

---

## Part 1 — 知识库版本化内容编辑 + 差异预览（已确认设计）

### 1.1 目标与非目标
**必须实现**：
1. 用户可在工作空间 Knowledge 页**内联编辑**文档正文（markdown），保存即生成**新版本**，旧版本按审计保留、可回滚。
2. 编辑提交前提供 **old vs new 行级差异预览**，确认后才落库。
3. 检索**只使用当前生效版本**的 chunks；旧版 chunks 不参与检索，避免矛盾/陈旧内容污染答案。
4. 支持**立即生效**（默认）与**排期生效**（`effective_from` 设未来日期）。
5. binary 文档（PDF/DOCX）编辑"提取文本"而非原文件；原文件保留为 source。

**不做**：
- 不做 chunk 级编辑（粒度太细、一致性复杂；本期只做文档级版本化）。
- 不做原文件级编辑（不在浏览器内编辑 PDF/DOCX 二进制）。
- 不删除兼容期既有 `reindex`/`PATCH 元数据`/`GET chunks` 端点（保留，版本化在其上扩展）。
- 不在本期做"检索测试预览"（针对单文档提问验证可被检索）——列为后续。

### 1.2 数据模型
- `Document` 新增 `text_content: TextField`（可编辑正文；上传/ingest 时从文件提取——md/txt=文件内容，PDF/DOCX=提取文本）。
- 复用既有：`version`、`parent_document`（版本谱系，SET_NULL）、`effective_from`/`effective_to`（生效期）、`content_hash`（去重）、`status`。
- **chunks 只留当前生效版本在 live 检索索引**（关键不变量，见 1.5）：旧版 chunks 在版本切换时**从 live 索引删除**（a1 决策：不留旧版 chunks/embedding，回滚时重新 chunk+embed；迁冷表是 a2 不在本期）；旧版的 `text_content` + 元数据 + 版本谱系**保留**（审计/回滚）。
- 新版本创建：`parent_document=旧版`、`version=旧版.version+1`、`effective_from=now`（默认）或用户指定未来日期；旧版 `effective_to=新版.effective_from`。

### 1.3 编辑流程
1. Knowledge 页 → 打开文档 → 内联 markdown 编辑器载入 `text_content`。
2. 用户编辑 → 点"预览差异"→ 后端返回 old `text_content` vs new 行级 diff。
3. 用户确认 → "保存为新版本"→ 后端在同一事务内：
   - 创建新 `Document`（`parent_document=旧版`、`version+1`、`effective_from`、`effective_to=null`、`text_content=new`）。
   - 旧版 `effective_to = 新版.effective_from`；旧版 status 标记 `superseded`。
   - 对新 `text_content` re-chunk + re-embed（新 chunks 进 live 索引）。
   - **旧版 chunks 从 live 索引删除**（a1 决策，不迁冷表；旧版 `text_content`+元数据留存）。
   - audit 事件（`document_version_created`：actor/when/旧版id/新版id/reason）。
   - `select_for_update(of=("self",))` 锁 Document 行（防并发版本竞争）。

### 1.4 差异预览（diff）
- 端点：`POST /api/v1/documents/{id}/preview-diff/` body `{text_content: new}` → 返回行级 diff（unified 或 side-by-side 结构化）。
- 不落库、不 embed（纯文本 diff，省成本）。
- 仅 `document.update`/`create_version` 权限可调。

### 1.5 检索语义（关键不变量）
- `HybridRetriever.search` 只检索**当前生效版本**的 chunks：`Document.status != superseded` AND `effective_from ≤ now ≤ effective_to`（或最新未废弃）。
- 旧版 chunks **不在 live 索引**（1.2/1.3 保证）→ 零矛盾/陈旧污染。
- **必须真实 PostgreSQL 验证**（条件过滤 + 索引 + 并发版本切换）；SQLite 不能替代。
- 回归测试：旧版 chunks 不被检索（防"干扰"——这是 brainstorm 中确认的核心顾虑）。

### 1.6 回滚
- "提升旧版为当前"：取旧版 `text_content` → 作为新版本 re-chunk+re-embed（走 1.3 同流程，`parent_document` 链保持）。
- 回滚是低频操作，重新 chunk+embed 可接受（故旧版只留文本+元数据、不留 chunks，省存储——a1 决策）。

### 1.7 生效期
- 默认 `effective_from=now`（立即生效，检索立即切新版）。
- 支持排期：`effective_from` 可设未来日期；该日前检索仍用旧版（`effective_to` 未到），到日自动切新版。
- 检索过滤统一按 `effective_from ≤ now ≤ effective_to`（无未来版的当前版 = 最近未废弃且 effective_to 为 null 或 ≥now 的最新版）。

### 1.8 权限
- 编辑/创建版本/预览差异：`knowledge_admin` + `space owner`（已有 `document.update`/`create_version`/`document.read_chunks` 能力，SPEC §6）。
- 普通成员/访客不可编辑（只读）。

### 1.9 binary 文档
- 编辑"提取文本"（`text_content`），不编辑原文件；原 `file` 保留为 source（可下载）。
- 上传新 binary 文件 = 新版本（提取→`text_content`→diff→确认→re-chunk+re-embed），走同一版本流程。

### 1.10 API 端点（新增 + 复用）
- 新增：
  - `PATCH/POST /api/v1/documents/{id}/text/`（编辑 text_content，暂存待预览）
  - `POST /api/v1/documents/{id}/preview-diff/`（差异预览，不落库）
  - `POST /api/v1/documents/{id}/versions/`（保存为新版本，事务内 re-chunk+re-embed + 旧版 chunks 移除 + audit）
  - `POST /api/v1/documents/{id}/rollback/`（提升指定旧版为当前新版本）
- 复用：`GET /documents/{id}/chunks/`（看当前版 chunks）、`POST /documents/{id}/reindex/`（重新 embed 当前版）、`PATCH /documents/{id}/`（元数据）、batch upload。

### 1.11 迁移
- `knowledge.00XX_add_document_text_content`：add `Document.text_content`（nullable → 回填从现有 file 提取 → non-null）。
- `knowledge.00XX_version_status`：add `superseded` to `status` choices；回填旧版状态。
- 依赖：在 V3 migration 序列之后。
- **PostgreSQL 验证**：`select_for_update(of=("self"))` 版本竞争 + 条件过滤 + 索引。

### 1.12 测试（TDD，必含）
- 编辑→新版本创建，旧版 `superseded` + `effective_to` 正确。
- diff 预览不落库、不 embed。
- **检索只命中当前生效版 chunks；旧版 chunks 零命中**（防干扰，核心）。
- 排期生效：未来版生效日前检索仍用旧版，到日切新版。
- 回滚：旧文本→新版本，链路正确。
- 并发编辑同一文档：`select_for_update(of=("self"))` + 版本号竞争，无双版本。
- binary 文档：编辑提取文本，原文件保留。
- audit：版本谱系 + actor/when/reason。
- 权限：member/guest 403；knowledge_admin/owner 200。

### 1.13 SPEC 约束（不可违反）
- §4/§5 固定安全相位（编辑是知识管理动作，非 chat 相位；但版本切换触发 re-chunk+re-embed 走 ingest 相位）。
- §6 四级能力矩阵 + scope 隔离（编辑限本空间 knowledge_admin/owner）。
- §7 不暴露 provider reasoning（re-embed 不外泄）。
- §13 迁移 additive + PostgreSQL 真实性。
- §16 单空间检索隔离（版本化不跨空间）。
- 数据保留（§10）：旧版 text_content+元数据不随版本切换删除（审计留存）。
- 审计/幂等/并发：版本创建带 Idempotency-Key + audit + `select_for_update(of=("self"))`。

### 1.14 创建流（与版本化编辑统一）

**两入口**：
1. **输入框/内联编辑器**（粘/打 MD）——主入口，快速精编条目（FAQ/简短政策/笔记），无文件。
2. **上传文件**（PDF/DOCX/MD/TXT）——次入口，自动提取到 `text_content`（MD），上传后可再编辑。

两路都产出 `text_content`（规范 MD），版本化/diff/检索都基于它（1.2–1.7 不变）。

**模型**：`Document.file` 改 **nullable**（输入框创建无文件）；`text_content` 总填充（文件提取 或 直接输入）→ chunk+embed 基于 `text_content`，不再只基于 `file`。

**不限制上传格式**（保留多格式 ingest 能力）；MD 是"可编辑规范态"。

权限：`document.create`（knowledge_admin/owner）。

测试：输入框创建无 file、`text_content` 直接 chunk+embed；上传 PDF→提取 `text_content`→可编辑；两路都走版本化（新版本/旧版隐藏/生效期）。

---

## Part 2 — RAG 效率问题盘点 + 解法路线（调研性，measure-first）

### 2.1 根因
"检索-生成"是一条**无智能决策的固定流水线**——不判断要不要检索、不判断检索够不够、不压缩不缓存、不分级不监控。"资源浪费"（无脑先检索）只是表面症状。

### 2.2 现状事实（已核查）
- 检索范围：单空间隔离（`hybrid.py` filter space_id；SPEC §16）。
- 方案：retriever（无脑先检索），非 tool-calling（无 `tools=`/`functions=`/`langgraph`；langgraph 是死依赖）。
- 不自判"要不要检索"：pipeline 只查注入（guardrails）+ 故障降级；对寒暄/元/超范围一律检索。

### 2.3 问题盘点（6 类，均未实现/未优化）
- **A 效率/成本**：重复查询无语义缓存；对话历史每轮全量回传 LLM（O(n) token）；过检索+低阈值(0.30)喂噪声；无上下文压缩/去重；流式不随客户端断开终止；无答案缓存。
- **B 检索质量/正确性**：0/低质检索仍生成（幻觉风险）；无 citation grounding 校验；无查询改写/HyDE；chunk 粒度固定 500/50；embedding 版本未管控；query/doc embedder 需确认一致。
- **C 可扩展性**：SSE 占 worker 线程（2×8=16 并发上限）；pgvector 单大索引按 space 过滤（大空间慢）；DashScope 限流无 batch/队列；Redis lease 180s 上限。
- **D 可观测**：metrics 有但无 dashboard/告警；无端到端 tracing；无成本计量；无检索质量漂移检测。
- **E 安全/隐私**：prompt injection 防护强度未知（需红队）；chat 外发 DashScope（敏感空间内容离开组织，SPEC 未涉 on-prem 模型路由）；跨空间向量泄漏回归风险；长历史敏感前文累积外发。
- **F 知识库/索引健康**：文档更新无自动重索引（`mark_stale_documents` 存在但是否触发？）；无索引一致性校验；无去重；冷启动。

### 2.4 解法路线（按性价比，非 tool-calling）
1. **规则路由层**（最便宜先做）：检索前规则识别寒暄/元/超范围→跳过检索直答；知识查询照常。~0 成本。
2. **Semantic Cache**（知识产品 ROI 最高）：`(space_id, query_embedding)` 缓存**检索到的 chunk id 列表**（不缓存答案）；命中→跳过 pgvector 检索复用 chunks，LLM 照常生成。复用 Redis（已有）；需失效钩子（doc ingest/delete + 版本切换清该空间缓存，与 Part 1 版本化联动）+ TTL。
3. **Adaptive/CRAG**（后期）：检索后给 chunk 打分，低质→改写重检索/拒答。
4. **不上 tool-calling**（`create_retriever_tool`）：每问多一次 LLM 决策往返 + agentic 循环 + 与 §4/§5/§7"无原始 reasoning"冲突；单轮知识问答用不上，留给未来多步检索。

### 2.5 measure-first gate（实现前必过）
- 先给 `ChatTurn` 加指标：`retrieval_result_count`、`query_near_dup`（近重复检测）、`cache_hit`、`routing_decision`、`retrieval_skipped_ms`。
- 跑一周采集：0/低质检索率、近重复率、寒暄/元占比、per-space 查询分布。
- **数据确认 ROI 后**再实现（规则路由先、semantic cache 后）；ROI 不显著则不建。

### 2.6 时机
- **排 V3 稳定之后**：V3 正在实施且 PostgreSQL 崩在迁移 0011/0012/0014/0016（`%` 转义 bug），别往 chat 路径叠第 4 个变更。
- Part 1（KB 版本化）与 Part 2（RAG 效率）可并行（不同路径），但都 post-v3。
- Part 1 的版本切换失效语义缓存（2.4.2 失效钩子）——两者有联动点，实现时对齐。

---

## Part 3 — 思考期"内心独白"显示（reasoning-phase display）

### 3.1 目标与非目标
**必须实现**：
1. 思考开关 ON 时，AI 给出最终回复前，前端展示**渐进式"内心独白"**（像 Claude Code 的 thinking 面板），让用户有心理预期（知道在思考而非卡死）。
2. 后端 SSE `phase` 事件在 reasoning 期发**多条渐进安全标签**（检索→分析→组织…），前端渐进渲染。
3. 全程**安全**：标签为服务端合成的白名单高层相位，**非模型 reasoning_content 原文**。

**不做**：
- **不加计时数字**（负作用——制造焦虑，已决）。
- **不流原始 CoT/reasoning_content**（SPEC §7/§15.2 红线：raw reasoning NEVER in SSE/browser）。
- 思考 off 时不显示内心独白（直接答案流）。

### 3.2 现状（已在仓库，复用复活）
- `frontend/src/store/chatStore.ts:122` `StreamPhase = 'idle'|'connecting'|'searching'|'streaming'|'completing'|'error'`（V3.5 统一状态机，替换旧 `isStreaming`+`thinkingPhase`+`connectionStatus`）。
- `SafeProcessingPhase = 'accepted'|'searching'|'generating'|'finalizing'`（§5 安全相位）。
- `deriveStreamPhase(phase)` 把后端 SSE `phase` 映射到 `streamPhase`/`safePhase`。
- `ChatPage` 有 `gemini-status-indicator` + `visibleAiStatusText`（流式状态胶囊）。
- 历史：v3.1 `THINKING_THRESHOLD`(10s)+`thinkingShown`"仍在思考中…"注入（已移除）；v3.3 `thinkingPhase`（connecting→searching→generating）；v3.5 统一为 `streamPhase`。

**当前缺口**：单条状态胶囊，非渐进式"内心独白"。

### 3.3 设计
- **后端**（`apps/chat/views.py` SSE + `apps/rag/guardrails.py`）：思考开关 on 时，reasoning 阶段经 SSE `phase` 事件发**多条渐进安全标签**（白名单）：`检索知识库…`→`分析相关文档…`→`组织答案…`。标签由服务端从管线实际状态合成（检索完成→分析→生成），**非模型 reasoning_content**（reasoning_content 服务端瞬态消费、不外泄，§7/§15.2）。
- **前端**（`chatStore.ts` + `ChatPage`）：扩展 `streamPhase`/`gemini-status-indicator` 渲染**渐进式思考面板**（多条标签渐进出现，无计时、无原始 CoT）；`answer_delta` 开始流后切答案区。
- **思考 off**：不显内心独白，直接答案流（`streamPhase: streaming`）。
- **reduced-motion**：动效最小化但状态变化可见（§15.3）。

### 3.4 SPEC 兼容
- §5.2 `phase` 事件："safe application-known phase and status only, never raw reasoning"——渐进安全标签合规。
- §7/§15.2：不外泄 reasoning_content——标签是服务端合成白名单，非原始 reasoning。
- §15.3：reduced-motion 支持。

### 3.5 测试
- 思考 on → SSE `phase` 发多条渐进安全标签 + 前端渐进渲染；`answer_delta` 后切答案。
- 思考 off → 无内心独白，直接答案流。
- **无原始 reasoning 出现在 SSE/日志/浏览器**（断言）。
- 无计时数字显示。
- reduced-motion 下状态可见、动效最小。
- 与思考开关（V3 §7）联动：off 时不显独白。

### 3.6 时机 + 联动
- 与 V3 §7（思考开关）+ §5（SSE phase）一起实现最自然（思考 on 时启用渐进相位）。
- 排 V3 稳定之后（V3 前置阻塞见 Part 4 / 文末）。

---

## Part 4 — 中英文区 / AI 答复语言（bilingual）

### 4.1 现状（已核查）
- `apps/rag/prompt_builder.py:11` `SYSTEM_PROMPT_EN` 含 "6. Respond in English."（硬编码英文答复）；`SYSTEM_PROMPT_ZH` 中文版；`build(language)` 按 language 选模板。
- `apps/chat/views.py:1040` `language = getattr(user, "language_preference", "en")` → 传 `retrieve_and_generate(..., language=language)`。
- **当前 AI 答复语言 = 用户 `language_preference`（默认 "en"），与 KB 内容语言无关**。
- 故：**KB 全中文 + 用户 pref="en"（默认）→ AI 用英文答**（引用中文内容）——疑虑成立。

### 4.2 问题
- 默认 "en" + 不跟查询语言 → 中文 KB / 中文提问也可能得英文答复（违和）。
- KB 内容语言不应驱动答复语言（应跟用户/查询，非 KB）。

### 4.3 设计（中英文区 + 答复语言解析）
**AI 答复语言解析顺序**（高→低）：
1. **查询语言自动检测**（主）：中文查询→中文答；英文查询→英文答（最自然，跟用户怎么问）。
2. **用户 `language_preference` 显式覆盖**（用户设 zh/en 则优先于检测）。
3. **空间 `default_language`**（per-space 新字段 `auto|zh|en`，默认 `auto`；查询/用户偏好未明时兜底）= "中英文区"。

- KB 内容语言**不**驱动答复语言（中英混合档可同空间；AI 引用 regardless + 用解析语言答）。
- **system prompt 改**：`SYSTEM_PROMPT_EN/ZH` 的 "Respond in English/中文" 改为 "Respond in {resolved_language}" 动态指令；不再硬编码 "en" 默认。
- **`KnowledgeSpace.default_language`** 新字段（迁移 additive；`auto|zh|en`，默认 `auto`）。
- **UI i18n** 已有（zh/en common.json）；KB 页按用户 UI 语言渲染（不与答复语言混）。

### 4.4 测试
- 中文查询→中文答；英文查询→英文答（自动检测）。
- 用户 pref="zh" + 英文查询→中文答（pref 覆盖）。
- 空间 default_language="zh" + auto 查询→中文答（空间兜底）。
- **KB 全中文 + 用户查询中文→中文答（不再误英文）**。
- KB 中英混合→答复语言跟查询/用户，引用跨语言正确。
- system prompt 不再硬编码 "en" 默认。

### 4.5 SPEC 兼容 + 时机
- §7 模型策略（答复语言不涉 reasoning，安全）；§16 单空间（`default_language` per-space）；不破坏 §4/§5。
- `KnowledgeSpace.default_language` 新字段（迁移 additive）。
- 排 V3 之后（与 Part 1 创建流 + Part 3 思考显示同期或之后）。

---

## Part 5 — 横切约束
- **PostgreSQL 真实性**：所有条件约束/索引/`select_for_update(of=("self"))`/迁移在真实 PG 验证（`config.settings.test` = PG），SQLite 不能替代（本会话已两次验证：chat FOR UPDATE P0 + V3 迁移 `%` 转义 bug 均为 SQLite 漏、PG 才抓）。
- 兼容期回退不删（§11）：`reindex`/`PATCH 元数据`/`GET chunks`/`POST /spaces/` adapter/legacy invitation code 等保留一版本；移除需用量证据+回滚演练+单独批准。
- 审计/幂等/并发保护：版本创建/回滚带 Idempotency-Key + audit + 行锁。
- 不把 token/密钥/人事原因/provider 信息写进日志/测试/提交。
- 不宣称筼筜/生产通过，除非实际完成授权现场验证。

---

## 待实现确认清单（brainstorm 已决）
- [x] 方案：内联文本编辑 + 版本化 + diff 预览（Approach A）。
- [x] binary 文档：编辑提取文本，原文件保留（接受）。
- [x] 旧版处理：a1——保留 text_content+元数据+版本谱系；chunks+embedding 只留当前版在 live 索引（不膨胀、不干扰、不丢审计；回滚重算可接受）。
- [x] 生效期：a+b——立即默认 + 支持排期（`effective_from` 未来日期）。
- [x] 新 spec，排 V3 之后。
- [x] 思考期"内心独白"显示：渐进安全相位标签（检索→分析→组织），无计时数字，无原始 CoT（SPEC §7/§15.2 红线），复用 `streamPhase`/`SafeProcessingPhase`，思考开关 on 时启用，与 V3 §7+§5 一起实现。
- [x] 创建流（Part 1.14）：多格式上传（不限制 MD）+ 输入框主入口 + `Document.file` nullable + `text_content` 规范 MD（文件提取/直接输入）；chunk+embed 基于 `text_content`。
- [x] 中英文区 / AI 答复语言（Part 4）：查询语言自动检测（主）+ 用户 `language_preference` 覆盖 + 空间 `default_language`（auto/zh/en）兜底；system prompt 改"Respond in {resolved_language}"动态指令，不硬编码 en；KB 内容语言不驱动答复语言；新增 `KnowledgeSpace.default_language` 字段。

## V3 前置阻塞（实现本 spec 前）
- V3 迁移 0011/0012/0014/0016 的 psycopg `%` 转义 bug 须先修（`%`→`%%`：RAISE `%'`/`%,`、`%ROWTYPE`）→ `migrate` 通过 → backend 起来 → V3 测试通过 → 提交。
- 本 spec 的 KB 版本化迁移依赖 V3 migration 序列之后。
