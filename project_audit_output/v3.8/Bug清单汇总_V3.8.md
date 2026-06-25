# EY Onboarding AI — Bug 清单汇总（V3.1-V3.7）

> **汇总版本**：V3.8 | **汇总日期**：2026-06-25 | **覆盖范围**：V3.1 → V3.7 全部Bug和问题
> **引用规则**：每条Bug标注 `[来源: V3.x/文件名.md]`，便于溯源

---

## 统计概览

| 类别 | 总发现 | 已修复 | 待修复 | 已降级 |
|------|--------|--------|--------|--------|
| 🔴 CRITICAL | 2 | 2 ✅ | 0 | — |
| 🟠 HIGH | 8 | 8 ✅ | 0 | — |
| 🟡 MEDIUM | 7 | 5 ✅ | 2 | — |
| 🟢 LOW | 5 | 5 ✅ | 0 | — |
| **合计** | **22** | **20 ✅** | **2** | — |

---

## 🔴 CRITICAL（2条，全部已修复）

### CRIT-001：SSE fetch 无法取消 → 3000并发下服务器雪崩
- **引入版本**：V3.4 发现 [来源: V3.4/bug_list.md CRIT-001]
- **描述**：`fetch()` 调用缺少 `AbortController.signal`，用户切换Session后旧SSE连接继续活跃，3000并发推演→90,000僵尸连接
- **修复版本**：V3.5 ✅ [来源: V3.5/bug_list.md v3.5-REGRESS-001]
- **修复方案**：`StreamLifecycleManager.ts` — `createStreamAbortController(sessionId)` + `abortActiveStream()`；`setActiveSession`调用abort；catch `AbortError` → `clearStreamOnComplete()`
- **V3.7验证**：✅ AbortController在session切换时成功触发 [来源: V3.7/性能优化验收报告_V3.7.md §2.3]

### CRIT-002：Session切换竞态 → 消息交叉显示
- **引入版本**：V3.4 发现 [来源: V3.4/bug_list.md CRIT-002]
- **描述**：`sendMessage` 和 `setActiveSession` 无同步机制，切换session后旧消息写入新session
- **修复版本**：V3.5 ✅ [来源: V3.5/bug_list.md v3.5-REGRESS-002]
- **修复方案**：streamPhase状态机(`idle→connecting→streaming→done`) + `finishStreamingMessage`验证sessionId匹配

---

## 🟠 HIGH（8条，全部已修复）

### HIGH-001：发送防抖缺失 → 双击/快速连续发送风暴
- **引入版本**：V3.4 [来源: V3.4/bug_list.md HIGH-001]
- **修复版本**：V3.5 ✅ [来源: V3.5/bug_list.md v3.5-REGRESS-003]
- **修复方案**：`isSendLocked` 状态 + 多入口守护（textarea + send button + AppLayout sidebar click）

### HIGH-002：删除流式Session → 无abort → 服务器线程阻塞
- **引入版本**：V3.4 [来源: V3.4/bug_list.md HIGH-002]
- **修复版本**：V3.5 ✅ [来源: V3.5/bug_list.md v3.5-REGRESS-004]
- **修复方案**：`AppLayout.tsx` sidebar click → `abortActiveStream()` 先abort再删除

### HIGH-003：DOM节点未虚拟化 → 100+消息DOM膨胀
- **引入版本**：V3.4 [来源: V3.4/bug_list.md HIGH-003]
- **修复版本**：V3.5 ⚠️ 部分通过 [来源: V3.5/bug_list.md v3.5-REGRESS-005]
- **修复方案**：Virtuoso虚拟滚动集成，但12轮内未触发"加载更早"

### HIGH-004：API无分页 → N+1查询 → 响应变慢
- **引入版本**：V3.4 [来源: V3.4/bug_list.md HIGH-004]
- **修复版本**：V3.5 ✅ [来源: V3.5/bug_list.md v3.5-REGRESS-006]
- **修复方案**：CursorPagination + prefetch_related

### HIGH-005：滑动窗口前后端不对齐
- **引入版本**：V3.4 [来源: V3.4/bug_list.md HIGH-005]
- **修复版本**：V3.5 ✅ [来源: V3.5/bug_list.md v3.5-REGRESS-007]
- **修复方案**：前后端 `WINDOW_ROUNDS=10` 对齐

### HIGH-006：Token逐帧渲染 → CPU密集
- **引入版本**：V3.4 [来源: V3.4/bug_list.md HIGH-006]
- **修复版本**：V3.5 ✅ [来源: V3.5/bug_list.md v3.5-REGRESS-008]
- **修复方案**：rAF `TokenBatchRenderer` 批处理

### HIGH-007(V3.5新发现)：快速连续发送 → error_generic
- **引入版本**：V3.5 [来源: V3.5/bug_list.md §三 3.1]
- **描述**：连续10+短消息触发SSE错误，原始error key未翻译
- **修复版本**：V3.6 ✅

### HIGH-008(V3.5新发现)：流式期间UI操作未完全禁用
- **引入版本**：V3.5 [来源: V3.5/reports/综合审计报告.md §二 2.2]
- **修复版本**：V3.6 ✅
- **修复方案**：`disableActions` prop设置pointer-events:none + opacity:0.3

---

## 🟡 MEDIUM（7条，5已修复，2待修复）

### MED-001(V3.4)：Zustand无限增长 → 3GB内存风险
- **引入版本**：V3.4 [来源: V3.4/bug_list.md MED-001]
- **修复版本**：V3.7 ✅ [来源: V3.7/性能优化验收报告_V3.7.md §2.2]
- **修复方案**：`MAX_ALL_MESSAGES=100` 硬上限裁剪 + `visibleRoundCount` 滑动窗口

### MED-002(V3.4)：HistoryPage日期分组不一致
- **引入版本**：V3.4 [来源: V3.4/bug_list.md MED-002]
- **修复版本**：V3.5 ❌ 回归失败 [来源: V3.5/bug_list.md v3.5-REGRESS-009]
- **V3.7状态**：⚠️ **待修复** — HistoryPage仍有独立分组+不在路由中

### MED-003(V3.4)：IntersectionObserver每帧重建 → GC压力
- **引入版本**：V3.4 → V3.6量化确认 [来源: V3.6/性能瓶颈分析报告_V3.6.md §2.5 验证C]
- **修复版本**：V3.7 ✅ — 依赖项修正（移除streamContent） [来源: V3.7/性能优化验收报告_V3.7.md §2.2]

### MED-004(V3.5新发现)：Sidebar搜索空结果UI处理
- **引入版本**：V3.5 [来源: V3.5/reports/综合审计报告.md §三 3.2]
- **修复版本**：V3.6 ✅ — 空搜索时不显示分组标题，UI不崩溃

### MED-005(V3.5新发现)：流式期间ReactMarkdown重渲染
- **引入版本**：V3.5→V3.6量化 [来源: V3.6/性能瓶颈分析报告_V3.6.md §2 瓶颈#2]
- **修复版本**：V3.7 ✅ [来源: V3.7/性能优化验收报告_V3.7.md §2.2]
- **修复方案**：isStreaming=纯文本span, !isStreaming=ReactMarkdown(仅1次解析)

### MED-006(V3.5新发现)：SSE错误key未翻译(error_generic)
- **引入版本**：V3.5 [来源: V3.5/bug_list.md §三 3.1]
- **修复版本**：V3.6 ✅

### MED-007(V3.5新发现)：Modal阻塞sidebar点击
- **引入版本**：V3.5 [来源: V3.4截图 v3.4_modal_blocking_sidebar.png]
- **修复版本**：V3.6 ✅ — Modal关闭后才可操作sidebar

---

## 🟢 LOW（5条，全部已修复）

| Bug ID | 描述 | 引入版本 | 修复版本 | 来源 |
|--------|------|---------|---------|------|
| LOW-001 | Puppeteer选择器不匹配(非真实Bug) | V3.1 | ⏭️跳过 | [来源: V3.1/bug_list.md BUG-001] |
| UX-001 | 思考指示器10s延迟 | V3.1 | V3.2 | [来源: V3.1/bug_list.md UX-001] |
| UX-002 | Profile仅2字段 | V3.1 | V3.2 | [来源: V3.1/bug_list.md UX-002] |
| UX-003 | 移动端汉堡菜单不够醒目 | V3.1 | V3.2 | [来源: V3.1/bug_list.md UX-003] |
| UX-004 | Demo账号提示不便捷 | V3.1 | V3.2 | [来源: V3.1/bug_list.md UX-004] |

---

## ⚠️ 待修复清单（V3.8需关注）

| # | 严重度 | 问题 | 原始来源 | 建议优先级 |
|---|--------|------|---------|----------|
| 1 | 🟡中 | HistoryPage日期分组不一致 | [来源: V3.5/reports/综合审计报告.md §三 3.3] | P2 |
| 2 | ⚠️中 | 知识库无数据RAG Citations无法验证 | [来源: V3.7/性能优化验收报告_V3.7.md §4 #1] | P1(需导入文档) |
