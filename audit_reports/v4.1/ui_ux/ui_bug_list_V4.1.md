# V4.1 UI/UX 新缺陷列表

> 版本: V4.1
> 日期: 2026-06-26
> 审计领域: UI/UX
> 环境: Docker (UI 领域端口隔离: 3010/8010/5433/6380)
> 测试浏览器: Chrome (agent-browser CDP) + 代码审查

---

## 分类统计

| 分类 | 数量 |
|------|------|
| 交互失效 | 4 |
| 视觉崩坏 | 5 |
| 体验卡顿 | 8 |
| **合计** | **17** |

| 严重度 | 数量 |
|--------|------|
| HIGH | 2 |
| MEDIUM | 5 |
| LOW | 10 |

---

## 【交互失效】

### BUG-001: TokenBatchRenderer 内存泄漏 — 模块级单例无法回收 (HIGH)

**文件**: `frontend/src/stream/TokenBatchRenderer.ts` lines 18-20, 90

**描述**: TokenBatchRenderer 是模块级单例（导出 initTokenBatcher/appendToken/flushImmediate），没有公开的 cleanup 方法。resetTokenBatcher 仅在 session reset 或 abort 时调用。如果用户发消息后离开聊天页，模块级变量（accumulatedContent, rafId, batchCallback）永远驻留内存。任何 pending rAF callback 引用 stale closure，可能造成内存泄漏。

**复现步骤**:
1. 发送消息触发流式输出
2. 在流式进行中切换到 Profile 页面
3. 返回聊天页 → 检查 streamContent 是否残留上次数据

**截图证据**: 无（运行时内存泄漏，需 Chrome DevTools Memory 面板确认）

---

### BUG-002: sendMessage 并发调用竞态条件 (HIGH)

**文件**: `frontend/src/store/chatStore.ts` lines 327-331

**描述**: send lock check 在 line 329-331 通过 `get()` 读取 Zustand state，但 lockSend() 在 line 334 执行。两次快速双击 Send 按钮可能在 329-334 的间隙中同时通过检查。更严重的是，`streamWithRetry` 内部函数（line 382）创建 AbortController 但不检查是否有其他流已在活动，可能导致交错响应。

**复现步骤**:
1. 输入消息后快速双击发送按钮（<100ms间隔）
2. 观察是否出现两条并发请求或 streamPhase 异常

**截图证据**: 无（竞态条件需极快操作触发）

---

### BUG-003: abortInterval 与 AbortController signal 冲突 (MEDIUM)

**文件**: `frontend/src/store/chatStore.ts` line 407, 446

**描述**: 当 SSE 流式超过 15s 无新 token 时，abortInterval handler 调用 `reader.cancel()`（line 446）而非通过 AbortController signal。reader.cancel() 抛出 DOMException（非 AbortError），在 catch block（line 506）中不会被 `error.name === 'AbortError'` 分支正确处理，导致截断消息可能丢失。

**复现步骤**:
1. 发送消息后等待 15+ 秒（AI 不回复）
2. 检查 abortInterval 是否触发 reader.cancel()
3. 确认 catch block 是否正确处理 DOMException vs AbortError

---

### BUG-004: 路由/Login 页面缺少全局 ErrorBoundary (MEDIUM)

**文件**: `frontend/src/layout/AppLayout.tsx` lines 853-861

**描述**: AppLayout 中的 ErrorBoundary 仅包裹 `<Outlet />` 主内容区域。LoginPage 和路由转换本身不在保护范围内。任何 auth 相关渲染崩溃会导致白屏。

**复现步骤**:
1. 在 LoginPage 组件中模拟渲染异常
2. 观察是否出现白屏而非友好错误提示

---

## 【视觉崩坏】

### BUG-005: 暗色模式硬编码颜色不一致 (MEDIUM)

**文件**: `MessageBubble.tsx` line 137, `CopyCodeButton.tsx` line 63, `AppLayout.tsx` lines 928/989

**描述**: 多个组件使用硬编码颜色值而非 CSS 变量，导致暗色模式下视觉不一致：
- 流式光标 `background: '#0052FF'` → 暗色模式应使用 `var(--accent)`
- 代码复制按钮 `color: '#52c41a'` → 暗色模式应使用 `#4ADE80`
- 侧边栏删除按钮文本 `color: '#ff4d4f'` → 可能与暗色背景对比度不足
- 卡片边线 `'#f0f0f0'` fallback → 在暗色背景 `#1E293B` 上几乎不可见

**复现步骤**:
1. 切换到暗色模式
2. 发送消息 → 观察流式光标颜色是否过于明亮
3. 发送含代码的消息 → 观察复制按钮 success 颜色对比度
4. 右键对话 → 观察删除按钮文本颜色

**截图证据**: `v41_ui_dark_mode.png`

---

### BUG-006: 浮动输入框在小屏设备 (< 768px) 被裁切 (MEDIUM)

**文件**: `frontend/src/pages/ChatPage.tsx` lines 341-436

**描述**: 输入框使用 `position: fixed; bottom: 32px`，在移动端浏览器地址栏收缩/展开时可见视口高度波动。`bottom: 32px` 偏移可能将输入框部分置于可见区域之下。内容器 `maxWidth: 720px` + `padding: 0 24px` 在 <500px 屏幕宽度可能造成水平溢出。无响应式调整。

**复现步骤**:
1. 在 <400px 宽度的设备/模拟器上打开页面
2. 触发浏览器地址栏展开（向上滚动）
3. 观察输入框是否被裁切或不可见

---

### BUG-007: 上下文菜单溢出屏幕边界 (LOW)

**文件**: `frontend/src/layout/AppLayout.tsx` lines 867-937, 939-997

**描述**: 右键菜单和侧边栏操作菜单使用原始 `top/left` 定位，无边界计算。在视口右边缘或底部附近触发菜单时，弹窗延伸到可见区域外，无法操作。

**复现步骤**:
1. 右键点击侧边栏底部最后一个对话
2. 观察菜单是否被视口底部裁切

---

### BUG-008: VirtualizedMessageList initialTopMostItemIndex 列表跳动 (LOW)

**文件**: `frontend/src/components/chat/VirtualizedMessageList.tsx` line 172

**描述**: `initialTopMostItemIndex={data.length - 1}` 设置初始滚动位置到最后一条消息。当流式完成时 streaming placeholder 被替换为正式消息，Virtuoso 重新计算导致轻微上跳。

**复现步骤**:
1. 连续发送多条消息
2. 观察每次流式完成时列表是否轻微上跳

---

### BUG-009: CSS :has() 选择器 Safari 兼容性 (LOW)

**文件**: `frontend/src/styles/globals.css` line 610

**描述**: `.ant-input-affix-wrapper:has(#sidebar-search-input)` 使用 CSS :has() 伪类，Safari < 15.4 不支持。旧版 Safari 用户侧边栏搜索输入框高度可能错位。

---

## 【体验卡顿】

### BUG-010: 跨标签同步事件无 Toast 反馈 (MEDIUM)

**文件**: `frontend/src/sync/crossTabSync.ts` lines 35-74

**描述**: 当 initCrossTabSync 接收到 `session-delete` 或 `session-switch` 事件时，静默更新 Zustand state、abort 流、reset store。用户没有视觉或听觉指示告知 session 被另一个标签页修改。同样，AppLayout 中的 `handleDeleteSession` 删除对话后无 Toast 确认。

**复现步骤**:
1. 在两个浏览器标签中同时登录
2. 在标签 A 中删除一个对话
3. 在标签 B 中观察 → 无任何提示，对话突然消失

---

### BUG-011: 移动端 Drawer 自动弹出行为不友好 (LOW)

**文件**: `frontend/src/layout/AppLayout.tsx` lines 80-87

**描述**: `ey-mobile-drawer-seen` localStorage 标志仅保存 2 秒。2 秒后 drawer 自动关闭，对首次移动端用户缺乏引导意义。

---

### BUG-012: 侧边栏搜索不展开已折叠分组 (LOW)

**文件**: `frontend/src/layout/AppLayout.tsx` lines 212-226, 414-438

**描述**: 搜索过滤对话时，已折叠的时间分组保持折叠。如果搜索匹配的对话在折叠分组中，用户看不到结果。

**复现步骤**:
1. 折叠侧边栏时间分组
2. 搜索某对话名称
3. 匹配结果隐藏在折叠分组中

---

### BUG-013: HistoryPage 时间分组逻辑与侧边栏不一致 (LOW)

**文件**: `frontend/src/pages/HistoryPage.tsx` lines 72, 82, 15

**描述**: HistoryPage 使用硬编码 `TimeFilter` 含 `'earlier'`（"本月之前"），而侧边栏 dateGroup 使用月级别动态键。同一对话列表在不同入口显示不同的时间边界。

---

### BUG-014: 异步 Logout 导航时序问题 (LOW)

**文件**: `frontend/src/auth/AuthProvider.tsx` lines 62-70

**描述**: logout 函数 await API 调用后清除 state，但 AppLayout 中 logout 后立即 navigate('/login')。如果 API logout 失败，本地 state 仍然被清除，用户被导航到登录页。如果登录页有问题，用户陷入卡住状态。

---

### BUG-015: 主题切换缺少视觉反馈动画 (LOW)

**文件**: `frontend/src/hooks/useTheme.ts` lines 62-66

**描述**: setThemeMode 写 localStorage 并 notifyAll()，图标切换是唯一反馈。无 ripple/spin 过渡动画，用户可能不察觉主题已变。

---

### BUG-016: WelcomeScreen 快捷操作焦点管理缺失 (LOW)

**文件**: `frontend/src/components/chat/WelcomeScreen.tsx` lines 186-217

**描述**: 快捷操作卡片有 role="button" + tabIndex={0} + Enter/Space handler，但触发后焦点停留在卡片上而非移到聊天输入框。键盘导航用户体验不佳。

---

### BUG-017: 滚动到底部按钮双阈值冲突 (LOW)

**文件**: `frontend/src/pages/ChatPage.tsx` lines 89, 119-125, 314

**描述**: "新消息" 按钮可见性由 IntersectionObserver threshold=0.1 和 scroll heuristic 100px 阈值共同决定。两者可能不一致，导致按钮在高频滚动时短暂闪烁。

---

## 截图清单

| 文件名 | 内容 |
|--------|------|
| v41_ui_overview.png | 亮色模式聊天页全览 |
| v41_ui_dark_mode.png | 暗色模式聊天页 |
| v41_sidebar_dark_expanded.png | 暗色模式侧边栏展开 |
| v41_sidebar_light_expanded.png | 亮色模式侧边栏展开 |
| reg_v4_ui_overflow_closeup.png | V4.0 代码溢出回测 |
| reg_v4_ui_overflow_annotated.png | V4.0 代码溢出注释截图 |
