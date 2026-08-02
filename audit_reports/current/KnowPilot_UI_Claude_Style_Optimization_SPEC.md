# KnowPilot UI Claude 风格优化 SPEC

版本：v1.0 ｜ 日期：2026-07-28 ｜ 范围：前端（frontend/src），不涉及后端

## 1. 背景与目标

本 SPEC 覆盖三项优化诉求：

1. **管理页面（含管理员账号 UI）统一对齐 Anthropic Claude 设计风格**：布局、样式、组件语言与 Claude 的"温暖纸感"视觉体系保持一致。
2. **修复深色模式对比度问题**：消除暗色下文字/背景对比不足、组件颜色失效等视觉不友好现象。
3. **Local Graph 科技感配色升级**：保留现有 SVG 力导向样式结构，配色更换为"深空蓝紫 + 霓虹青"方案。

## 2. 设计原则（Claude 视觉语言）

| 维度 | 规范 |
|------|------|
| 主色 | 陶土橙 accent：亮色 `#B85B35` / 暗色 `#E27B55` |
| 底色 | 纸感米白：亮色 background `#F7F6F0`、surface `#FDFDFB`；暗色 `#161513` / `#1C1B19` |
| 标题字体 | Fraunces 衬线（`--font-family-display`），正文 Inter |
| 圆角体系 | 控件 8px（`--radius-control`）、面板 12px（`--radius-surface`）、大卡片 16px（`--radius-lg`） |
| 间距 | 8px 基准网格（`--spacing-*`） |
| 状态徽章 | `rgba(var(--*-rgb), 0.10~0.12)` 底 + 语义色文字 + 0.2~0.3 透明度描边（以 AdminDashboardPage 映射为标准模板） |
| 页头 | 衬线标题（`.page-title`，含 40px accent 下划线）+ 副标题（`.page-sub`） |

**唯一颜色真源**：`src/design/tokens.ts`。任何组件禁止硬编码 hex/rgba 颜色，必须引用 CSS 变量；禁止携带亮色语义的回退值（如 `var(--color-error, #c0392b)`）。

## 3. 暗色对比度问题清单与修复方案

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| D1 | 图谱连线高亮、KB 状态标签、Timeline 热力格等在暗色下渲染为透明/继承色 | `--color-accent` / `--color-accent-rgb` 从未在 token 层定义，浏览器忽略引用了它们的声明 | `getCssVariables` 补齐两个变量（别名到 `accent` / `accentRgb`） |
| D2 | antd 组件（Badge/Tag/Alert/Tabs/Modal/Select 等）暗色适配靠 CSS `!important` 补丁，覆盖不全 | 应用未挂载 ConfigProvider，`getAntTheme`（含 darkAlgorithm）闲置 | 新建 `design/ThemeBridge.tsx` 挂载 ConfigProvider；删除 globals.css 中的暗色 antd 补丁块 |
| D3 | 暗色边框 `#756B60` 过亮，视觉刺眼、层级混乱 | 调色板取值不当 | border → `#3D3A35`，borderSecondary → `#302D29` |
| D4 | 模板中心禁用文案暗色下不可见 | 回退色 `rgba(0,0,0,0.25)` 为亮色语义 | 改为 `var(--color-text-placeholder)` |
| D5 | 遮罩层（onboarding 弹窗、移动端抽屉）固定黑色 rgba | 硬编码 | 改为 `var(--color-overlay)` |
| D6 | 通知铃、ErrorBoundary、Profile 必填星号带亮色 hex 回退值 | 硬编码回退 | 删除回退值，仅保留变量 |
| D7 | Profile 头像文字固定白色 | 硬编码 `#FFFFFF` | 改为 `var(--color-text-on-accent)` |
| D8 | 图谱中等新鲜度节点固定金黄 `#d4a017` | 硬编码 | 改为 `var(--graph-node-mid)` |

**验收标准**：暗色模式下正文文字对 surface 对比度 ≥ 4.5:1（WCAG AA）；次级文字 ≥ 4.5:1；禁用/占位文字 ≥ 3:1；所有语义徽章文字可读。

## 4. 管理页面统一规范

- **外壳（AdminLayout）**：248px 侧边栏（sunken 纸感底）+ 56px 顶栏。导航项：active 态 accent-soft 底 + 左侧 3px accent 指示条；hover 态 `--color-fill` 底（`.admin-nav-link:hover`）。顶栏用户按钮为胶囊样式（999px 圆角 + borderSecondary 描边），头像 accent 底 + on-accent 文字。
- **页头**：全部 9 个 admin 页面统一"衬线标题 + 副标题"结构。`h1.page-title` 页面追加 `p.page-sub`（新增 i18n key：`admin_*_subtitle`）；Templates/Quality 页沿用 `PageHeader` 组件（等价结构）。
- **卡片**：`glass-panel` + `var(--radius-lg)` 圆角 + `borderSecondary` 描边 + `shadow-sm`。
- **表格**：表头 sunken 底、次级文字色（由 antd 主题 `Table.headerBg/headerColor` token 全局生效）。
- **管理员账号 UI**：ProfilePage 头像/必填标记、AdminLoginPage 均只引用主题变量。

## 5. Local Graph 配色规范（深空蓝紫 + 霓虹青）

图谱是刻意与 Claude 暖色主题解耦的"科技感专属区"，token 组定义于 `tokens.ts`（`--graph-*`）：

| Token | 暗色 | 亮色 | 用途 |
|-------|------|------|------|
| `--graph-bg-start/end` | `#0E1220` → `#161A2E` | `#F5F7FC` → `#E9EDF7` | SVG 背景 160° 线性渐变 |
| `--graph-node-fresh` | `#22D3EE` 霓虹青 | `#0E7490` | 新鲜度 ≥ 0.7 |
| `--graph-node-mid` | `#60A5FA` 电蓝 | `#2563EB` | 新鲜度 0.4~0.7 |
| `--graph-node-stale` | `#F59E0B` 琥珀 | `#B45309` | stale 状态 |
| `--graph-node-inactive` | `#5B6B84` 灰蓝 | `#64748B` | 低新鲜度 |
| `--graph-edge-link` | `#22D3EE` | `#0E7490` | 显式链接边 |
| `--graph-edge-term` | `#3B4863` | `#94A3B8` | 术语边 |
| `--graph-edge-similar` | `#818CF8` 靛紫 | `#6366F1` | 相似度边（虚线） |
| `--graph-halo(-rgb)` | `#22D3EE` | `#0E7490` | 选中光环 |
| `--graph-label` | `#9FB0C9` | `#475569` | 节点标签文字 |

**发光处理**：所有可见节点应用 `feGaussianBlur(2.4)` 外发光滤镜；选中节点用更强的 `feGaussianBlur(5)` 光晕 + 半径 +7 的 18% 透明度光环圈。布局算法、节点半径、交互（点击高亮邻域、边类型过滤、global/local 模式）保持不变。

## 6. 变更清单

| 文件 | 变更 |
|------|------|
| `src/design/tokens.ts` | 补 `--color-accent(-rgb)`；暗色 border 调暗；新增 `graphLight/graphDark` 调色板与 14 个 `--graph-*` 变量 |
| `src/design/ThemeBridge.tsx` | 新建：ConfigProvider + getAntTheme 挂载 |
| `src/main.tsx` | 渲染树包裹 ThemeBridge |
| `src/styles/globals.css` | 删除暗色 antd `!important` 补丁块；新增 `.admin-nav-link:hover` |
| `src/layout/AdminLayout.tsx` | 导航 hover 类、顶栏用户胶囊按钮、accent 头像 |
| `src/pages/admin/*`（7 个页面） | 页头补副标题 |
| `src/i18n/locales/{en,zh}/common.json` | 新增 7 个 `admin_*_subtitle` key |
| `src/components/knowledge/KnowledgeGraphPanel.tsx` | 图谱配色 token 化 + 渐变背景 + 发光滤镜 |
| `src/pages/admin/AdminTemplatesPage.tsx`、`src/layout/AppLayout.tsx`、`src/components/NotificationBell.tsx`、`src/components/ErrorBoundary.tsx`、`src/pages/ProfilePage.tsx` | 硬编码颜色/亮色回退值清理 |

## 7. 验收与回归

1. `npm run build` 与 typecheck 通过。
2. 浏览器端到端验证：管理员登录 → 9 个 admin 页面明/暗双模式截图核查；图谱 Tab global/local 模式新配色与发光效果；Modal/Select/Tag/Badge 暗色对比度；Profile 头像、移动端抽屉遮罩。
3. 员工端（Chat/History 等）冒烟：确认 ConfigProvider 挂载未引入回归（按钮、输入框、下拉、消息气泡样式正常）。
