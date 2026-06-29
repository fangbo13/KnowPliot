# KnowPilot 前端毁灭性重写 — PLAN

> 目标：在**不触碰任何后端、也不触碰已加固的前端逻辑内核**的前提下，把整套界面脱胎换骨为 **Anthropic / Claude 风**（米白纸感 + 陶土强调色 + 衬线标题 + 克制动效），并把操作丝滑度提升一个等级。

## Context（为什么做这次重写）

当前前端历经 V3.4→V6.x 多轮加固，**逻辑层非常稳**（流式状态机、rAF 批渲染、AbortController 生命周期、滑动窗口+虚拟列表、跨标签同步）。问题全在**表现层**：`AppLayout.tsx` ~1200 行内联样式、`globals.css` ~1500 行堆满 `!important` 的 AntD 覆盖与暗色补丁，视觉是“AntD 默认 + 蓝色渐变”，缺乏大厂质感与丝滑交互。

本次只重写**表现层**，把视觉、布局、交互、动效、错误/空/加载态、流式渲染体验、微动效、多端适配全部做掉，并新增 ⌘K 命令面板与快捷键体系。

## 不可触碰（保留逻辑内核）

`store/chatStore.ts`、`stream/TokenBatchRenderer.ts`、`stream/StreamLifecycleManager.ts`、`api/*`、`auth/AuthProvider|ProtectedRoute|RoleGuard`、`store/spaceStore.ts`、`sync/crossTabSync.ts`、`utils/*`、`hooks/useTheme` 的**单例逻辑**（仅替换其导出的 AntD `eyTheme` token 值）。后端 `backend/**` 完全不动。

## 设计系统（Claude 暖色纸感）

**单一事实来源 = CSS 变量**。沿用现有变量名（`--color-text`/`--color-bg-container`/`--accent`/`--gradient-accent`/`--color-fill`…）但替换其值 → 全站（含 AntD 后台页）一次性换肤；再对对话核心做定制组件实现真正“脱胎换骨”。

| Token | Light（纸） | Dark（暖炭） |
|---|---|---|
| `--color-bg-body` | `#F5F4EE` | `#1C1A17` |
| `--color-bg-container` | `#FCFBF7` | `#24221E` |
| `--color-bg-elevated` | `#FFFFFF` | `#2B2925` |
| `--color-text` | `#29251F` | `#ECE7DC` |
| `--color-text-secondary` | `#6E675C` | `#B0A998` |
| `--color-text-tertiary` | `#9A9384` | `#847D6E` |
| `--color-border` | `#E4E0D5` | `#38352F` |
| `--accent`（填充/标记） | `#C2693F` 陶土 | `#D9805C` |
| `--accent-text`（文字/链接，达 AA） | `#9C4A26` | `#E8A483` |
| `--color-error` | `#B23B30` | `#E07B6B` |
| `--color-success` | `#4F7A4A` | `#7FB069` |

**排版**：标题/字标 → 衬线 `Fraunces`（替换 Calistoga，更 editorial）；UI/正文 → `Inter`；代码 → `JetBrains Mono`。`index.html` 字体 link 相应替换。

**动效**：`--ease-out: cubic-bezier(.22,1,.36,1)`、`--ease-spring: cubic-bezier(.34,1.4,.5,1)`；时长 `--dur-fast 140ms / --dur 220ms / --dur-slow 360ms`。统一柔和暖调阴影 `--shadow-sm/md/lg`、`--shadow-floating-input`。新增圆角 `--radius-2xl 20 / --radius-3xl 28`（Composer 胶囊）。

**无障碍/性能**：保留并强化 `prefers-reduced-motion`；主题切换走 **View Transitions API**（不支持则优雅降级），消除闪烁；焦点环、ARIA live、≥44px 触控目标。

## 文件改动地图

**新增**
- `src/styles/tokens.css` — 全部设计 token（light+dark）
- `src/styles/chat.css` — 对话核心组件样式（侧栏/消息流/Composer/Welcome/命令面板/状态）
- `src/components/CommandPalette.tsx` — ⌘K 命令面板（搜会话/新建/切换空间/导航/切主题）
- `src/hooks/useHotkeys.ts` — 全局快捷键（⌘K、⌘B 收起侧栏、⌘⇧O 新对话）
- `src/components/chat/StreamingMarkdown.tsx` — **块级增量 Markdown**：已完成块 memo 化只解析一次，进行中的尾块走纯文本+光标 → 流式期代码/表格也能实时成形且每帧 O(1) 摊销，不卡顿

**彻底重写（表现层）**
- `src/styles/globals.css`（reset/base/排版/滚动条/选区/keyframes/AntD 换肤）
- `index.html`（字体）、`src/main.tsx`（引入新 css、View Transition 主题切换包装）
- `src/layout/AppLayout.tsx`（干净侧栏+顶栏，类名替代海量内联样式，接入 ⌘K）
- `src/pages/ChatPage.tsx`（布局/错误态/回到底部 FAB/标题重命名）
- `src/components/chat/ChatComposer.tsx`（Claude 胶囊输入、停止/发送态、字数、快捷键提示）
- `src/components/chat/MessageBubble.tsx`（Claude 文档式助手消息 + 陶土微底用户气泡；接入 StreamingMarkdown）
- `src/components/chat/VirtualizedMessageList.tsx`（保留 virtuoso，仅重排版/思考态）
- `src/components/chat/WelcomeScreen.tsx`（Claude 问候 + 建议 chips）
- `src/auth/LoginPage.tsx`（暖色 editorial，**login() 数据流不变**）
- `src/components/ErrorBoundary.tsx`、`NetworkStatusBanner.tsx`、`SessionRenameModal.tsx`、`CopyCodeButton.tsx`、`SpaceSwitcher.tsx`（统一新视觉）
- `src/hooks/useTheme.ts` 中的 `eyTheme`（仅 token 值 → Claude 暖色，供 AntD 后台页换肤）

**Token 适配（沿用 AntD，靠变量继承换肤 + 页面壳层微调）**
- `pages/ProfilePage.tsx`、`pages/admin/AdminDashboardPage.tsx`、`pages/admin/KnowledgeBasePage.tsx`、`pages/SpaceManagementPage.tsx`：统一页头/间距/空态/`Fraunces` 标题，主体靠 token 继承。

**i18n**：向 `locales/{en,zh}/{common,chat}.json` **新增**键（命令面板、快捷键、空态、回到底部等），不改既有键。

## 执行顺序（阶段）

1. **基座**：tokens.css → globals.css → index.html 字体 → eyTheme → main.tsx（含 View Transition 主题切换）
2. **对话核心**：chat.css → StreamingMarkdown → MessageBubble → ChatComposer → VirtualizedMessageList → WelcomeScreen → ChatPage
3. **外壳与导航**：AppLayout → CommandPalette + useHotkeys → SpaceSwitcher / NetworkStatusBanner / ErrorBoundary
4. **认证页**：LoginPage
5. **后台/表单页换肤**：Profile / AdminDashboard / KnowledgeBase / SpaceManagement
6. **打磨**：暗色逐组件核对、移动端 Drawer/安全区/触控、reduced-motion 复核

## 验证

- 迭代：`cd frontend && npm run dev`（:3000，代理→ :8000 后端）做 HMR 实测；逐页核对 light/dark、移动断点、键盘流。
- 类型/构建：`npm run typecheck`、`npm run test`（保留既有用例：dateGroup、chatStore.setActiveSession）、`npx vite build`。
- 流式压测：长回复（含代码块/表格）观察块级增量渲染不卡顿、停止/超时/切会话不串流。
- 上线 :3003：`npx vite build` → `docker compose build frontend && docker compose up -d frontend`。
- 交付：完成后输出 `FRONTEND_REWRITE_OPTIMIZATION.md`（改了什么/为什么/前后对比/性能与无障碍/后续）。
