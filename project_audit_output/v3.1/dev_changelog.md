# EY Onboarding AI — 代码变更日志

> 变更日期：2026-06-25 | 版本：Version_3.1 → Version_3.2 | 修复人：Full-stack Engineer

---

## 修改文件清单

| 文件路径 | 修改类型 | 关联任务 |
|----------|----------|----------|
| `frontend/src/store/chatStore.ts` | 重构 | P0-1 + P0-2 |
| `frontend/src/pages/ChatPage.tsx` | 优化 | P0-1 + P0-2 |
| `frontend/src/i18n/locales/en/chat.json` | 新增 | P0-1 + P0-2 |
| `frontend/src/i18n/locales/zh/chat.json` | 新增 | P0-1 + P0-2 |
| `frontend/src/layout/AppLayout.tsx` | 优化 | P1-3 + P1-4 + P2-1 |
| `frontend/src/i18n/locales/en/common.json` | 新增 | P1-1 + P1-2 + P2-1 |
| `frontend/src/i18n/locales/zh/common.json` | 新增 | P1-1 + P1-2 + P2-1 |
| `frontend/src/auth/LoginPage.tsx` | 新增 | P1-1 |
| `frontend/src/pages/ProfilePage.tsx` | 重构 | P1-2 |

---

## 详细变更说明

### [重构] BUG-002 + UX-001 — 聊天 SSE 流式响应即时反馈 + 渐进式思考指示器

**涉及文件**：`chatStore.ts`, `ChatPage.tsx`, `chat.json` (en+zh)

**修复方案**：
1. **chatStore.ts** — 核心重构
   - 移除旧的 10s `THINKING_THRESHOLD` + `thinkingCheckInterval` + `thinkingShown` 机制（旧方案在10s后将 `'\n\n⏳ _仍在思考中..._'` 注入 `streamContent`）
   - 新增 `thinkingPhase` 状态（`'connecting' | 'searching' | 'generating'`），初始值 `'connecting'`
   - 新增 `connectionStatus` 状态（`'idle' | 'connecting' | 'streaming' | 'error' | 'fallback'`），初始值 `'idle'`
   - 新增 `setThinkingPhase` 和 `setConnectionStatus` actions
   - 修改 `setStreaming` action：当 `isStreaming=false` 时重置 `thinkingPhase='connecting'` 和 `connectionStatus='idle'`
   - `sendMessage` 内部重构：
     - 发送前立即设置 `thinkingPhase='connecting'` + `connectionStatus='connecting'`（<500ms 即有反馈）
     - fetch headers 接收后设置 `connectionStatus='streaming'`
     - 替换 interval 检查为 setTimeout 定时器：
       - 3s → `thinkingPhase='searching'`
       - 8s → `thinkingPhase='generating'`
       - 5s → `connectionStatus='fallback'`（慢连接检测）
     - 30s abort 阈值保留（`ABORT_THRESHOLD=30000`）
     - 所有退出路径（token/done/error/catch/abort）统一调用 `clearAllTimers()` 清理
     - 移除所有 `thinkingShown` 变量和 `updateStreamContent(assistantContent + '\n\n⏳')` 注入逻辑
     - catch 块新增 `setConnectionStatus('error')` 调用

2. **ChatPage.tsx** — 渐进式思考指示器渲染
   - 新增 `thinkingPhase` 和 `connectionStatus` store subscriptions
   - 替换思考指示器渲染块：从固定 `t('thinking')` 改为根据 `thinkingPhase` 渐进式显示
     - `connecting` → `t('thinking_connecting')` ("正在连接...")
     - `searching` → `t('thinking_searching')` ("正在检索知识库...")
     - `generating` → `t('thinking_generating')` ("正在生成回复...")
   - 新增 `connectionStatus === 'fallback'` 时的慢连接提示（淡黄色背景 + `(t('connection_slow'))` 附加文字）
   - 屏幕阅读器 `aria-live` 区域同步更新为渐进式文案

3. **i18n chat.json** — 新增 4 个翻译键
   - en: `thinking_connecting`, `thinking_searching`, `thinking_generating`, `connection_slow`
   - zh: 对应中文翻译

---

### [优化] UX-003 — 移动端汉堡菜单优化

**涉及文件**：`AppLayout.tsx`

**优化方案**：
- 图标从 `MenuUnfoldOutlined` 改为 `MenuOutlined`（三条横线，更符合主流 App 习惯）
- 触控区域增至 44×44px（`minWidth: 44, minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'center'`）
- 颜色从 `var(--color-text-secondary)` 改为 `var(--color-text)`（更醒目）
- 新增首次移动端自动展开 Drawer 2s 的 useEffect（localStorage `ey-mobile-drawer-seen` 标记防止重复）

---

### [优化] UX-005 — 侧边栏搜索改进

**涉及文件**：`AppLayout.tsx`

**优化方案**：
- 搜索 Input 从 `size="small"` 改为 `size="middle"`（更大、更可见、更易点击）
- SearchOutlined 图标 fontSize 从 12px 改为 14px（更醒目）

---

### [新增] UX-006 — 新手引导跳过选项

**涉及文件**：`AppLayout.tsx`, `common.json` (en+zh)

**优化方案**：
- Onboarding Modal 底部 "开始使用" Button 下方新增 `Button type="link"` "暂时跳过"
- 调用同一 `handleOnboardingClose` handler（设置 localStorage `ey-onboarding-seen` 标记）
- i18n：`skip_for_now`（en: "Skip for now", zh: "暂时跳过"）

---

### [新增] UX-004 — Demo 账号一键填入

**涉及文件**：`LoginPage.tsx`, `common.json` (en+zh)

**优化方案**：
- 新增 `Form.useForm()` + `form={form}` 绑定
- Form initialValues 从 `{ email: '' }` 改为 `{ email: '', password: '' }`
- 在 Info Alert 下方添加 `UserSwitchOutlined` icon 的 "使用演示账户" link Button
- 点击调用 `form.setFieldsValue({ email: 'admin@ey.com', password: 'admin123' })`
- i18n：`demo_fill_btn`（en: "Use Demo Account", zh: "使用演示账户"）

---

### [重构] UX-002 — Profile 页面内容扩展

**涉及文件**：`ProfilePage.tsx`, `common.json` (en+zh)

**重构方案**：
- 从单卡片（email + language）重构为两卡片布局：
  1. **Account Info Card**：Avatar（64px，蓝渐变背景 + UserOutlined）+ Username header + Divider + Row/Col 2×2 grid 展示 service_line / office_location / role_level / email（空值显示 `'—'`）
  2. **Preferences Card**：Language preference Select + 保存按钮（保留原有 PATCH 功能）
- 移除未使用的 `Input`, `LockOutlined`, `Text` imports
- 移除 disabled email Form.Item（改为 Account Info Card 中的纯展示字段）
- i18n：新增 `account_info`, `preferences`, `service_line`, `office_location`, `role_level`, `username`

---

## 构建验证

- TypeScript 编译：✅ 通过（无错误）
- Vite 构建：✅ 通过（21.80s）
- 仅有 antd chunk 大小警告（项目原有，非本次修改引入）
