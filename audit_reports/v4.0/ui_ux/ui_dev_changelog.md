# V4.0 UI 开发变更日志

> 版本: V4.0 UI 重塑
> 日期: 2026-06-25
> 审计来源: `audit_reports/v4.0/ui_ux/v4.0_ui_综合审计报告.md`

---

## Bug 修复

### UI-HIGH-001: 停止生成按钮

| 属性 | 内容 |
|------|------|
| 来源 | `audit_reports/v4.0/ui_ux/ui_bug_list.md` §UI-HIGH-001 |
| 问题 | 用户无法中断流式输出，只能等 30s 超时或切换会话 |
| 修复方式 | ChatPage + WelcomeScreen 输入栏条件渲染 StopOutlined/SendOutlined 按钮 |
| 修改文件 | `frontend/src/pages/ChatPage.tsx` (L6-8 import, L174-180 handleStop, L387-401 条件渲染按钮) |
| 修改文件 | `frontend/src/components/chat/WelcomeScreen.tsx` (L13 StopOutlined import, L56 handleStop, L148-174 条件渲染按钮) |
| 修改文件 | `frontend/src/store/chatStore.ts` (L508-527 AbortError handler 保留截断内容) |
| 关联功能 | `StreamLifecycleManager.abortActiveStream()` |
| 验证点 | Stop 按钮可见 → 点击后内容截断保留 → Network (cancelled) → 之后可正常发送 |

### UI-HIGH-002: 代码块语法高亮

| 属性 | 内容 |
|------|------|
| 来源 | `audit_reports/v4.0/ui_ux/ui_bug_list.md` §UI-HIGH-002 |
| 问题 | 代码块全灰色等宽字体，无语言识别和颜色区分 |
| 修复方式 | 安装 rehype-highlight + highlight.js，配置 ReactMarkdown rehypePlugins |
| 修改文件 | `frontend/package.json` (+rehype-highlight, +highlight.js) |
| 修改文件 | `frontend/src/components/chat/MessageBubble.tsx` (L5-6 import, L318-319 remarkPlugins/rehypePlugins) |
| 修改文件 | `frontend/src/styles/globals.css` (L7 @import highlight.js/styles/github.css, 暗色模式 hljs 覆盖) |
| 修改文件 | `frontend/src/components/chat/MessageBubble.tsx` (L24 span 加入 ALLOWED_ELEMENTS) |
| 验证点 | 代码块有颜色区分 → highlight.js span token 渲染正确 → 暗色模式正常 |

### UI-MED-001: GFM 支持

| 属性 | 内容 |
|------|------|
| 来源 | `audit_reports/v4.0/ui_ux/ui_bug_list.md` §UI-MED-001 |
| 问题 | remark-gfm 未安装，表格/删除线/任务列表渲染为原始 Markdown |
| 修复方式 | 安装 remark-gfm，配置 ReactMarkdown remarkPlugins，扩充 ALLOWED_ELEMENTS + CSS 样式 |
| 修改文件 | `frontend/package.json` (+remark-gfm) |
| 修改文件 | `frontend/src/components/chat/MessageBubble.tsx` (L4 import remarkGfm, L318 remarkPlugins, L25 input 加入 ALLOWED_ELEMENTS) |
| 修改文件 | `frontend/src/styles/globals.css` (新增 .markdown-content table/th/td 样式, GFM del/checkbox 样式) |
| 验证点 | Markdown 表格正确渲染 → 删除线显示 → 任务列表 checkbox 可见 |

### UI-MED-002: 代码块复制按钮

| 属性 | 内容 |
|------|------|
| 来源 | `audit_reports/v4.0/ui_ux/ui_bug_list.md` §UI-MED-002 |
| 问题 | handleCopy 复制整条消息，代码块无独立复制功能 |
| 修复方式 | 新建 CopyCodeButton 组件 + 自定义 ReactMarkdown pre 渲染器注入 |
| 新增文件 | `frontend/src/components/chat/CopyCodeButton.tsx` |
| 修改文件 | `frontend/src/components/chat/MessageBubble.tsx` (L10 import, L320-350 自定义 pre 渲染器) |
| 修改文件 | `frontend/src/styles/globals.css` (新增 .code-block-copy-btn, .code-lang-label 样式 + hover/touch 显现逻辑) |
| 验证点 | 代码块右上角复制按钮 → 点击后 Toast "代码已复制" → 剪贴板内容正确 |

### UI-MED-003: Markdown 移动端溢出

| 属性 | 内容 |
|------|------|
| 来源 | `audit_reports/v4.0/ui_ux/ui_bug_list.md` §UI-MED-003 |
| 问题 | 小屏 (<400px) 代码块和表格溢出气泡边界 |
| 修复方式 | 新增 @media(max-width:400px) CSS 规则 + CSS 变量响应式 padding + 扩大气泡宽度 |
| 修改文件 | `frontend/src/styles/globals.css` (新增 @media(max-width:400px) 响应式规则, --msg-bubble-padding CSS 变量) |
| 修改文件 | `frontend/src/components/chat/MessageBubble.tsx` (L276 bodyStyle 使用 CSS 变量) |
| 验证点 | 375px 视口下代码块有横向滚动条 → 气泡边缘无遮挡 → 表格可滚动 |

### UI-LOW-001: Card bodyStyle 硬编码 padding

| 属性 | 内容 |
|------|------|
| 来源 | `audit_reports/v4.0/ui_ux/ui_bug_list.md` §UI-LOW-001 |
| 问题 | MessageBubble bodyStyle 使用硬编码 `'12px 16px'` 而非 CSS 变量 |
| 修复方式 | 改用 `var(--msg-bubble-padding, 12px 16px)` CSS 变量引用 |
| 修改文件 | `frontend/src/styles/globals.css` (新增 --msg-bubble-padding CSS 变量) |
| 修改文件 | `frontend/src/components/chat/MessageBubble.tsx` (L276) |
| 验证点 | 小屏时 padding 自动缩减 |

---

## 功能新增

| 功能 | i18n Key | zh 值 | en 值 |
|------|----------|-------|-------|
| 停止生成按钮 | `stop_generation` | 停止生成 | Stop generation |
| 代码块复制 | `code_copied` | 代码已复制 | Code copied |
| 代码块复制 | `copy_code` | 复制代码 | Copy code |

修改文件: `frontend/src/i18n/locales/zh/chat.json`, `frontend/src/i18n/locales/en/chat.json`

---

## 关键架构决策

1. **AbortError 保留内容**: chatStore.ts AbortError handler 原先清空 `streamContent`（L511: `streamContent: ''`），V4.0 改为先 flush + 读取已输出内容 + addMessage 保存截断消息，再清空状态。这确保 Stop 按钮点击后用户已看到的文本不会丢失。

2. **流式期间不触发 Markdown**: V3.7 P1.2 的性能优化策略保留——`isStreaming=true` 时用纯文本 span 渲染，`isStreaming=false` 时才触发 ReactMarkdown（含 GFM + syntax highlight）。这意味着代码高亮和复制按钮仅在流结束后出现，避免流式期间的 O(n²) AST 解析。

3. **CopyCodeButton AST 提取**: 通过 ReactMarkdown `components.pre` 的 `node` prop（AST 节点）提取代码内容和语言标签，而非从 rendered React children 提取。这避免了 highlight.js 渲染后 children 结构复杂导致的提取失败。

---

## 构建验证

- TypeScript 编译: ✅ (仅遗留 `crossTabSync.ts` 已有错误，非本次引入)
- Vite 构建: ✅ `built in 25.43s`
- highlight.js CSS 打包: ✅ (hljs 规则出现在 dist CSS 中)
- Bundle size: index.js 478KB, antd 1124KB, markdown 119KB
