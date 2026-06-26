# EY Onboarding AI — UI Bug 清单（V4.0）

> **审计版本**：V4.0 | **审计日期**：2026-06-25 | **审计类型**：UI/UX专项
> **引用规则**：每条Bug标注 `[来源: V3.x/文件名.md §章节]` 或 `[来源: 代码审计: 文件名:行号]`
> **排除规则**：V3.8已修复的20条Bug不在此清单（见V3.8/Bug清单汇总_V3.8.md）

---

## 统计概览

| 类别 | 新发现 | V3.8遗留 | 合计 |
|------|--------|---------|------|
| 🔴 CRITICAL | 0 | 0 | 0 |
| 🟠 HIGH | 2 | 0 | 2 |
| 🟡 MEDIUM | 3 | 1 | 4 |
| 🟢 LOW | 2 | 1 | 3 |
| **合计** | **7** | **2** | **9** |

> V3.4的CRIT-001/002已在V3.5修复，V3.8无新CRITICAL级UI问题。
> V3.8遗留2条：MED-002 HistoryPage分组不一致 + RAG Citations验证。

---

## 🟠 HIGH（2条新发现）

### UI-HIGH-001：无Stop Generation按钮

- **类型**：功能缺失 | **影响**：用户体验 | **严重度**：🟠 HIGH
- **位置**：`ChatPage.tsx` 全文件无stop/cancel button
- **描述**：
  流式响应期间，用户无法主动停止生成。当前abort机制仅通过程序化触发（session切换、删除、resetSession）。用户面对冗长或错误响应时只能等待30s超时或手动切换session。

  **AbortController调用点**（均为程序化，无UI入口）：
  - `chatStore.ts:183` — setActiveSession 切换session时abort
  - `chatStore.ts:202` — resetSession 新建对话时abort
  - `AppLayout.tsx:244` — handleDeleteSession 删除session时abort

  **ChatPage.tsx输入栏现状**：
  - L358: `disabled={isStreaming || isSendLocked}` — textarea禁用
  - L373: `disabled={!inputValue.trim() || isStreaming || isSendLocked || !isOnline}` — send按钮禁用
  - **缺失**：isStreaming时应显示Stop按钮取代Send按钮

- **对比**：ChatGPT/Claude/DeepSeek均有可见的Stop按钮（StopOutlined/PauseCircleOutlined）
- **复现步骤**：
  1. 发送任意消息 → 流式开始
  2. 观察输入栏 → Send按钮变为disabled灰色，**无Stop按钮出现**
  3. 等待30s → 超时自动abort；或切换/删除session → 程序化abort
- **根因**：`StreamLifecycleManager.ts` 的 `abortActiveStream()` 无UI触发入口。ChatPage.tsx在isStreaming状态下只做了disable，未做条件渲染Stop按钮。
- **来源**：[来源: 代码审计: ChatPage.tsx L358/L373 + StreamLifecycleManager.ts 全文件]

---

### UI-HIGH-002：代码块无语法高亮

- **类型**：功能缺失 | **影响**：可读性+专业性 | **严重度**：🟠 HIGH
- **位置**：`MessageBubble.tsx:309-322` — ReactMarkdown无rehypePlugins
- **描述**：
  ReactMarkdown未配置`rehype-highlight`或`react-syntax-highlighter`插件。所有代码块渲染为纯灰色monospace文本，无语言识别、无语法颜色区分。

  **当前ReactMarkdown配置**（MessageBubble.tsx:309-322）：
  ```tsx
  <ReactMarkdown
    allowedElements={ALLOWED_ELEMENTS}
    unwrapDisallowed={true}
    components={{
      a: ({ href, children }) => (...),
      img: ({ src, alt }) => (...),
    }}
  >{message.content}</ReactMarkdown>
  ```
  - ❌ 无 `remarkPlugins` prop（缺 remark-gfm）
  - ❌ 无 `rehypePlugins` prop（缺 rehype-highlight）
  - ❌ 无自定义 `code` component（无语言标签/复制按钮）

  **CSS样式**（globals.css:387-399）：
  - `.markdown-content code`: background=var(--muted), padding=2px 6px → 全灰色背景
  - `.markdown-content pre code`: background=transparent → 代码块内代码无背景
  - font-family=var(--font-family-mono) → 纯monospace字体

- **对比**：所有主流AI助手均提供代码语法高亮（至少Python/JS/Java等常见语言）
- **复现步骤**：
  1. 请求AI返回Python代码 → `def foo(): ...`
  2. 观察代码块 → 全灰色纯monospace文本
  3. 无关键字紫色、字符串绿色、注释灰色等区分
- **根因**：
  - `package.json` dependencies无rehype-highlight或react-syntax-highlighter
  - ReactMarkdown components prop未定义code渲染组件
  - globals.css无语法高亮相关样式（.hljs-keyword等）
- **来源**：[来源: 代码审计: MessageBubble.tsx L309-322 + package.json dependencies + globals.css L387-399]

---

## 🟡 MEDIUM（3新发现 + 1遗留）

### UI-MED-001：GFM不支持（表格/删除线/任务列表渲染为原始文本）

- **类型**：功能缺失 | **影响**：内容渲染完整性 | **严重度**：🟡 MEDIUM
- **位置**：`MessageBubble.tsx:309-322` — ReactMarkdown无remarkPlugins
- **描述**：
  `remark-gfm`未安装，GFM扩展语法无法渲染：

  | GFM语法 | 期望渲染 | 实际渲染 |
  |---------|---------|---------|
  | `| A | B |` 表格 | HTML `<table>` 对齐表格 | 管道符原始文本 |
  | `~~删除~~` 删除线 | `<del>` 删除线效果 | 带~~的文本 |
  | `- [x] done` 任务列表 | 复选框样式 | 普通列表项 `[x] done` |
  | 自动链接 `https://...` | `<a href>` 可点击链接 | 纯文本URL |

  **关键**：`ALLOWED_ELEMENTS`（MessageBubble.tsx:12-20）包含`table,thead,tbody,tr,th,td`，说明开发者意图支持表格。但由于**缺少remark-gfm解析器**，Markdown表格语法不会被转换为HTML table元素，ALLOWED_ELEMENTS白名单中的table相关标签实际上永远不会被使用。

- **复现步骤**：
  1. 输入包含表格的Markdown → 观察渲染为管道符原始文本
  2. 输入`~~删除线~~` → 观察渲染为带~~的文本
  3. 输入`- [ ] todo` → 观察渲染为普通列表项
- **根因**：package.json无remark-gfm依赖；ReactMarkdown无remarkPlugins prop
- **来源**：[来源: 代码审计: MessageBubble.tsx L12-20(ALLOWED_ELEMENTS含table) + L309-322(无remarkPlugins) + package.json]

---

### UI-MED-002：代码块无复制按钮（只有全消息复制）

- **类型**：UX缺失 | **影响**：操作效率 | **严重度**：🟡 MEDIUM
- **位置**：`MessageBubble.tsx:88-107` — handleCopy复制全消息内容
- **描述**：
  代码块(`pre/code`)无独立的复制按钮。当前复制机制：
  - `handleCopy` [L88-107]: `navigator.clipboard.writeText(message.content)` → 复制**整个消息内容**，不是仅代码块
  - 桌面端hover显示 `CopyOutlined` 按钮 [L179-191] → 点击复制全消息
  - 移动端Popover菜单 [L233-261] → 同样复制全消息

  **用户痛点**：
  - AI返回含代码块的回复 → 用户需要仅复制代码部分
  - 当前方案：复制全消息 → 手动截取代码 → 粘贴 → 删除多余内容
  - 理想方案：代码块右上角独立Copy按钮 → 一键复制代码内容

- **复现步骤**：
  1. 请求AI返回含代码块的回复
  2. hover出现CopyOutlined按钮 → 点击
  3. 粘贴 → 复制的是全消息（含非代码文本），不是仅代码块
- **来源**：[来源: 代码审计: MessageBubble.tsx L88-107(handleCopy) + L179-191(CopyOutlined)]

---

### UI-MED-003：Markdown内容移动端溢出风险

- **类型**：视觉bug | **影响**：可读性 | **严重度**：🟡 MEDIUM
- **位置**：
  - `globals.css:377-385` — `.markdown-content pre { overflow-x:auto; max-width:100% }`
  - `MessageBubble.tsx:157` — `maxWidth:'75%'` (msg-bubble-wrapper)
  - `MessageBubble.tsx:276` — `bodyStyle:{padding:'12px 16px'}`
- **描述**：
  在窄屏幕(<400px如iPhone SE)，消息气泡的宽度约束链：
  ```
  视口375px × msg-bubble-wrapper maxWidth:75% = 281px
  → Card body padding 12px×2 + 16px×2 ≈ 实际内容区249px
  → .markdown-content pre max-width:100% = 249px
  → 50行代码块每行可能>249px → 需overflow-x:auto生效
  ```
  **风险点**：如果overflow-x:auto被父容器约束覆盖（Card可能有自己的overflow策略），代码块可能溢出Card边界。

  **当前无小屏幕CSS适配**：
  - globals.css无`@media(max-width:400px)`的markdown-content相关规则
  - 只有`@media(max-width:768px)`的通用padding缩减 [globals.css:330-334]

- **复现步骤**：
  1. Chrome DevTools → 375px视口 (iPhone SE模拟)
  2. 请求AI返回50+行Python代码
  3. 观察代码块是否溢出Card边界
- **来源**：[来源: 代码审计: globals.css L377-385 + MessageBubble.tsx L157/276]

---

### UI-MED-004（V3.8遗留）：HistoryPage日期分组不一致

- **引入版本**：V3.4 [来源: V3.4/bug_list.md MED-002]
- **V3.5状态**：❌ 回归失败 [来源: V3.5/bug_list.md v3.5-REGRESS-009]
- **V3.7状态**：⚠️ 待修复 [来源: V3.7/性能优化验收报告_V3.7.md]
- **V3.8状态**：⚠️ 同上
- **V4.0验证**：
  - `App.tsx:46-62` 路由仅含 `/chat`, `/profile`, `/admin/knowledge`
  - **无 `/history` 路由** → HistoryPage为dead code（未注册在路由中）
  - HistoryPage使用独立的 `getDateGroup()` 而非共享 `dateGroup.ts`
- **严重度维持**：🟡 MED（功能不可达但代码存在，需要路线决定：修复并启用 vs 删除）
- **来源**：[来源: V3.5/reports/综合审计报告.md §三 3.3 + 代码审计: App.tsx L46-62]

---

## 🟢 LOW（2新发现 + 1遗留）

### UI-LOW-001：Card bodyStyle硬编码padding

- **类型**：代码质量 | **影响**：可维护性 | **严重度**：🟢 LOW
- **位置**：`MessageBubble.tsx:276` — `bodyStyle:{padding:'12px 16px'}`
- **描述**：
  padding值硬编码为`'12px 16px'`，不使用CSS变量(`--spacing-md`)，也不响应屏幕尺寸。globals.css已定义`--spacing-md: 16px`和`--spacing-sm: 8px`但MessageBubble未使用。

  在<400px屏幕上，16px横向padding占可用宽度(249px)的6.4%以上，导致内容区更窄。
- **来源**：[来源: 代码审计: MessageBubble.tsx L276 + globals.css L49(--spacing-md)]

---

### UI-LOW-002：globals.css 898行未模块化

- **类型**：架构 | **影响**：可维护性 | **严重度**：🟢 LOW
- **位置**：`frontend/src/styles/globals.css` (全文件898行)
- **描述**：
  全局CSS未拆分为模块，混合了：
  - 设计token (L9-72) — 颜色/字体/间距/阴影变量
  - 全局样式 (L114-172) — body/scrollbar/selection
  - 动画 (L174-238) — 10个keyframes定义
  - 组件样式 (L300-420) — markdown/card/button/skeleton
  - 暗色覆盖 (L525-623) — 15个[data-theme="dark"]规则
  - 迭代特定样式 (L706-898) — sidebar/tour/message-skeleton等

  P3-3规划CSS重构（CSS Modules或拆分文件）但未落地。
- **来源**：[来源: V3.8/迭代功能规划汇总_V3.8.md P3-3 + 代码审计: globals.css]

---

### UI-LOW-003（V3.8遗留）：RAG Citations无法端到端验证

- **引入版本**：V3.7 [来源: V3.7/性能优化验收报告_V3.7.md §4 #1]
- **描述**：知识库无文档数据，Citations功能无法端到端验证
- **V3.8状态**：⚠️ 待导入文档后二次验证
- **V4.0验证**：MessageBubble.tsx:330-408有完整的Citations UI代码（折叠按钮+文档标题+页码+相关性分数），但无实际数据触发
- **来源**：[来源: V3.7/性能优化验收报告_V3.7.md §4 #1]

---

## 📊 Bug严重度分布图

```
CRITICAL (0) ████████████████████████████████ 全部已修复(V3.5)
HIGH     (2) ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░ Stop Button + 代码高亮
MEDIUM   (4) ████░░░░░░░░░░░░░░░░░░░░░░░░░░ GFM + 代码复制 + 溢出 + HistoryPage
LOW      (3) ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░ padding + CSS模块化 + Citations验证
```

---

## 🔗 与V3.8 Bug清单的关系

| V3.8 Bug | V4.0状态 | 说明 |
|----------|---------|------|
| CRIT-001 SSE无法取消 | ✅ 已修复(V3.5) | AbortController机制完善，但缺UI入口(UI-HIGH-001) |
| CRIT-002 Session竞态 | ✅ 已修复(V3.5) | streamPhase状态机稳定运行 |
| HIGH-001~008 | ✅ 全部已修复 | isSendLocked/abort/Virtuoso/rAF/error-i18n/disableActions |
| MED-002 HistoryPage | ⚠️ 遗留 → UI-MED-004 | 路由缺失+分组不一致 |
| MED-001/003~007 | ✅ 已修复 | MAX上限/Observer/ReactMarkdown/error-i18n/modal |
| Citations验证 | ⚠️ 遗留 → UI-LOW-003 | 知识库无数据 |

**V4.0新增7条Bug**：2 HIGH + 3 MED + 2 LOW，均为功能缺失和视觉问题，非逻辑Bug。
