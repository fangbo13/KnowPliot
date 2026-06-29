# V4.2 UI/UX 开发变更日志

> 版本: V4.2 · 领域: UI/UX · 日期: 2026-06-26
> 开发者: Claude (资深前端交互工程师)
> 输入: `audit_reports/v4.2/ui_ux/ui_bug_list_V4.2.md` (12 个缺陷)
> 前端构建: Vite 5.x, 24.39s build, TypeScript 预存错误不变

---

## 修复概览

| 严重度 | 修复数 | 验证结果 |
|--------|--------|----------|
| P1 (严重) | 2 | ✅ PASS |
| P2 (一般) | 7 | ✅ PASS |
| P3 (轻微) | 3 | ✅ PASS |
| **合计** | **12** | **12/12 PASS** |

---

## P1 修复详情

### UI-V4.2-001: CrawlerAdminPage useEffect 无空依赖数组

**问题**: `useEffect(() => { fetchDocs(); }, [fetchDocs])` 依赖数组包含 useCallback 函数 `fetchDocs`，语言切换/HMR 导致 fetchDocs 重建触发全量 API 请求风暴。

**修复**: 改为 `useEffect(() => { fetchDocs(); }, [])` — 仅在组件 mount 时执行一次。后续刷新由 polling interval（5000ms）和手动 Refresh 按钮触发。

**文件**: `frontend/src/pages/admin/CrawlerAdminPage.tsx` lines 76-78

**影响**: 消除语言切换/HMR 时的 API 请求风暴，降低被限流拦截风险。

---

### UI-V4.2-002: handleRetry 绕过 sendLock + offline 检查

**问题**: `handleRetry` 直接调用 `sendMessage(lastUserMsg.content)`，绕过了 handleSend 的完整守卫链（isStreaming / isSendLocked / isSendingRef / navigator.onLine），导致离线 Retry 仍发出请求或并发双流。

**修复**: 将 handleRetry 重构为复用 handleSend 的完整守卫逻辑：
- 添加 `isStreaming || isSendLocked || isSendingRef.current` 检查
- 添加 `navigator.onLine` 检查 + offline warning toast
- 使用 `isSendingRef` 同步守卫 + `requestAnimationFrame` 重置
- 原子操作：先 setSendError(null)，再 isSendingRef=true，再 sendMessage

**文件**: `frontend/src/pages/ChatPage.tsx` lines 202-208

**影响**: 消除离线无效请求和并发双流风险，Retry 行为与 Send 行为完全一致。

---

## P2 修复详情

### UI-V4.2-003: 网络错误 alert 硬编码亮色背景

**问题**: `border: '2px solid #ff4d4f'` + `background: '#fff2f0'` 硬编码 Ant Design 亮色值，暗色模式下形成刺眼亮白矩形。同时 `animation: 'slideDown 0.3s ease-out'` 引用 keyframe 但此处的 Alert 自带动画。

**修复**: 
- `#ff4d4f` → `var(--color-error)`（暗色模式解析为 `#F87171`）
- `#fff2f0` → `rgba(var(--color-error-rgb, 239, 68, 68), 0.08)`（轻透红色，暗色模式为 `rgba(248, 113, 113, 0.08)`）
- 移除 `animation: 'slideDown'`（冗余，antd Alert 有自带入场动画）
- 在 globals.css `:root` 和 `[data-theme="dark"]` 新增 `--color-error-rgb`、`--color-success-rgb`、`--color-warning-rgb` RGB 分量变量

**文件**: `frontend/src/pages/ChatPage.tsx` lines 304-308 + `frontend/src/styles/globals.css` lines 41-44, 118-121

---

### UI-V4.2-004: AppLayout logo 容器阴影硬编码 rgba

**问题**: `boxShadow: '0 2px 8px rgba(0, 82, 255, 0.25)'` 硬编码原始蓝色，暗色模式 accent 为 `#4D7CFF` 但阴影色调不一致。

**修复**: 替换为 `var(--shadow-accent)`（亮色: `rgba(0, 82, 255, 0.25)`，暗色: `rgba(77, 124, 255, 0.2)`）。入职弹窗 logo 阴影也同步修复为 `var(--shadow-accent-lg)`。

**文件**: `frontend/src/layout/AppLayout.tsx` lines 383, 652

---

### UI-V4.2-005: AdminDashboardPage Active Users 计数器硬编码绿色

**问题**: `color: '#52c41a'` 硬编码 Ant Design 亮色绿，暗色模式对比度不足。

**修复**: 替换为 `var(--color-success)`（亮色: `#22C55E`，暗色: `#4ADE80`）。

**文件**: `frontend/src/pages/admin/AdminDashboardPage.tsx` line 224

---

### UI-V4.2-006: MessageBubble 相关性颜色硬编码

**问题**: `getRelevanceColor(score)` 返回 `#52c41a`、`#faad14`、`#8c8c8c` 硬编码值，暗色模式对比度不足。

**修复**: 改为 CSS 变量：
- `score > 0.8` → `var(--color-success)`
- `score > 0.5` → `var(--color-warning)`
- 其他 → `var(--color-text-tertiary)`

**文件**: `frontend/src/components/chat/MessageBubble.tsx` lines 35-39

---

### UI-V4.2-007: globals.css 侧边栏 hover 使用未定义 --color-fill

**问题**: `.sidebar-session-item:hover`、`.new-chat-btn:hover`、`.sidebar-chat-item:hover` 使用 `var(--color-fill)`，但 `--color-fill` 和 `--color-fill-secondary` 不在 `:root` 或 `[data-theme="dark"]` 中定义（Ant Design 内部 theme token，仅在 ConfigProvider context 中可用），导致侧边栏 hover 完全无视觉反馈。

**修复**: 在 globals.css 定义：
- `:root`: `--color-fill: rgba(0, 82, 255, 0.04)` + `--color-fill-secondary: rgba(0, 82, 255, 0.06)`
- `[data-theme="dark"]`: `--color-fill: rgba(77, 124, 255, 0.08)` + `--color-fill-secondary: rgba(77, 124, 255, 0.12)`

**文件**: `frontend/src/styles/globals.css` lines 46-52 (light), 126-127 (dark)

---

### UI-V4.2-010: ErrorBoundary 重试 = window.location.reload() 丢失全部 SPA 状态

**问题**: `window.location.reload()` 杀死全部 Zustand 状态、断开 SSE/WebSocket、重置整个 SPA。用户丢失未保存的聊天内容和登录状态。

**修复**: 将 `onClick={() => window.location.reload()}` 改为 `onClick={this.handleRetry}`，其中 `handleRetry = () => this.setState({ hasError: false, error: null })`。React 重置 state 后重新渲染 children，仅重挂载失败子树，保留全局状态。

**文件**: `frontend/src/components/ErrorBoundary.tsx` lines 43-49

---

### UI-V4.2-011: AdminDashboardPage 系统健康状态全部硬编码

**问题**: `loadSystemStatus` 获取 auditRes 但完全不使用响应数据，所有状态字段硬编码为 'running'/'connected'。API 失败后 backend_status/db_status 仍显示 'running'/'connected'。

**修复**: 
- API 成功：`backend_status: 'running'`，`db_status: 'connected'`，`total_documents: auditRes.data.count`（使用真实审计日志数）
- API 失败：区分网络错误（`backend_status: 'down'`，`db_status: 'disconnected'`）与 HTTP 错误（`backend_status: 'degraded'`，`db_status: 'unknown'`）
- Tag 颜色动态映射：running→green，degraded/unknown→orange，down/disconnected→red

**文件**: `frontend/src/pages/admin/AdminDashboardPage.tsx` lines 63-88, 218-228

---

## P3 修复详情

### UI-V4.2-008: Source count emoji 非屏幕阅读器友好

**问题**: `📎` (U+1F4CE) emoji 作为引用图标前缀，屏幕阅读器可能朗读 Unicode 名称而非本地化文字。

**修复**: 替换为 `<PaperClipOutlined aria-label={t('sources')} />` — 语义化图标 + 本地化 aria-label。

**文件**: `frontend/src/components/chat/MessageBubble.tsx` line 401

---

### UI-V4.2-009: Chat 输入字数计数器无 ARIA live region

**问题**: `{inputValue.length}/4000` 纯视觉展示，无 `aria-live` 或 `role="status"`，屏幕阅读器用户无法感知字数变化。同时计数器颜色也使用硬编码 `#ff4d4f`/`#faad14`。

**修复**: 
- 添加 `role="status" aria-live="polite" aria-label={...}`
- 同时修复硬编码颜色：`#ff4d4f` → `var(--color-error)`，`#faad14` → `var(--color-warning)`

**文件**: `frontend/src/pages/ChatPage.tsx` lines 463-474

---

### UI-V4.2-012: NetworkStatusBanner animation 引用未定义 keyframe

**问题**: `animation: 'slideDown 0.3s ease-out'` 引用 `@keyframes slideDown`（已在 globals.css 定义，但 inline animation 在严格 CSP 环境下可能阻断）。antd Alert 有自带入场动画，此 inline animation 属冗余死代码。

**修复**: 移除 inline `animation` 属性，依赖 antd Alert 内置入场动画。

**文件**: `frontend/src/components/NetworkStatusBanner.tsx` line 38

---

## 修改文件清单

| 文件 | 修改类型 | Bug IDs |
|------|----------|---------|
| `frontend/src/pages/admin/CrawlerAdminPage.tsx` | useEffect 依赖修复 | 001 |
| `frontend/src/pages/ChatPage.tsx` | handleRetry 守卫 + ARIA + CSS 变量 | 002, 003, 009 |
| `frontend/src/pages/admin/AdminDashboardPage.tsx` | 健康状态真实化 + CSS 变量 | 005, 011 |
| `frontend/src/layout/AppLayout.tsx` | logo 阴影 CSS 变量 | 004 |
| `frontend/src/components/chat/MessageBubble.tsx` | 相关性颜色 + a11y icon | 006, 008 |
| `frontend/src/components/ErrorBoundary.tsx` | retry 方式改进 | 010 |
| `frontend/src/components/NetworkStatusBanner.tsx` | 移除冗余 animation | 012 |
| `frontend/src/styles/globals.css` | CSS 变量定义 (--color-fill, --color-*-rgb) | 003, 007 |

---

## 性能验证

| 指标 | 方法 | 结果 |
|------|------|------|
| 前端构建时间 | `npx vite build` | **24.39s** (V4.1: 26.65s, ↓2.26s) |
| TypeScript 编译 | `npx tsc --noEmit` | **仅预存错误，无新增** |
| 新增 bundle size | build stats | vendor chunk 不变 |
| CSS 变量新增 | globals.css | +6 变量定义行 (3 rgb per mode) |

---

## V4.0 回归遗留确认 → 全部修复

V4.0 BUG-005 boxShadow `rgba(0,82,255,0.4)` 残留已在最终迭代中修复：
- StreamingCursor glow → `var(--shadow-accent)` 替换 rgba(0,82,255,0.4)

---

## 补充修复 — 全量硬编码颜色扫描遗漏项

在 V4.2 bug list 12项修复完成后，执行了全量前端硬编码颜色扫描
(`rgba(0,82,255,...)` + `#0052FF` + `#4D7CFF`)，发现以下额外遗漏项并全部修复：

| 项 | 原值 | 替换为 | 文件 |
|---|---|---|---|
| StreamingCursor glow | `rgba(0,82,255,0.4)` | `var(--shadow-accent)` | MessageBubble.tsx |
| sidebar active 背景 | `rgba(0,82,255,0.08)` | `var(--color-fill-secondary)` | AppLayout.tsx |
| onboarding icon bg | `rgba(0,82,255,0.08)` | `var(--color-fill-secondary)` | AppLayout.tsx |
| language menu dot | `color: '#0052FF'` | `var(--accent)` | AppLayout.tsx |
| header lang button | `color: '#0052FF'` | `var(--accent)` | AppLayout.tsx |
| sidebar logo shadow | `rgba(0,82,255,0.25)` | `var(--shadow-accent)` | AppLayout.tsx (已修复004) |
| onboarding shadow | `rgba(0,82,255,0.25)` | `var(--shadow-accent-lg)` | AppLayout.tsx (已修复004) |
| Welcome tip bg | `rgba(0,82,255,0.06...)` gradient | `var(--color-fill)` | WelcomeScreen.tsx |
| Welcome tip border | `rgba(0,82,255,0.15)` | `var(--color-border-secondary)` | WelcomeScreen.tsx |
| WelcomeScreen logo shadow | `rgba(0,82,255,0.25)` | `var(--shadow-accent-lg)` | WelcomeScreen.tsx |
| LoginPage boxShadow | `rgba(0,82,255,0.35)` | `var(--shadow-accent-lg)` | LoginPage.tsx |
| Brand gradients | `linear-gradient(#0052FF,#4D7CFF)` | `var(--gradient-accent)` | AppLayout/WelcomeScreen/LoginPage/ProfilePage |
| LoginPage accent stripe | `#0052FF` | `var(--accent)` | LoginPage.tsx |
| globals.css ::selection | `rgba(0,82,255,0.12)` | 添加 dark override `rgba(77,124,255,0.15)` | globals.css |
| globals.css input focus | `rgba(0,82,255,0.1)` | rgba(var(--color-primary-rgb),0.1) + dark override | globals.css |
| globals.css .login-submit:hover | `rgba(0,82,255,0.35)` | `var(--shadow-accent)` | globals.css |
| globals.css .section-label | `rgba(0,82,255,0.3/0.05)` | rgba(var(--color-primary-rgb),...) + var(--color-fill) | globals.css |
| --color-primary-rgb 变量 | 未定义 | 添加 light: `0,82,255` dark: `77,124,255` | globals.css |

**CSS 新增变量总计**: 8项 (--color-fill, --color-fill-secondary, --color-error-rgb, --color-success-rgb, --color-warning-rgb, --color-primary-rgb × light+dark)

**前端 TSX 硬编码 #0052FF 剩余**: 仅 MessageBubble borderLeft fallback `var(--user-msg-accent, #0052FF)` — 正确（fallback 值）

**前端 TSX 硬编码 rgba(0,82,255,...) 剩余**: 仅 useTheme.ts Ant Design ConfigProvider token — 正确（内部 theme token，light/dark 各有独立配置）

[来源: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-001~012 + 全量扫描补充]
