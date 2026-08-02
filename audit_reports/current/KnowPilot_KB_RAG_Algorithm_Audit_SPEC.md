# KnowPilot 知识库检索算法与迭代机制审计 SPEC

版本：v1.0 ｜ 日期：2026-07-28 ｜ 范围：backend/apps/rag、backend/apps/knowledge ｜ 目标：对齐 Obsidian 级知识库体验 + 跨库 Agent 调用下的检索质量

## 1. 现状架构

### 1.1 检索链路（chat 提问）
```
retrieve_and_generate (rag/pipeline.py)
  └─ resolve_reference_space_ids (knowledge/library_views.py)   # 跨库白名单
  └─ HybridRetriever.search (rag/hybrid.py)
       ├─ PgVectorRetriever (rag/retriever.py)   # pgvector HNSW 余弦，space 白名单硬过滤
       ├─ _postgres_lexical_search               # PostgreSQL FTS（simple 配置）
       ├─ reciprocal_rank_fusion (rrf_k=60)
       ├─ _annotate_document_signals             # 新鲜度指数衰减
       ├─ rerank_results                         # 0.55×融合 + 0.35×单路证据 + 0.10×新鲜度
       ├─ _apply_query_signals                   # 术语+0.1 / 跨财年×0.6 / stale×0.7
       └─ diversify_results                      # 每文档≤2块
  └─ classify_confidence → low/insufficient 拒答
  └─ _build_citations → LLM 流式生成（熔断器保护）
```

### 1.2 迭代更新链路
```
上传/编辑 → enqueue_document_ingestion (knowledge/ingestion.py, 持久化Job)
  → Celery ingest_document → LangChainChunker → EmbeddingService → chunk落库 + pgvector同步
  → sync_document_links (knowledge/links.py, wikilink全删重建)
夜间 → scan_stale_documents (knowledge/tasks.py, 超期置stale+通知术语负责人)
```

## 2. 问题清单

### A. 检索/资源调用算法

| # | 问题 | 证据位置 | 影响 | 状态 |
|---|------|----------|------|------|
| A1 | 跨库无路由无配额：所有启用参考库每问全量检索，RRF 池统一排序，大库可挤占本空间结果 | pipeline.py L382-400、hybrid.py diversify_results | 相关性下降、成本线性放大 | 配额 **P0 已修复**；路由 **P2 已修复（library_routing 按库名/类目关键词路由，可开关降级）** |
| A2 | 置信度尺度失准：signal boost/penalty 改写 rerank_score，0.75/0.55 阈值按原尺度校准 | hybrid.py `_apply_query_signals` | 术语命中虚高置信；惩罚导致误拒答 | **P0 已修复** |
| A3 | 参考库新鲜度语义错误：半衰期只取首文档空间；准则文档吃时间衰减+stale 惩罚 | hybrid.py `_annotate_document_signals` | IFRS 等标准文档被系统性降权 | **P0 已修复** |
| A4 | 查询理解原始：正则财年 + 全量词表 Python 包含匹配；无同义词/改写/多查询 | rag/query_understanding.py | 同义术语召回漏（坏账准备 vs 信用减值损失） | **P2 已修复（受控同义词表 synonyms + 词法扩展）** |
| A5 | 假批量 embedding：embed_batch 逐条串行 + 每 5 条 sleep 0.5s | rag/embedding.py L270-299 | 500 chunk 文档 500 次调用 + 50s 空等 | **P1 已修复** |
| A6 | 中文词法检索差：FTS simple 配置，汉字逐字成 token | hybrid.py L19、L336-343 | 中文关键词召回质量低 | **P1 已修复（CJK bigram）** |
| A7 | 切块非结构感知：不按 Markdown 标题分块 | rag/chunker.py | 章节语义丢失，无法做标题级引用 | **P2 已修复（split_markdown + citation section）** |
| A8 | 无模型级 rerank；查询 embedding 缓存为进程内 5min TTL 不跨 worker | hybrid.py / embedding.py L115 | 排序上限受限；缓存命中率低 | 缓存 **P1 已修复（Redis L2）**；rerank **P2 已修复（可选 LLM rerank，默认关）** |
| A9 | 拒答兜底文案为 HR 领域残留 | pipeline.py、prompt_builder.py | 与审计定位不符 | **P0 已修复** |

### B. 迭代更新机制

| # | 问题 | 证据位置 | 影响 | 状态 |
|---|------|----------|------|------|
| B1 | 双链缺 Obsidian 核心能力：无 unresolved link、无重命名传播、无补全端点、不跨库 | knowledge/links.py | 断链静默发生；编辑体验不闭环 | **P3 已修复（unresolved 灰链+自动解析、重命名传播+审计、link-suggest 端点、跨库双链）** |
| B2 | 图谱相似度边请求时 O(n²) Python 现算（300 节点 ≈ 4.5 万次 1024 维余弦），且仅取首块向量 | knowledge/viz_views.py L136-152 | 图谱 Tab 卡顿；相似度失真 | **P1 已修复（DocumentSimilarity 预计算 + 池化向量）** |
| B3 | 质量信号无闭环：拒答/负反馈不自动生成知识缺口工单、不回流排序 | viz_views.knowledge_dashboard | 迭代靠人工盯看板 | **P2 已修复（insufficient 回答自动开工单，幂等+术语关联）** |
| B4 | 工程性：版本历史无 GET 列表（勘误：GET 已存在于 DocumentVersionCreateView.get）；stale 扫描逐条 save+notify；superseded chunk 无清理；ingest 每 chunk 单独 UPDATE 同步向量 | knowledge/views.py、tasks.py、rag/pipeline.py L146-160 | 运维成本随规模上升 | stale 扫描 **P1 已修复**；chunk 清理 **P3 已修复（purge_superseded_chunks 夜间任务）**；向量同步待优化 |

### C. 做对了的部分（不要动）
- 空间隔离：检索强制 space_id 白名单 + UUID 校验 + 过滤键白名单防注入；chunk 反规范化 space FK
- RRF 融合避免了跨路分数直接比较；持久化 IngestionJob + Celery 异步索引；chunk 注入检测清洗

## 3. P0 修复实施记录（本次已完成）

| 修复 | 文件 | 方案 |
|------|------|------|
| A2 置信度尺度 | `rag/hybrid.py` | boost/penalty 只写入 `score`/`signal_adjusted_score` 驱动排序；`rerank_score` 保持纯净供 `classify_confidence` 使用 |
| A3 新鲜度豁免 | `rag/hybrid.py` | 按各文档所在空间取半衰期；published ReferenceLibrary 空间文档 freshness=1.0、标记 `is_reference_library`、跳过 stale 惩罚 |
| A1 来源配额 | `rag/hybrid.py` | `diversify_results` 新增 `primary_space_id` + `max_reference_ratio=0.5`：参考库结果最多占 top_k 一半，本空间不足时才回填 |
| A9 兜底文案 | `rag/pipeline.py`、`rag/prompt_builder.py` | 中英文案改为"补充相关知识文档或联系知识库管理员" |

测试：`backend/apps/rag/test_p0_audit_fixes.py`（6 例全过）；`apps.rag` 全量 66 例仅 1 个存量 SSE 用例失败（基线复测同样失败，与本次无关）。

## 4. 后续路线图

### P1 — 性能（已实施，见 test_p1_perf.py）
1. 真批量 embedding：每请求 ≤10 条（EMBED_BATCH_SIZE），取消固定 sleep，批失败降级单条、单条失败落零向量
2. 查询 embedding 缓存增加 Django/Redis L2（TTL 30min，跨 worker 共享，后端故障自动降级）
3. 图谱相似度预计算：Document.pooled_embedding（chunk 均值池化）+ DocumentSimilarity 边表（ingest 时刷新）；viz 端点只读，未回填空间回退现算；存量数据由 backfill_document_similarities 任务回填（已执行：10 docs / 1 edge / 12 chunk tokens）
4. 中文检索：无新依赖的 CJK bigram 方案 —— chunk 新增 content_tokens 列（分词后标题+正文），查询侧同构扩展，旧行保持兼容
5. stale 扫描批量化：bulk update + 按负责人合并通知；同时修复旧实现 save 刷新 updated_at 导致新鲜度时钟被重置的 bug

### P2 — 算法升级（已实施，见 test_p2p3_features.py）
1. 轻量库路由（rag/library_routing.py）：按库名提及 / 类目关键词表决定检索哪些库；无信号仅本空间；RAG_LIBRARY_ROUTING_ENABLED=False 降级全量
2. 结构感知切块：chunker.split_markdown 按标题层级分段，chunk metadata 记 section 路径，citation 携带 § 章节（前端 Sources 展示）；md 文件与 text_content 两条 ingest 路径生效
3. 同义词扩展：TaxonomyTerm.synonyms（迁移 0018）+ 术语 API 支持维护；analyze_query 命中同义词并产出 expansion_terms 扩展词法查询（信号单次分析复用）
4. 可选 LLM rerank（rag/llm_rerank.py）：RAG_LLM_RERANK_ENABLED 默认关；失败/乱序输出一律回退原序；不影响置信度
5. 质量闭环：insufficient 回答自动创建 KnowledgeGapTicket（按空间+问题哈希幂等，suggested_source 携带命中术语，审计 knowledge_gap_create）

### P3 — Obsidian 体验（已实施）
1. 版本历史 GET：勘误修正 —— 端点早已存在（DocumentVersionCreateView.get 返回完整版本链），无需开发
2. wikilink 补全端点：GET /documents/link-suggest/?q= —— 本空间+已启用库标题模糊匹配；前端编辑器 linkCandidates 已接入
3. Unresolved links：DocumentLink.target 可空 + unresolved_title（迁移 0018）；灰链在 BacklinksPanel 展示；目标文档创建/ingest 后自动解析
4. 标题重命名传播：DocumentDetailView.perform_update 检测改名 → 重写引用方 [[旧标题]]/[[旧标题|别名]] → 重建链接 → 审计 document_rename_propagate（audit 迁移 0017）
5. 跨库双链：链接解析范围扩展到已启用 published 参考库（本空间同名优先）
6. superseded chunk 清理：purge_superseded_chunks 夜间任务（保留期 KNOWLEDGE_SUPERSEDED_CHUNK_RETENTION_DAYS 默认 30 天；回滚基于 text_content 不受影响）

## 5. 验收标准（P0）
- classify_confidence 输入不受 signal 调整污染（单测覆盖）
- published 参考库文档 freshness=1.0 且免 stale 惩罚（单测覆盖）
- top_k 中参考库来源 ≤ 50%，本空间不足时回填（单测覆盖）
- 拒答文案无 HR 字样（单测覆盖 + 浏览器验证）
- 现有 apps.rag 测试无新增失败
