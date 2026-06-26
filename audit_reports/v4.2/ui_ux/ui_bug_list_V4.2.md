# V4.2 UI/UX 新缺陷列表

> 版本: V4.2
> 日期: 2026-06-26
> 审计领域: UI/UX
> 环境: Docker (UI 领域端口隔离: 3010/8010/5433/6380)
> 测试浏览器: Chrome (CDP agent-browser) + 代码审查
> 基线来源: V4.1/ui_ux/ui_bug_list_V4.1.md (BUG-001~017 已修复，不在本列表)
> V4.0回测已知残留: BUG-005 boxShadow rgba(0,82,255,0.4) — P2 轻微，不在本列表重复

---

## 分类统计

| 分类 | 数量 |
|------|------|
| 交互失效 | 3 |
| 视觉崩坏 | 5 |
| 体验卡顿 | 2 |
| 可访问性 | 2 |
| **合计** | **12** |

| 严重度 | 数量 |
|--------|------|
| P1 (严重) | 2 |
| P2 (一般) | 7 |
| P3 (轻微) | 3 |

---

## 【交互失效】

### UI-V4.2-001: CrawlerAdminPage useEffect 无空依赖数组，每次渲染触发 API (P1)

**文件**: `frontend/src/pages/admin/CrawlerAdminPage.tsx` lines 76-78

**描述**: `useEffect(() => { fetchDocs(); }, [fetchDocs])` 的依赖数组包含 `fetchDocs`（一个 `useCallback` 函数）。当 `fetchDocs` 的依赖 `t`（i18n 翻译函数）因语言切换/HMR 重新创建时，整个 effect 重新触发，导致全量 API 调用。在没有 `[]` 空依赖守卫的情况下，任何父组件 state 变化都可能引发数据请求风暴。

**复现步骤**:
1. 打开 CrawlerAdminPage（/admin/crawler）
2. 观察 console — `listCrawledDocuments` 被调用
3. 切换界面语言（中→英）→ 立即再次调用 API
4. HMR 热更新触发 → 再次调用 API

**预期 vs 实际**: 预期仅在 mount 时加载一次，后续靠 polling interval 刷新。实际每次 fetchDocs 重新创建都触发全量请求。

**截图证据**: 代码审查（无自然触发截图）

**影响范围**: CrawlerAdminPage 全页；可能引发 API 频率过高被限流拦截

**建议修复方向**: 改为 `useEffect(() => { fetchDocs(); }, [])`，或使用 `useRef` 跟踪 "已加载" 标志 + polling interval 管理刷新

---

### UI-V4.2-002: handleRetry 绕过 sendLock + offline 检查 (P1)

**文件**: `frontend/src/pages/ChatPage.tsx` lines 195-200

**描述**: `handleSend`（行 172-185）有完整守卫链：`isStreaming || isSendLocked || isSendingRef.current || !navigator.onLine`。但 `handleRetry` 直接调用 `sendMessage(lastUserMsg.content)`，绕过了所有锁和在线检查。在网络断开时点击 Retry，请求仍会发出并失败；在流式进行中点击 Retry（如果 error 状态下 isSendLocked 已释放但 isStreaming 仍为 true），可能触发并发双流。

**复现步骤**:
1. 断开网络连接
2. 发送消息 → 触发网络错误
3. 点击 Retry 按钮 → 观察请求仍然发出
4. 或：流式进行中触发 error → 点击 Retry → 可能并发

**预期 vs 实际**: 预期 Retry 应复用 handleSend 的完整守卫逻辑。实际绕过所有守卫直接调用 sendMessage。

**截图证据**: [bug_v42_002_retry_guard.png](screenshots/bug_v42_002_retry_guard.png) — 红框标注 Retry 按钮区域与守卫缺失

**影响范围**: ChatPage 重试路径；可能导致并发请求或离线无效请求

**建议修复方向**: 将 `handleRetry` 重构为 `sendWithGuard(lastUserMsg.content)`，复用 handleSend 的所有守卫条件

---

### UI-V4.2-011: AdminDashboardPage 系统健康状态全部硬编码 (P2)

**文件**: `frontend/src/pages/admin/AdminDashboardPage.tsx` lines 63-88, 210-225

**描述**: `loadSystemStatus` 函数调用 `/audit/` API 获得 `auditRes`，但**完全不使用响应数据**。所有状态字段硬编码为 `'running'`/`'connected'`，`total_documents: 0`。即使 API 失败（catch block），backend_status 和 db_status 仍显示 `'running'`/`'connected'`，仅 celery_status 变为 `'unknown'`。管理员看到的健康面板展示虚假数据，可能掩盖真实故障。

**复现步骤**:
1. 以 admin 身份登录 → 导航到 Admin Dashboard
2. 观察 "System Health" 面板 → backend=running, db=connected, celery=running/unknown
3. 停止 Celery worker → 面板仅 celery 变为 unknown，其余不变
4. 停止 backend → 面板仍显示 backend=running（因 API 失败→catch→hardcoded）

**预期 vs 实际**: 预期使用 auditRes.data 真实状态填充面板。实际全部硬编码字符串，API 数据被浪费。

**截图证据**: [bug_v42_011_admin_health.png](screenshots/bug_v42_011_admin_health.png) — 红框标注硬编码状态面板

**影响范围**: Admin Dashboard 全页；管理员无法获知真实系统健康状态

**建议修复方向**: 将 `auditRes.data` 字段映射到 SystemStatus interface，使用真实后端报告数据填充面板

---

## 【视觉崩坏】

### UI-V4.2-003: 网络错误 alert 硬编码亮色背景 (P2)

**文件**: `frontend/src/pages/ChatPage.tsx` lines 304-308

**描述**: 网络错误 alert 样式使用 `border: '2px solid #ff4d4f'` + `background: '#fff2f0'`。`#fff2f0` 是 Ant Design 亮色模式红色淡背景，在暗色模式（body `#1E293B`）下形成刺眼的亮白矩形，视觉完全不协调。与 BUG-005 不同（BUG-005 覆盖了 stream cursor/copy button/sidebar delete，本项是 error alert 专属）。

**复现步骤**:
1. 切换到暗色模式
2. 触发网络错误（断开连接后发消息）
3. 观察 error alert — `#fff2f0` 白色背景在暗色界面上突兀

**预期 vs 实际**: 预期 error alert 背景适配暗色模式。实际硬编码亮色背景。

**截图证据**: [bug_v42_003_network_alert_dark.png](screenshots/bug_v42_003_network_alert_dark.png) — 红框标注暗色模式下的亮色错误框

**影响范围**: ChatPage 错误提示区域；暗色模式用户

**建议修复方向**: 替换 `#ff4d4f` 为 `var(--color-error)`，`#fff2f0` 为 `var(--color-error-bg)` 或 `rgba(var(--color-error-rgb), 0.08)`

---

### UI-V4.2-004: AppLayout logo 容器阴影硬编码 rgba (P2)

**文件**: `frontend/src/layout/AppLayout.tsx` line 383

**描述**: `boxShadow: '0 2px 8px rgba(0, 82, 255, 0.25)'` 硬编码在 EY logo 容器 div 上。暗色模式 accent 变为 `#4D7CFF`（CSS var `--accent`），但阴影仍使用 `rgba(0, 82, 255, 0.25)` 原始蓝色。视觉上阴影色调与暗色模式 accent 不一致。

**复现步骤**:
1. 切换暗色模式
2. 观察侧边栏 logo 区域 → 蓝色阴影色调偏暗偏饱和

**预期 vs 实际**: 预期阴影使用 CSS 变量跟随暗色 accent。实际硬编码 rgba。

**截图证据**: [bug_v42_004_logo_shadow_dark.png](screenshots/bug_v42_004_logo_shadow_dark.png) — 红框标注 logo 阴影区域

**影响范围**: AppLayout header/sidebar logo 区域；暗色模式视觉一致性

**建议修复方向**: 定义 `--shadow-accent` CSS 变量，或使用 `color-mix(in srgb, var(--accent) 25%, transparent)` 替代

---

### UI-V4.2-005: AdminDashboardPage Active Users 计数器硬编码绿色 (P2)

**文件**: `frontend/src/pages/admin/AdminDashboardPage.tsx` line 224

**描述**: `color: '#52c41a'` 硬编码在 active users 计数器上。暗色模式下 `var(--color-success)` 解析为 `#4ADE80`（更亮、对比度更好），但硬编码 `#52c41a` 在 `#1E293B` 暗色背景上对比度不足。

**复现步骤**:
1. 切换暗色模式
2. 导航到 Admin Dashboard → 观察 "Active Users" 数字颜色偏暗

**预期 vs 实际**: 预期使用 `var(--color-success)` 适配暗色。实际硬编码 `#52c41a`。

**截图证据**: [bug_v42_005_admin_green.png](screenshots/bug_v42_005_admin_green.png) — 红框标注硬编码绿色数字

**影响范围**: AdminDashboardPage；暗色模式对比度

**建议修复方向**: 替换 `'#52c41a'` 为 `'var(--color-success)'`

---

### UI-V4.2-006: MessageBubble 相关性颜色硬编码 (P2)

**文件**: `frontend/src/components/chat/MessageBubble.tsx` lines 35-39

**描述**: `getRelevanceColor(score)` 函数返回硬编码颜色值：
- `score > 0.8` → `'#52c41a'`（Ant Design 亮色绿）
- `score > 0.5` → `'#faad14'`（Ant Design 亮色黄）
- 其他 → `'#8c8c8c'`（Ant Design 暗灰）

这些颜色在暗色模式下不适配：
- `#52c41a` 应为 `var(--color-success)` → `#4ADE80`（暗色更亮）
- `#faad14` 应为 `var(--color-warning)` → `#FBBF24`（暗色更亮）
- `#8c8c8c` 应为 `var(--color-text-tertiary)` → 暗色模式下可能需调亮

此缺陷**不在 BUG-005 覆盖范围内**（BUG-005 仅覆盖 stream cursor/copy button/sidebar delete）。

**复现步骤**:
1. 暗色模式
2. 观察消息引用相关性分数颜色 → 与暗色背景对比度不足

**预期 vs 实际**: 预期使用 CSS 变量适配暗色。实际 3 处硬编码 Ant Design 亮色值。

**截图证据**: [bug_v42_006_relevance_colors.png](screenshots/bug_v42_006_relevance_colors.png) — 红框标注相关性颜色区域

**影响范围**: MessageBubble 引用标记区域；暗色模式对比度

**建议修复方向**: 改为使用 CSS 变量 `var(--color-success)`、`var(--color-warning)`、`var(--color-text-tertiary)`，或通过 `getComputedStyle` 读取 CSS 变量值

---

### UI-V4.2-007: globals.css 侧边栏 hover 使用未定义 --color-fill (P2)

**文件**: `frontend/src/styles/globals.css` lines 924, 1012, 1018, 1085

**描述**: `.sidebar-session-item:hover`、`.new-chat-btn:hover`、`.sidebar-chat-item:not([data-active="true"]):hover` 使用 `background: var(--color-fill) !important`。但 `--color-fill` 和 `--color-fill-secondary` **不在 `:root` 或 `[data-theme="dark"]` 的 CSS 变量定义中**。这些变量是 Ant Design 内部 theme token，仅在 Ant Design ConfigProvider context 中可用，不在全局 CSS 类中生效。因此侧边栏 hover 背景完全不显示，用户无 hover 视觉反馈。

**复现步骤**:
1. 在侧边栏 hover 一条对话 → 无背景变化
2. 检查 DevTools → `var(--color-fill)` 解析为空（未定义）

**预期 vs 实际**: 预期 hover 时显示淡蓝色/淡灰色背景。实际 `var(--color-fill)` 未定义→hover 无视觉反馈。

**截图证据**: [bug_v42_007_sidebar_hover.png](screenshots/bug_v42_007_sidebar_hover.png) — 红框标注 hover 失效区域

**影响范围**: AppLayout 侧边栏所有对话项；用户交互反馈缺失

**建议修复方向**: 在 `:root` 中定义 `--color-fill: rgba(0, 82, 255, 0.04)` 和 `[data-theme="dark"]` 中定义 `--color-fill: rgba(77, 124, 255, 0.08)`；或改为 Ant Design token 引用方式

---

## 【体验卡顿】

### UI-V4.2-010: ErrorBoundary 重试 = window.location.reload() 丢失全部 SPA 状态 (P2)

**文件**: `frontend/src/components/ErrorBoundary.tsx` lines 43-49

**描述**: 当 ErrorBoundary 捕获渲染错误时，Retry 按钮执行 `window.location.reload()`。这会杀死全部 Zustand 状态、断开 SSE/WebSocket 连接、重置整个 SPA 到初始加载状态。用户可能丢失未保存的聊天内容、登录状态和滚动位置。对于单页应用，retry 应尝试局部子树重挂载而非核弹级全页刷新。

**复现步骤**:
1. 在任意子组件中触发渲染异常 → ErrorBoundary 显示
2. 点击 RELOAD → 全 SPA 重启，所有状态丢失

**预期 vs 实际**: 预期重试仅重挂载失败子树，保留全局状态。实际全页刷新丢失一切。

**截图证据**: [bug_v42_010_error_boundary.png](screenshots/bug_v42_010_error_boundary.png) — 红框标注 ErrorBoundary 重试按钮

**影响范围**: 全 SPA；任何渲染崩溃场景

**建议修复方向**: 改为 `setState({ hasError: false, error: null })` 重挂载子树，或提供 `retryFn` prop 让调用方自定义恢复逻辑

---

### UI-V4.2-012: NetworkStatusBanner animation 引用未定义 keyframe (P3)

**文件**: `frontend/src/components/NetworkStatusBanner.tsx` line 38

**描述**: `animation: 'slideDown 0.3s ease-out'` 引用 `@keyframes slideDown`，但此 keyframe **不在 globals.css 中定义**。antd Alert 内部有自己的入场动画，此 inline animation 属死代码。在严格 CSP 环境下（无 `unsafe-inline`），可能导致渲染阻断。

**复现步骤**:
1. 断开网络 → 观察 NetworkStatusBanner 出现
2. 检查 DevTools → animation 属性值为无效引用

**预期 vs 实际**: 预期使用有效的 slideDown 动画或依赖 antd 内置动画。实际引用未定义 keyframe。

**影响范围**: NetworkStatusBanner；视觉效果（antd Alert 自带动画覆盖，实际影响极小）

**建议修复方向**: 移除 inline animation，依赖 antd Alert 内置动画；或在 globals.css 中定义 `@keyframes slideDown`

---

## 【可访问性】

### UI-V4.2-008: Source count emoji 非屏幕阅读器友好 (P3)

**文件**: `frontend/src/components/chat/MessageBubble.tsx` line 401

**描述**: 引用计数标记使用 `'\u{1F4CE}'` (📎) emoji 作为图标前缀。屏幕阅读器可能朗读 "U+1F4CE" 或 "paperclip" 而非本地化文字。对于国际部署场景，emoji 无法提供本地化替代文本。

**复现步骤**:
1. 使用屏幕阅读器（VoiceOver/NVDA）浏览消息引用区域
2. 朗读结果可能为 emoji Unicode 名称而非语义文字

**预期 vs 实际**: 预期使用语义化图标 + `aria-label`。实际纯 emoji 无可访问性标注。

**影响范围**: MessageBubble 引用区域；屏幕阅读器用户

**建议修复方向**: 替换为 `<PaperClipOutlined aria-label={t('sources')} />` 或添加 `aria-label` 属性

---

### UI-V4.2-009: Chat 输入字数计数器无 ARIA live region (P3)

**文件**: `frontend/src/pages/ChatPage.tsx` lines 456-467

**描述**: `{inputValue.length}/4000` 字数计数器纯视觉展示，无 `aria-live="polite"` 或 `role="status"`。当字符数接近上限（3500+），颜色变琥珀/红色但屏幕阅读器用户无法感知。打字过程中字数变化不向辅助技术通报。

**复现步骤**:
1. 使用屏幕阅读器导航到聊天输入区
2. 输入文字 → 字数计数器变化但屏幕阅读器不朗读

**预期 vs 实际**: 预期 `aria-live="polite"` + `aria-label="Character count: X of 4000"`。实际纯视觉 div。

**影响范围**: ChatPage 输入区域；屏幕阅读器用户无法感知字数限制

**建议修复方向**: 在计数器 div 上添加 `role="status" aria-live="polite" aria-label={`Character count: ${inputValue.length} of 4000`}`

---

## 截图清单

| 文件名 | 内容 |
|--------|------|
| bug_v42_002_retry_guard.png | Retry按钮守卫缺失标注 |
| bug_v42_003_network_alert_dark.png | 暗色模式网络错误亮色背景 |
| bug_v42_004_logo_shadow_dark.png | Logo阴影硬编码rgba标注 |
| bug_v42_005_admin_green.png | Admin计数器硬编码绿色标注 |
| bug_v42_006_relevance_colors.png | 相关性颜色硬编码标注 |
| bug_v42_007_sidebar_hover.png | 侧边栏hover失效标注 |
| bug_v42_010_error_boundary.png | ErrorBoundary全页刷新标注 |
| bug_v42_011_admin_health.png | 系统健康硬编码状态标注 |

[来源: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-001~012]
