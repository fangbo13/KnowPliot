# KnowPilot 暗色重调 + 语言系统修复 + 管理布局 Claude 化 优化 SPEC

- 版本：V1.0（2026-07-28）
- 范围：纯前端（`frontend/src`）+ i18n 资源；不改路由、权限与后端
- 关联：`KnowPilot_UI_Claude_Style_Optimization_SPEC.md`（上一轮 Claude 风格迁移）

---

## 1. 背景与目标

| # | 用户问题 | 方案方向（已确认） |
|---|---------|------------------|
| A | 深色模式配色存在对比度冲突，视觉不友好 | 保持 Claude 暖棕纸感基调，整体重建暗色阶梯与文字对比（WCAG AA） |
| B | 中英文切换后部分文案仍是英文 | 穷尽清理硬编码英文 + 补齐 en/zh 语言包缺失 key |
| C | 管理布局需全面向 Claude 靠齐（聊天页除外） | 升级现有外壳（不新建入口）：console 顶栏补齐、页面骨架统一 |

## 2. A — 暗色调色板重调（`design/tokens.ts` dark 对象）

### 2.1 换色对照表

| Token | 旧值 | 新值 | 说明 |
|-------|------|------|------|
| background | #161513 | **#141210** | 页面底，加深与 surface 拉开 |
| sunken | #100F0E | **#0D0B09** | 侧栏/最低层 |
| surface | #1C1B19 | **#1E1B18** | 卡片层，略提亮 |
| elevated | #252320 | **#2B2723** | 悬浮层，明显高于卡片 |
| text | #ECE6DE | **#F1ECE4** | 主文字提亮 |
| textSecondary | #B5ADA3 | **#C6BDB1** | 次级文字 ≥7:1 |
| textTertiary | #988F84 | **#A39A8E** | 三级文字 ≥4.5:1（含 elevated 上） |
| accent | #E27B55 | **#E9855F** | 暗底提亮一档 |
| accentHover/Active | #EC8A65/#D16C46 | **#F0936E/#D97450** | 同步 |
| accentText | #EC8A65 | **#F09B7A** | 正文链接色 ≥4.5:1 |
| success | #86B875 | **#95C285** | 语义色暗色专调 |
| warning | #E0B05C | **#E7BC70** | 同上 |
| error | #E07B6B | **#EB8D7D** | 同上 |
| border/borderSecondary | #3D3A35/#302D29 | **#403B35/#322E29** | 分隔可辨 |
| userMessage | #2C2925 | **#332E29** | 用户气泡与底拉开 |
| fill 三档 | 0.08/0.12/0.18 | **0.10/0.15/0.22** | hover/选中态增强 |
| --accent-soft / strong | 0.14/0.22 | **0.17/0.26** | 导航选中态增强 |
| onAccent | #16100B | **#1A120C** | 随 accent 微调 |

不变：graphDark（深空蓝紫+霓虹青）、hljs 暗色六色、亮色调色板。

### 2.2 对比度矩阵（WCAG，计算值约数）

| 前景 × 背景 | 对比度 | 标准 | 结果 |
|------------|-------|------|------|
| text #F1ECE4 × surface #1E1B18 | ≈14.1:1 | AA 4.5:1 | 通过（AAA） |
| textSecondary #C6BDB1 × surface | ≈8.8:1 | 7:1（目标） | 通过 |
| textTertiary #A39A8E × surface | ≈6.0:1 | AA 4.5:1 | 通过 |
| textTertiary × elevated #2B2723 | ≈5.0:1 | AA 4.5:1 | 通过 |
| accentText #F09B7A × surface | ≈7.7:1 | AA 4.5:1 | 通过 |
| accent #E9855F × surface（UI 组件） | ≈6.3:1 | 3:1 | 通过 |
| onAccent #1A120C × accent | ≈6.9:1 | AA 4.5:1 | 通过 |
| success #95C285 × surface | ≈8.3:1 | AA 4.5:1 | 通过 |
| warning #E7BC70 × surface | ≈9.0:1 | AA 4.5:1 | 通过 |
| error #EB8D7D × surface | ≈6.8:1 | AA 4.5:1 | 通过 |

## 3. B — 语言系统修复

### 3.1 根因

1. **整体未接 i18n**：`layout/consoleNavigation.ts`（19 项导航 label）、`layout/ScopedConsoleLayout.tsx`（标题/说明/返回）、`pages/console/` 下 ScopedUsers/ScopedQuality/ScopedMetrics/ScopedAudit/ConsoleOverview/ConsolePlaceholder 六个页面——中文语言下侧边栏与整页仍英文的直接原因。
2. **admin 页面局部硬编码**：列头 title、筛选 placeholder、Select option label、message 提示（Dashboard/Users/Codes/BusinessLines/Audit/Announcements/Spaces/Templates 共 8 页约 70 处）。
3. **语言包缺失 key**：`t('key') || 'English'` 模式中 i18next 缺 key 时返回 key 本身（真值），`||` 兜底永不生效，实际显示由 en fallback 决定——en/zh 各缺 169 个 key（含聊天组件 feedback_*/thinking_*/welcome_* 整组）。

### 3.2 修复方式

- `consoleNavigation.ts`：新增 `labelKey` 字段（保留 `label` 作英文 fallback 与测试兼容），渲染处 `t(labelKey, label)`。
- `ScopedConsoleLayout` / 6 个 console 页面 / 8 个 admin 页面全部文案接 `t()`。
- `auth/ProtectedRoute.tsx` "Loading workspace…" → `loading_workspace`。
- rate-limit "retry in Ns" 手写拼接统一为 `retry_after_seconds` 插值 key（AccessRequests/OwnershipTransfers/AdminDashboard 三处一致）。
- 语言包：`scripts/audit_i18n_keys.mjs`（自动收集 `t('key')` 引用与 en/zh 差集）+ `scripts/merge_i18n_keys.mjs`（一次性双语补齐 169 key）。**回归后差集为 0**。

### 3.3 验收

- 切中文后：platform-admin/governance/workspace 侧边栏、全部管理页表头/筛选/提示/空态均为中文。
- `node scripts/audit_i18n_keys.mjs` 输出 `MISSING_EN []` / `MISSING_ZH []`（可作为 CI 检查）。

## 4. C — 管理布局 Claude 化（升级现有外壳）

1. **ScopedConsoleLayout 顶栏**（新增 `.kp-console-topbar`，56px sticky）：NotificationBell、明暗切换、语言切换、用户胶囊——此前控制台完全没有主题/语言入口。品牌区加 accent "K" 标。
2. **导航 hover 态**：`.kp-console-nav__item:hover` 补 `--color-fill` 底。
3. **StatCard 原语**（`design/primitives.tsx` + `.kp-stat-card`）：大写小标签 + 28px 衬线数值，替换 AdminDashboard 4 卡、AdminQuality 4 卡、ScopedMetrics 4 卡的重复内联实现。
4. **老式 console 页迁移**：ScopedUsers/ScopedMetrics/ScopedAudit/ConsolePlaceholder 从 `page/page-head + glass-panel(inline radius)` 迁移至 PageHeader + Surface；ScopedAuditPage 裸 `<table>` 换 antd Table。
5. **细节统一**：11 个页面 `div.page` 的 inline `background:'transparent'` 残留清除；OwnershipTransfers 内层卡圆角统一 `var(--radius-lg)`。
6. 聊天页面（ChatPage/AppLayout 聊天区）不动。

## 5. 测试与验证

- `tsc -b` 通过；vitest 26/26 通过（ScopedConsoleLayout.test 补 useTheme/AuthProvider/NotificationBell mock；ScopedConsolePages.test 补 jsdom matchMedia stub）。
- `npm run build` + bundle 预算通过。
- 浏览器 E2E（browser-use）：中文暗色/亮色下走查 platform-admin 导航、Dashboard/Users/Audit 表头筛选、console Scoped 页、聊天页——截图存 `audit_reports/screenshots/`。

## 6. 风险与回滚

- 暗色换色集中于 tokens.ts 单点，回滚即恢复旧 dark 对象。
- i18n 仅增 key 与 t() 包装，`labelKey` 为增量字段，旧接口不破坏。
- 控制台顶栏为纯增量 DOM，不影响路由与权限（导航仍由 capability 过滤）。
