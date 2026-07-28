# KnowPilot 统一管理入口（Console Hub）布局优化 SPEC

- 版本：V1.0（2026-07-28）
- 分支：`feature/console-entry-hub`（自 `V1.76.6` 迁出）
- 风格基线：Anthropic Claude（陶土橙 accent、纸感底色、Fraunces 衬线标题、8px 圆角体系、克制留白）
- 范围：纯前端；不改后端能力契约（CapabilitySnapshot 保持 contract_version=2 不变）
- 前置：`KnowPilot_Dark_i18n_Layout_Optimization_SPEC.md`（外壳顶栏/i18n/暗色已就绪）

---

## 1. 现状问题（入口审计结论）

| # | 问题 | 证据 |
|---|------|------|
| E1 | **入口埋藏且分散**：管理入口只存在于顶栏用户菜单下拉（0–3 条）与 ⌘K 面板，主侧边栏完全没有管理入口 | `AppLayout.tsx` L152-L184（userMenu）、L420-L457（sidebar 无入口）；`managementEntries.ts` |
| E2 | **多控制台用户只见一个入口**：`buildManagementEntries` 只产出一条 "Management console"，目标为服务端 `default_console` 单值；同时具备 platform+governance 权限的用户想去非默认控制台只能手动输 URL | `managementEntries.ts` L21-L23；`authorization.ts` L122-L124；快照无 consoles 列表 |
| E3 | **控制台之间无法互切**：进入 /platform-admin 后侧边栏只有本控制台导航 + "Back to app"，去 /governance 或某工作空间管理无任何入口 | `ScopedConsoleLayout.tsx` L94-L97 |
| E4 | **workspace 管理入口依赖 activeSpaceId**：只有当前激活空间才出现 "Workspace management" 菜单项；管理多个空间的负责人无法总览与切换 | `managementEntries.ts` L24-L31；`SpaceSwitcher.tsx` 空间卡片无 manage 链接 |
| E5 | **双轨外壳残留**：legacy `AdminLayout`（内联样式、9 条静态导航、无逐项能力过滤）与 ScopedConsoleLayout 并存，风格不一致 | `App.tsx` L159-L192；`AdminLayout.tsx` L27-L37 |

## 2. 目标设计：Console Hub（管理中心）

一句话：**新增单一入口 `/console`（管理中心），用 Claude 设置页风格的卡片中枢承载全部管理去向；三个控制台外壳增加控制台切换器；用户菜单管理入口收敛为一条。**

### 2.1 信息架构

```
用户菜单 ─── 「管理中心」(1 条) ──→  /console (Hub)
                                        ├─ 平台管理卡  ──→ /platform-admin/*
                                        ├─ 治理控制台卡 ──→ /governance/*
                                        ├─ 工作空间管理卡（内嵌空间列表）──→ /workspace/{id}/manage/*
                                        └─ 知识库卡    ──→ /workspace/{id}/knowledge
ScopedConsoleLayout 品牌区 ─── 控制台切换器 ──→ Hub / 其它控制台（能力过滤）
```

### 2.2 `/console` Hub 页面（新组件 `pages/console/ConsoleHubPage.tsx`）

- **可见性**：`hasAny(platform.access, governance.access, workspace.manage, knowledge.read)`，否则 ForbiddenPage。
- **布局**（Claude settings-hub 风格，管理宽度 `--management-max` 居中）：
  - PageHeader：衬线标题「管理中心」+ 副标题「按你的权限展示可用的管理区域」。
  - 卡片栅格 `repeat(auto-fit, minmax(320px, 1fr))`，每卡为 `Surface` + 新 `kp-hub-card` 样式：左上 28px accent 圆角图标章、衬线卡题、一句描述、卡内 2–4 条快捷链接（chips 风格，逐条 capability 过滤）、右上角「进入 →」。
  - 卡片按能力条件渲染：
    | 卡 | 显示条件 | 主跳转 | 快捷链接（能力过滤） |
    |----|---------|--------|--------------------|
    | 平台管理 | `platform.access` | /platform-admin | 用户、工作空间、审计、模型 |
    | 治理控制台 | `governance.access` | /governance | 用户、业务线、模板、审计 |
    | 工作空间管理 | `workspace.manage`（任一可管空间） | 列表内选择 | 卡内直接列出可管理空间（见 2.3），每行 → /workspace/{id}/manage |
    | 知识库 | `knowledge.read` 且 activeSpaceId | /workspace/{activeSpaceId}/knowledge | 文档、审核队列、图谱 |
- **数据来源**：全部取自现有 `useAuthorization()` + `useSpaceStore`（`snapshot.scopes.space_ids` ∩ `spaces` 列表求名称与 my_role）；**不新增后端接口**。

### 2.3 工作空间管理卡（解决 E4）

- 卡内列出「我可管理的空间」：`spaces.filter(s => scopes.space_ids.includes(s.id) && (my_role 为 owner/admin 或 has('workspace.manage')))`，每行：空间名 + 角色 Tag + 「管理」链接。
- 超过 5 个折叠为「查看全部」展开；空列表时卡片隐藏。

### 2.4 控制台切换器（解决 E2/E3，改 `ScopedConsoleLayout.tsx`）

- 品牌区标题从静态文本升级为下拉（`kp-console-switcher`）：当前控制台名 + DownOutlined；下拉项 = 「管理中心」+ 按能力过滤的其它控制台（platform.access → 平台管理；governance.access → 治理控制台；workspace 项列 activeSpaceId 或最近管理过的空间）。
- 侧边栏底部 "返回应用" 上方追加「管理中心」链接（HomeOutlined），与 back_to_app 同样式。

### 2.5 入口收敛（改 `managementEntries.ts` / `AppLayout` / `CommandPalette`）

- `buildManagementEntries` 重构：有任一管理能力 → 仅一条 `{ id: 'hub', label: '管理中心', to: '/console' }`；知识库入口保留独立一条（使用频率高，直达价值大）。workspace 管理入口从菜单移除（收进 Hub 与切换器）。
- ⌘K 面板同步：管理命令 = 「管理中心」+ Hub 各卡主跳转（能力过滤），检索友好。

### 2.6 路由与守卫接线

- `App.tsx`：`/` 子路由新增 `console`（AppLayout 外壳内，普通页面；`SuspendedRoute`+组件内能力判断）。
- `authorization.ts` `safeConsolePath`：capability 白名单追加 `/console`。
- `NavigationRouting.tsx` `capabilityRouteAllowed`：`/console` → `hasAny(platform.access, governance.access, workspace.manage, knowledge.read)`。
- `default_console` 语义不变（登录后仍按服务端值直达）；`LegacyAdminRedirect` 不变。

### 2.7 Legacy 清理（E5，低风险步骤）

- capability 模式下 `AdminLayout` 已不可达，本期**不删除**（legacy 双轨保留），仅在 SPEC 记录废弃状态；`/console` 仅注册在 capability 模式（legacy 模式不出现 Hub，菜单行为保持现状）。

## 3. 视觉规范（Claude 风格要点）

- 卡片：`--color-bg-container` 纸面 + `--color-border-secondary` 1px 边 + `--radius-lg`；hover 抬升 `--shadow-sm` + 边框透明度加深，200ms `--motion-ease`。
- 图标章：28–32px 圆角 9px，`--accent-soft` 底 + `--accent-text` 图标（暗色自动适配已重调的 token）。
- 快捷链接 chips：`--color-fill` 底、`--radius-control` 圆角、hover 换 `--accent-soft`；全部走既有 token，不新增硬编码颜色。
- 空状态：无任何卡可见时显示 EmptyState（「暂无可用的管理区域」）——理论上被路由守卫拦截，双保险。

## 4. i18n

新增 key（en/zh 双写，命名沿用 console_ 前缀）：`console_hub_title`、`console_hub_subtitle`、`console_hub_enter`、`console_hub_card_platform_desc`、`console_hub_card_governance_desc`、`console_hub_card_workspace_desc`、`console_hub_card_knowledge_desc`、`console_hub_my_spaces`、`console_hub_view_all`、`console_hub_empty`、`console_switcher_aria`、`management_hub`。完成后跑 `frontend/scripts/audit_i18n_keys.mjs` 确认差集为 0。

## 5. 实施拆分（本分支内分组提交）

1. `feat(hub)`: ConsoleHubPage + 路由 + safeConsolePath/capabilityRouteAllowed + i18n key
2. `feat(hub)`: ScopedConsoleLayout 控制台切换器 + 侧边栏「管理中心」链接
3. `refactor(entries)`: buildManagementEntries 收敛 + AppLayout/CommandPalette 适配 + 单测更新（managementEntries 相关断言）
4. `docs`: 本 SPEC 标记实施状态

## 6. 测试计划

- 单测：`managementEntries` 新行为（单条 hub 入口 + knowledge 条目）；Hub 卡片能力过滤渲染（mock useAuthorization 四种能力组合）；`safeConsolePath('/console')`；`capabilityRouteAllowed('/console', …)`。
- `tsc -b` + `npm run build` bundle 预算。
- 浏览器 E2E（browser-use，中英双语 × 明暗双主题）：
  1. admin 登录 → 用户菜单只见「管理中心」→ 进 Hub → 四卡按能力渲染 → 各卡跳转正确；
  2. 控制台内切换器：platform ↔ hub ↔ workspace 管理互切；
  3. 普通成员（无管理能力）：菜单无管理入口，直输 /console 得 Forbidden；
  4. 截图存 `audit_reports/screenshots/`。

## 7. 风险与回滚

- 纯增量路由 + 菜单重构；`default_console`、路由门禁、能力契约零改动，后端无感。
- 回滚：还原 `managementEntries.ts` 即恢复旧菜单；`/console` 路由独立可摘除。
- 已知取舍：快照无 consoles 列表，Hub 的控制台可见性由前端能力推断（与现有路由门禁同一判据，不产生越权入口——最终访问仍被 CapabilityGate 拦截）。
