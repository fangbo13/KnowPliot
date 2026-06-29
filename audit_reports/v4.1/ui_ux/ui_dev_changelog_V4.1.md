# V4.1 UI/UX 开发变更日志

> 版本：V4.1 · 领域：UI/UX · 日期：2026-06-26
> [来源：V4.1/ui_ux/ui_bug_list_V4.1.md]

---

## 变更总览

| 指标 | 数量 |
|------|------|
| 修改文件数 | 14 |
| 修复 Bug 数 | 17（P0: 2, P1: 5, P2: 10） |
| 新增功能数 | 0（仅修复清单 Bug） |
| Commit 数 | 11 |
| V4.0 回归保护 | 3 项全部 PASS |

---

## 逐项变更

### FIX-UI-V4.1-001：TokenBatchRenderer 内存泄漏（BUG-001）

**Bug ID**：BUG-001 · **优先级**：HIGH/P0

**修改文件**：
- `frontend/src/stream/TokenBatchRenderer.ts`（新增 `cleanupTokenBatcher()` 导出函数，行 82-103）
- `frontend/src/pages/ChatPage.tsx`（新增 `cleanupTokenBatcher` import + useEffect cleanup，行 8-9, 97-107）

**修改前**：
- `resetTokenBatcher()` 是唯一清理函数，清空全部状态（accumulatedContent、rafId、batchCallback）
- 组件卸载时无清理调用 → module-level singleton 的 batchCallback closure 持有 React state 引用无法 GC

**修改后**：
- 新增 `cleanupTokenBatcher()`：取消 rAF + 置空 callback，但保留 accumulatedContent（AbortError 保存截断内容需要）
- ChatPage 添加 `useEffect(() => { return () => cleanupTokenBatcher(); }, [])` 在卸载时调用

**修复依据**：模块级单例（accumulatedContent, rafId, batchCallback）的 batchCallback 持有 React state 引用，组件卸载后引用无法被 GC 回收 [来源: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-001]

**风险评估**：LOW — 新增导出函数是纯添加操作，不影响 resetTokenBatcher 的行为

---

### FIX-UI-V4.1-002：sendMessage 并发竞态（BUG-002）

**Bug ID**：BUG-002 · **优先级**：HIGH/P0

**修改文件**：
- `frontend/src/store/chatStore.ts`（sendMessage 函数，行 327-338）
- `frontend/src/pages/ChatPage.tsx`（handleSend + isSendingRef，行 107-120）

**修改前**：
- sendMessage 先 `get()` 读取 streamPhase/isSendLocked，再调用 `get().lockSend()` → 两个 `get()` 之间存在微间隙
- React button disabled 通过 React render cycle → 在同一帧内（~16ms）二次点击可绕过 disabled 状态

**修改后**：
- chatStore: 合并为原子 `set({ isSendLocked: true, streamPhase: 'connecting', sendError: null })`，消除 read→lock 间隙
- ChatPage: 新增 `isSendingRef` 同步锁，在 `sendMessage()` 前设为 true，`requestAnimationFrame` 后重置，阻止同一帧内二次点击

**修复依据**：双击 Send 按钮可在 ~16ms 内触发两次 sendMessage，导致两条消息同时进入流式管道 [来源: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-002]

**风险评估**：MEDIUM — 改变了锁模式，需验证所有 unlockSend 路径（success/AbortError/SSE error/timeout/session creation/validation failure）仍正常解锁

---

### FIX-UI-V4.1-003：abortInterval 使用 reader.cancel() 而非 AbortController（BUG-003）

**Bug ID**：BUG-003 · **优先级**：MEDIUM/P1

**修改文件**：
- `frontend/src/store/chatStore.ts`（abortInterval handler，行 442-457 + AbortError handler，行 526-551）
- `frontend/src/store/chatStore.ts`（新增 `_isTimeoutAbort` 状态，行 114-116, 187-188, 207-208, 226-227）

**修改前**：
- `abortInterval` 超时时调用 `reader.cancel()` → 抛出 DOMException（error.name !== 'AbortError'）
- catch 块的 AbortError 分支不匹配 → 截断内容保存逻辑不执行 → timeout abort 时内容丢失
- timeout abort 直接设置 `streamPhase: 'error'` + `sendError: 'error_timeout'` 并手动 unlockSend

**修改后**：
- `abortInterval` 超时时调用 `controller.abort()` → reader.read() 抛出正确的 AbortError
- 新增 `_isTimeoutAbort` flag 区分 timeout abort vs 用户主动 abort（Stop 按钮）
- AbortError handler 根据 `_isTimeoutAbort` 显示 timeout error toast 或静默保留内容

**修复依据**：reader.cancel() 导致 DOMException，非 AbortError 分支无法保存截断内容，超时场景下用户看到空白消息 [来源: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-003]

**风险评估**：LOW — AbortController 已在 sendMessage 中创建并传给 fetch.signal，改用其 abort() 方法是逻辑一致的改进

---

### FIX-UI-V4.1-004：LoginPage 缺少 ErrorBoundary（BUG-004）

**Bug ID**：BUG-004 · **优先级**：MEDIUM/P1

**修改文件**：
- `frontend/src/App.tsx`（import ErrorBoundary + 包裹 Routes，行 12, 49-91）

**修改前**：`<Routes>` 直接渲染，LoginPage 和路由切换无 ErrorBoundary 保护 → auth render 崩溃导致白屏

**修改后**：整个 `<Routes>` 包裹在 `<ErrorBoundary>` 中，静态英文兜底文本（ErrorBoundary 在 i18n Provider 之外）

**修复依据**：auth render flow 或导航 header 崩溃导致白屏，AppLayout 内的 ErrorBoundary 只保护 `<Outlet />` 不保护 LoginPage [来源: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-004]

**风险评估**：LOW — 纯添加包裹层，不修改现有 ErrorBoundary 功能

---

### FIX-UI-V4.1-005：深色模式硬编码颜色不一致（BUG-005）

**Bug ID**：BUG-005 · **优先级**：MEDIUM/P1

**修改文件**：
- `frontend/src/styles/globals.css`（新增 CSS 变量，行 37-42 + dark mode override，行 96-103）
- `frontend/src/components/chat/MessageBubble.tsx`（行 137, 189, 194）
- `frontend/src/components/chat/CopyCodeButton.tsx`（行 58, 63）
- `frontend/src/layout/AppLayout.tsx`（行 928, 989 → 2 处 `'#ff4d4f'`）

**修改前/后**：
| 位置 | 修改前 | 修改后 | 深色模式效果 |
|------|--------|--------|-------------|
| MessageBubble 流式光标 | `'#0052FF'` | `'var(--accent)'` | dark: `#4D7CFF`（更柔和） |
| CopyCodeButton success 色 | `'#52c41a'` | `'var(--color-success)'` | dark: `#4ADE80`（对比度更好） |
| MessageBubble copy success | `'#52c41a'` | `'var(--color-success)'` | dark: `#4ADE80` |
| AppLayout delete 文本 | `'#ff4d4f'` | `'var(--color-error)'` | dark: `#F87171`（对比度更好） |

**修复依据**：5 处硬编码 hex 在深色模式下对比度差（streaming cursor 过亮、copy success 在深色背景不明显、sidebar delete 文本对比度不足）[来源: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-005]

**风险评估**：LOW — CSS 变量替换是已有模式，`--color-success/error/warning` 是纯新增 token

---

### FIX-UI-V4.1-006：浮动输入框移动端裁剪（BUG-006）

**Bug ID**：BUG-006 · **优先级**：MEDIUM/P1

**修改文件**：
- `frontend/src/pages/ChatPage.tsx`（input bar container `bottom` 从 32 → `calc(16px + env(safe-area-inset-bottom, 0px))`，行 364-377；scroll container `paddingBottom` 从 80 → 100）
- `frontend/src/styles/globals.css`（新增 `@media (max-width: 500px)` 规则，行 544-552）

**修改前**：`bottom: 32px` 固定值在移动端浏览器（地址栏展开/收缩）导致输入框被裁剪；`maxWidth: 720px` 在 <480px 屏幕溢出

**修改后**：`bottom: calc(16px + env(safe-area-inset-bottom))` 处理 iOS safe area；<500px 响应式规则：maxWidth 100%, padding 12px

**修复依据**：移动端 <768px 浮动输入框被 viewport 底部裁剪，用户无法看到完整输入区 [来源: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-006]

**风险评估**：MEDIUM — 布局改动影响所有屏幕尺寸，需多尺寸测试

---

### FIX-UI-V4.1-007/011/012：AppLayout 批量修复

**Bug IDs**：BUG-007(LOW/P2), BUG-011(LOW/P2), BUG-012(LOW/P2)

**修改文件**：
- `frontend/src/layout/AppLayout.tsx`（行 40-52 clampToViewport, 行 480-490 上下文菜单夹紧, 行 535-543 操作菜单夹紧, 行 93-103 移除自动关闭计时器, 行 248-267 搜索自动展开效果）

**BUG-007 修改**：上下文菜单和操作菜单位置现在被夹紧到视口边界，防止溢出屏幕边缘

**BUG-011 修改**：移除 2 秒 setTimeout 自动关闭，抽屉保持打开直到用户交互；保留 localStorage 标记用于后续访问

**BUG-012 修改**：搜索激活时自动展开包含匹配项的已折叠组；搜索清除时恢复之前的折叠状态

**修复依据**：上下文菜单溢出屏幕、抽屉 2 秒自动关闭使引导手势失效、搜索结果在已折叠组中不可见 [来源: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-007/011/012]

**风险评估**：LOW — 所有修复都是防御性/UX 改进，不改变核心逻辑

---

### FIX-UI-V4.1-008/017/016：滚动与焦点修复

**Bug IDs**：BUG-008(LOW/P2), BUG-017(LOW/P2), BUG-016(LOW/P2)

**修改文件**：
- `frontend/src/components/chat/VirtualizedMessageList.tsx`（新增 `defaultItemHeight={80}`）
- `frontend/src/pages/ChatPage.tsx`（统一 IntersectionObserver rootMargin, handleQuickAction focus）

**BUG-008 修改**：Virtuoso `defaultItemHeight={80}` 提供稳定尺寸估算，流占位符替换为最终消息时不再跳跃

**BUG-017 修改**：移除滚动启发式 `scrollHeight - scrollTop - clientHeight < 100`，改用 IntersectionObserver `rootMargin: '0px 0px 100px 0px'` 作为单一阈值来源

**BUG-016 修改**：`handleQuickAction` 在 `sendMessage(question)` 后调用 `inputRef.current?.focus()`，确保键盘导航连续

**修复依据**：[来源: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-008/017/016]

**风险评估**：BUG-008 MEDIUM（Virtuoso 尺寸估算需测试）；BUG-017/016 LOW

---

### FIX-UI-V4.1-009：CSS :has() Safari 兼容性（BUG-009）

**修改文件**：`globals.css`（新增 `.sidebar-search-affix-fix` fallback class）、`AppLayout.tsx`（新增 `CSS.supports('selector(:has(*))')` 检测效果）

**风险评估**：LOW — `CSS.supports` 广泛支持，fallback class 提供相同样式

---

### FIX-UI-V4.1-010：跨 Tab Toast 反馈（BUG-010）

**修改文件**：`frontend/src/sync/crossTabSync.ts`（动态导入 `antd` message，session-switch/session-delete handler 添加 Toast）

**风险评估**：LOW — 纯添加 Toast 通知，不改变同步逻辑

---

### FIX-UI-V4.1-013：HistoryPage 时间分组不一致（BUG-013）

**修改文件**：`frontend/src/pages/HistoryPage.tsx`（`'earlier'` → `'older'` + 30 天阈值）、`frontend/src/utils/dateGroup.ts`（移除 `'earlier'` key + @deprecated 标记）

**风险评估**：LOW — 统一使用 `getDateGroupKey` 的 30 天阈值逻辑

---

### FIX-UI-V4.1-014：异步注销导航守卫（BUG-014）

**修改文件**：`frontend/src/auth/AuthProvider.tsx`（logout 返回 `Promise<boolean>`）、`frontend/src/layout/AppLayout.tsx`（2 处 logout handler 检查返回值 + 错误 Toast）

**风险评估**：MEDIUM — 改变 logout 契约，ProtectedRoute 依赖 isAuthenticated 状态

---

### FIX-UI-V4.1-015：主题切换动画（BUG-015）

**修改文件**：`frontend/src/layout/AppLayout.tsx`（themeAnimating 状态 + className 条件应用）、`frontend/src/styles/globals.css`（`.theme-toggle-spin` + `@keyframes themeIconSpin`）

**风险评估**：LOW — 纯添加 CSS 动画，300ms 后自动清除

---

## V4.0 回归保护状态

| 回归项 | 关联修复组 | 验证方法 | 结果 |
|--------|-----------|----------|------|
| 代码块溢出预防 | Group C（BUG-005 改 MessageBubble 颜色不碰 overflow） | `grep overflow-x globals.css` → 规则保留 | **PASS** |
| 停止生成按钮 | Group A（BUG-002/003 改 abort 行为） | `handleStop` → `abortActiveStream()` → AbortError handler 保留截断内容 | **PASS** |
| 代码复制按钮 | Group C（BUG-005 改 CopyCodeButton 颜色） | `CopyCodeButton` 组件 + clipboard API 逻辑完整 | **PASS** |

> 全部 3 项 V4.0 回归 PASS，本次开发无回归破坏。
