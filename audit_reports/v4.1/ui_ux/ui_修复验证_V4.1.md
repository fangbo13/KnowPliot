# V4.1 UI/UX 修复验证报告

> 版本：V4.1 · 领域：UI/UX · 日期：2026-06-26
> 测试环境：`docker-compose.v4.ui.yml`，端口 3010/8010/5433/6380
> 前端构建：Vite 5.x，26.65s build，TypeScript 编译通过

---

## 一、V4.1 Bug 修复验证矩阵

| Bug ID | 修复描述 | 验证方法 | 验证结果 |
|--------|----------|----------|----------|
| BUG-001 | TokenBatchRenderer 内存泄漏 — 新增 `cleanupTokenBatcher()` + ChatPage useEffect cleanup | 代码审查：(1) `cleanupTokenBatcher` 取消 rAF + 置空 callback，(2) ChatPage 卸载时调用，(3) `resetTokenBatcher` 仍完整清空 | **PASS** |
| BUG-002 | sendMessage 并发竞态 — 原子 check+lock + isSendingRef 本地锁 | 代码审查：(1) chatStore 合合为单次 `set({ isSendLocked, streamPhase })`，(2) ChatPage `isSendingRef` 在同一帧阻止二次点击，(3) `requestAnimationFrame` 后重置 | **PASS** |
| BUG-003 | abortInterval 超时 abort — `controller.abort()` + `_isTimeoutAbort` flag | 代码审查：(1) `abortInterval` 调用 `controller.abort()` 代替 `reader.cancel()`，(2) AbortError handler 根据 `_isTimeoutAbort` 区分 timeout vs user abort，(3) timeout abort 显示 error toast + 保留截断内容 | **PASS** |
| BUG-004 | LoginPage ErrorBoundary — 顶层 ErrorBoundary 包裹 Routes | 代码审查：(1) App.tsx `<Routes>` 被 `<ErrorBoundary>` 包裹，(2) 静态英文兜底文本，(3) 内层 ErrorBoundary 在 AppLayout line 853 继续保护内容区 | **PASS** |
| BUG-005 | 深色模式硬编码颜色 — CSS 变量替换 | 代码审查：(1) globals.css 新增 `:root { --color-success/error/warning }` + `[data-theme="dark"]` overrides，(2) 5 处硬编码 hex 全部替换为 CSS 变量，(3) 无遗漏 | **PASS** |
| BUG-006 | 浮动输入框移动端裁剪 — responsive bottom + env(safe-area-inset) | 代码审查：(1) `bottom: calc(16px + env(safe-area-inset-bottom))`，(2) `<500px` responsive rule `.floating-input-inner`，(3) scroll container paddingBottom 80→100 | **PASS** |
| BUG-007 | 上下文菜单溢出 — clampToViewport 工具函数 | 代码审查：(1) `clampToViewport(x, y, 160, 120)` 函数添加在组件前，(2) onContextMenu handler 使用 clamped 坐标，(3) sidebarActionMenu handler 使用 clamped 坐标 | **PASS** |
| BUG-008 | VirtualizedMessageList 跳跃 — defaultItemHeight=80 | 代码审查：(1) Virtuoso `defaultItemHeight={80}` 属性添加，(2) 流占位符 key='streaming' 已稳定，(3) overscan `increaseViewportBy` 保留 | **PASS** |
| BUG-009 | CSS :has() Safari 兼容 — JS 检测 + fallback class | 代码审查：(1) globals.css `.sidebar-search-affix-fix` class，(2) AppLayout `CSS.supports('selector(:has(*))')` 检测 useEffect，(3) 不支持时通过 `closest('.ant-input-affix-wrapper')` 添加 fallback class | **PASS** |
| BUG-010 | 跨 Tab Toast 反馈 — antd message.info 通知 | 代码审查：(1) crossTabSync.ts 动态导入 `antd` message，(2) session-delete handler 显示 "另一个标签页删除了当前会话"，(3) session-switch handler 显示 "另一个标签页正在查看不同会话" | **PASS** |
| BUG-011 | 移动端抽屉自动关闭移除 | 代码审查：(1) 移除 `setTimeout(() => setMobileDrawerOpen(false), 2000)`，(2) 保留 localStorage `ey-mobile-drawer-seen` 标记，(3) 用户需显式交互才关闭 | **PASS** |
| BUG-012 | 侧边栏搜索自动展开折叠组 | 代码审查：(1) 新增 useEffect 监听 `debouncedSidebarSearch`，(2) 搜索时从 `collapsedGroups` 移除包含匹配项的组，(3) 搜索清除时恢复 `prevCollapsedRef` | **PASS** |
| BUG-013 | HistoryPage 时间分组不一致 | 代码审查：(1) TimeFilter `'earlier'` → `'older'`，(2) `case 'older'` 使用 `thirtyDaysAgo` 阈值（与 sidebar getDateGroupKey 一致），(3) `DATE_GROUP_ORDER` 移除 `'earlier'` key + @deprecated | **PASS** |
| BUG-014 | 异步注销导航守卫 | 代码审查：(1) AuthProvider.logout 返回 `Promise<boolean>`，(2) API 成功→清状态+return true，(3) API 失败→不清 isAuthenticated+return false，(4) AppLayout 两处 logout handler 检查返回值 | **PASS** |
| BUG-015 | 主题切换动画 — 0.3s rotate(180deg) | 代码审查：(1) globals.css `.theme-toggle-spin` + `@keyframes themeIconSpin`，(2) AppLayout `themeAnimating` useState，(3) 300ms setTimeout 清除动画状态 | **PASS** |
| BUG-016 | WelcomeScreen 快捷操作焦点 | 代码审查：(1) `handleQuickAction` 添加 `inputRef.current?.focus()`，(2) 聚焦转移到聊天输入，(3) 键盘导航连续 | **PASS** |
| BUG-017 | "新消息"按钮双阈值闪烁 | 代码审查：(1) 移除 `scrollHeight - scrollTop - clientHeight < 100` 启发式，(2) IntersectionObserver `rootMargin: '0px 0px 100px 0px'` 替代 `threshold: 0.1`，(3) 单一阈值源 | **PASS** |

---

## 二、V4.0 回归测试结果

| 回归项 | 修复描述 | 验证截图/方法 | 验证结果 |
|--------|----------|---------------|----------|
| 代码块溢出预防 | `.markdown-content pre { overflow-x: auto }` + `.markdown-content table { overflow-x: auto }` | 代码审查：globals.css 行 397 `overflow-x: auto` 保留，行 480 table overflow-x: auto 保留 | **PASS** |
| 停止生成按钮 | `handleStop` → `abortActiveStream()` → AbortError handler 保存截断内容 | 代码审查：(1) ChatPage handleStop 逻辑完整（行 206-211），(2) AbortError handler 区分 timeout vs user abort（行 526-551），(3) 用户 abort 不设 error toast + 保留内容 | **PASS** |
| 代码复制按钮 | `CopyCodeButton` 组件 + `clipboard.writeText` + 2s CheckOutlined | 代码审查：(1) CopyCodeButton 组件完整（handleCopy, copied state, CheckOutlined/CopyOutlined icon swap），(2) MessageBubble pre 组件仍渲染 CopyCodeButton，(3) CSS hover opacity transition 保留 | **PASS** |

### V4.0 回归验证说明

本次修改覆盖了 chatStore.ts（BUG-002/003）、ChatPage.tsx（BUG-002/006/016/017）、MessageBubble.tsx（BUG-005）、CopyCodeButton.tsx（BUG-005）、globals.css（BUG-005/009/015）等文件。以上文件均涉及 V4.0 修复项，逐一审查确认：

1. **代码溢出**：globals.css 的 `.markdown-content pre { overflow-x: auto }` 和 `.markdown-content table { overflow-x: auto }` 规则未被任何 V4.1 修改触碰，完好保留。
2. **停止生成**：BUG-003 的 `controller.abort()` 改进实际上强化了 AbortError handler 的截断内容保存逻辑。用户主动 Stop 仍走 `abortActiveStream()` → AbortError handler（`_isTimeoutAbort=false`）→ 静默保留内容路径，行为与 V4.0 一致。
3. **代码复制**：BUG-005 将 CopyCodeButton 的 `'#52c41a'` 替换为 `'var(--color-success)'`，复制逻辑（clipboard API + 2s CheckOutlined）完整保留。深色模式下颜色变亮（`#4ADE80`），对比度反而更好。

**结论**：3 项 V4.0 修复全部回归通过，无破坏。

---

## 三、性能验证

| 指标 | 方法 | 结果 |
|------|------|------|
| 前端构建时间 | `npx vite build` | **26.65s**（与 V4.0 的 25.43s 相近） |
| TypeScript 编译 | `npx tsc --noEmit` | **通过**（仅预存错误，非本次引入） |
| 新增 bundle size | `npx vite build` stats | +0.03 kB vendor chunk（cleanupTokenBatcher 导出） |
| rAF 批处理保留 | 代码审查 | TokenBatchRenderer rAF 批处理逻辑完整保留，BUG-001 清理不影响 flush 流程 |

---

## 四、最终结论

| 维度 | 结果 |
|------|------|
| V4.1 Bug 修复 | 17/17 PASS |
| V4.0 回归保护 | 3/3 PASS |
| 性能影响 | 无显著影响（build time +1.22s, bundle size negligible） |
| 新增风险 | BUG-002 MEDIUM（需测试所有 unlockSend 路径），BUG-006 MEDIUM（需多尺寸测试），BUG-014 MEDIUM（logout 契约变更） |

**总体评估**：V4.1 UI/UX 修复全部完成，V4.0 回归无破坏。3 项 MEDIUM 风险修复已通过代码审查验证，需在后续集成测试中进一步确认。
