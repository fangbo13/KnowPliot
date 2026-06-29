# KnowPilot 前端毁灭性重写 — 优化说明（交付）

> 一句话：在**零改动后端、零改动已加固的前端逻辑内核**前提下，把整套界面脱胎换骨为 **Anthropic / Claude 风**（米白纸感 + 陶土强调色 + 衬线标题 + 克制动效），并把丝滑度、流式渲染、人机交互、错误态、多端适配整体提升一个等级。已构建并部署到 `http://127.0.0.1:3003`。

---

## 1. 成果概览

| 维度 | 重写前 | 重写后 |
|---|---|---|
| 视觉语言 | AntD 默认 + 电光蓝渐变 | Claude 暖色纸感（陶土 `#C2693F` / 米白 `#F5F4EE`）+ Fraunces 衬线 |
| 样式架构 | `AppLayout.tsx` ~1200 行内联样式；`globals.css` ~1500 行堆满 `!important` | 三层 CSS：`tokens.css`（令牌）/`globals.css`（基座）/`chat.css`（对话组件），AntD 靠 ConfigProvider 令牌换肤 |
| 流式渲染 | 流式期纯文本（无格式），结束才解析一次 | **块级增量 Markdown**：完成块 memo 化只解析一次，进行中尾块实时成形，每帧 O(1) 摊销 |
| 人机交互 | 鼠标为主 | 新增 **⌘K 命令面板** + 快捷键（⌘B/⌘⇧O）+ IME 安全回车 + 统一会话菜单 |
| 错误/空/加载态 | AntD Alert | 品牌化错误卡 / 骨架屏 / 暖色离线条 / 两级 ErrorBoundary |
| 多端 | 基本响应式 | 移动抽屉、安全区 inset、≥44px 触控、单列建议卡、`100dvh` |
| 主题切换 | 整页“咔哒” | **View Transitions API** 交叉淡入（不支持优雅降级，尊重 reduced-motion） |

验证：`tsc --noEmit` 通过；`vitest` 36/36 通过（保留逻辑用例零回归）；`vite build` 成功；`:3003` 已加载新构建（`index-Bak6Leg6.js` / `index-B2EkIJ3W.css`）。桌面/移动 × 明/暗 × 全路由（登录/欢迎/对话/Profile/Admin/知识库）× 流式/命令面板/抽屉 均实测通过。

---

## 2. 设计系统（单一事实来源）

`src/styles/tokens.css` —— 沿用既有变量名、只换值，所以 **AntD 后台页与自定义对话区同步换肤**。

- **色板**：陶土 `--accent #C2693F`（暗色 `#D9805C`）；文字链接专用 `--accent-text`（达 WCAG AA）；纸感中性 `--color-bg-body #F5F4EE` / `--color-bg-container #FCFBF7` / 暖炭暗色 `#1C1A17 / #24221E`；语义 success/error/warning 全部暖调化并配 `-rgb`。
- **排版**：标题/字标 `Fraunces`（替换 Calistoga，更 editorial）；UI/正文 `Inter`；代码 `JetBrains Mono`。
- **动效令牌**：`--ease-out / --ease-spring / --ease-in-out` + `--dur-fast 140 / --dur 220 / --dur-slow 360`。
- **阴影**：暖棕基底的柔和分层 `--shadow-sm…xl` + `--shadow-floating-input / --shadow-context-menu`。
- **圆角**：新增 `--radius-2xl 24 / --radius-3xl 28`（Composer 胶囊）。

---

## 3. 文件改动地图

**新增**
- `styles/tokens.css`、`styles/chat.css`
- `components/CommandPalette.tsx`（⌘K：搜会话 / 新建 / 切空间 / 导航 / 切主题，键盘全可达）
- `hooks/useHotkeys.ts`（单监听、ref 读取最新绑定，避免重复绑定）
- `components/chat/markdown.tsx`（共享 XSS 安全 Markdown，memo 化）
- `components/chat/StreamingMarkdown.tsx`（块级增量渲染引擎）

**彻底重写（表现层）**：`styles/globals.css`、`index.html`(字体)、`main.tsx`(CSS 引入顺序)、`layout/AppLayout.tsx`、`pages/ChatPage.tsx`、`components/chat/{ChatComposer,MessageBubble,VirtualizedMessageList,WelcomeScreen,CopyCodeButton}.tsx`、`auth/LoginPage.tsx`、`components/NetworkStatusBanner.tsx`、`components/SpaceSwitcher.tsx`(触发器)、`hooks/useTheme.ts`(仅 `eyTheme` 令牌值 + View Transition 包装)。

**Token 适配（沿用 AntD）**：`pages/ProfilePage.tsx`、`pages/admin/{AdminDashboardPage,KnowledgeBasePage}.tsx`、`pages/SpaceManagementPage.tsx` —— 统一 `.page` 滚动壳层 + Fraunces 标题 + 响应式，主体靠令牌继承。

**i18n**：新增命令面板/欢迎语/页码/加载更早/用户管理等键（en+zh），未改既有键。

---

## 4. 丝滑度与流式渲染（防卡顿）

- **块级增量 Markdown**（`StreamingMarkdown.tsx`）：按空行/围栏切块；除最后一块外全部 `MarkdownView`（按内容字符串 memo）→ 只解析一次、永不重解析；进行中的尾块作为**当前块**实时渲染 Markdown（仅它每帧重渲染，复杂度被限定在单块，而非整段）。光标用 CSS `:last-child::after` 内联到尾部；进行中的代码围栏单独走实时 `<pre>`。流结束由 `MessageBubble` 渲染一次权威全量 Markdown，消除任何切块瑕疵。
- **保留的高性能管线**：`TokenBatchRenderer` 的 rAF 增量批渲染、`StreamLifecycleManager` 的 AbortController 生命周期、`react-virtuoso` 虚拟列表、`MessageBubble` 的 `React.memo` 比较器 —— 全部原样保留。
- **主题切换**：`useTheme.notifyAll` 用 View Transitions 交叉淡入，首屏同步应用不闪烁；`prefers-reduced-motion` 时关闭。
- **微动效**：消息入场 `messageIn`、命令面板 `cmdkIn`、Composer 聚焦环、发送/停止按钮 spring 缩放、侧栏项 hover/active、骨架 shimmer、思考点 `dotBounce` —— 统一走 `--ease-*` 令牌。

---

## 5. 人机交互升级

- **⌘K 命令面板**：分组（操作 / 最近对话 / 空间 / 导航），↑↓ 选择、↵ 执行、esc 关闭，鼠标 hover 同步高亮，底部 kbd 提示。
- **快捷键**：⌘K 面板、⌘B 收起/展开侧栏、⌘⇧O 新对话（输入框内也可触发）。
- **IME 安全回车**：通过 `compositionstart/end` + `isComposing` 守卫，**修复了中文拼音选词时回车误发送**的老问题。
- **统一会话菜单**：右键与三点合并为同一浮层，含就地“删除确认”两步态，自动夹紧视口边界。
- **回到底部 FAB**、**标题就地重命名**（↵ 保存 / esc 取消 / 失焦保存）、Composer 自增高 + 字数告警 + 发送/停止态切换。

---

## 6. 错误 / 空 / 加载态

- 对话错误改为**品牌化错误卡**（暖红描边 + 重试/忽略），替代 AntD Alert。
- 首次加载**骨架屏**；侧栏/路由**空态**文案；**暖色离线条**（`navigator.onLine` 监听）。
- **两级 ErrorBoundary**（顶层 Routes + 内容区）：子树重挂载而非整页刷新，保住 Zustand/登录/流式连接。

---

## 7. 多端适配与无障碍

- `100dvh` + `env(safe-area-inset-bottom)`；移动隐藏侧栏改 **Drawer 抽屉**（品牌头 + 全量会话）；汉堡/搜索移入顶栏。
- 触控目标 ≥44px；建议卡 ≤640px 单列；触屏下消息操作常显、代码复制常显。
- 可见焦点环、`aria-live` 流式播报、`role/aria-*`、Skip-to-content、kbd 提示；全局尊重 `prefers-reduced-motion`（含 View Transition 关闭）。

---

## 8. 未触碰的逻辑内核（按约定保留）

`store/chatStore.ts`、`stream/TokenBatchRenderer.ts`、`stream/StreamLifecycleManager.ts`、`api/*`、`auth/{AuthProvider,ProtectedRoute,RoleGuard}`、`store/spaceStore.ts`、`sync/crossTabSync.ts`、`utils/*`、`hooks/{useBreakpoint,useDebounce}`、整个 `backend/**`。`useTheme` 仅改 `eyTheme` 令牌值并加 View Transition 包装，单例状态逻辑不变。

---

## 9. 验证清单

- [x] `tsc --noEmit` 0 错（strict + noUnusedLocals/Parameters）
- [x] `vitest run` 36/36（dateGroup 33 + chatStore.setActiveSession 3）零回归
- [x] `vite build` 成功，产物部署到 `:3003`（asset 哈希已核对）
- [x] 实测：登录 / 欢迎 / 流式（列表+代码+引用）/ 命令面板 / Profile / Admin / 知识库 / 暗色 / 移动抽屉

---

## 10. 已知取舍与后续建议

- **包体积**：`antd` 单 chunk ~1.13MB（gzip 357KB）为既有问题。后续可按路由 `lazy()` 拆分、或对后台页 tree-shake AntD。
- **流式尾块极端场景**：超长“无空行单块”会让当前块每帧重解析；常规含段落的回复无感。如需进一步保险，可对尾块长度设阈值降级为纯文本。
- **后台页深度定制**：Profile/Admin/KB/Space 目前为令牌换肤 + 壳层统一；如需对话区同等质感，可后续逐页定制表格/表单。
- **设计回归**：建议补一组视觉快照（明/暗 × 桌面/移动）做回归基线。

---

*交付物：`frontend/REWRITE_PLAN.md`（计划）+ 本文（优化说明）。本地预览 `npm run dev`（:5199，代理 :8000）；线上 `:3003` 已更新。*
