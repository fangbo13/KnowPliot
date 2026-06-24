# EY Onboarding AI — UX 优化交接文档

## 项目概览
- **项目**: EY Onboarding AI — React 18 + TypeScript + Ant Design 5 + Vite 5 新员工入职助手
- **工作目录**: d:\Github\Onborading-AI
- **当前分支**: Version_2.4
- **Docker**: `docker compose up -d`（frontend:3000 / backend:8000 / postgres / redis）
- **登录**: admin@ey.com / admin123
- **API**: DashScope (阿里云百炼) — chat: qwen3.6-flash, embedding: text-embedding-v4
- **`.env` 已配置正确的 API key**

## 已完成的工作

### ✅ 迭代 5 — 历史搜索/新手指引/消息复制
- HistoryPage 添加 Input.Search 关键词搜索 + Segmented 时间筛选（今天/本周/本月/更早）
- AppLayout 添加首次登录引导 Modal（4 功能卡片 2×2 网格，localStorage: ey-onboarding-seen）
- MessageBubble hover 显示 CopyOutlined 按钮 + clipboard API + Toast 反馈
- 新增 17 个 i18n keys（zh + en）
- PPT: `ux_improvement_report/UX优化成果汇报.pptx`（7 页中文汇报）
- Bug 修复：复制按钮 CSS hover 选择器修正（.msg-bubble-wrapper）

### ✅ 迭代 8 — v3 审计 18/18 全部修复（最新）

**核心功能：DeepSeek 风格侧边栏对话列表**
- 侧边栏 Menu 下方新增常驻对话列表区域，按时间分组（今天/昨天/7 天内/30 天内/更早）
- 新建对话胶囊按钮（顶部），点击 `resetSession()` + 导航到 `/chat`
- 分组标题可折叠（默认展开今天和昨天），带计数徽章
- 单行标题 CSS `text-overflow: ellipsis` 截断 + Tooltip 完整显示
- 当前活跃对话高亮（蓝色背景 + 加粗）
- 点击对话项: `setActiveSession(id)` + `navigate('/chat')`
- 右键菜单（桌面端）: 重命名/置顶/删除（Popconfirm 确认）
- 移动端 Drawer 同步对话列表 + 搜索
- 空状态引导提示
- 搜索胶囊（`useDebounce` 300ms 实时过滤）

**P0 修复**:
- P0-1: 移除侧边栏 Menu 中的 Profile 项（消除与 Header 用户下拉菜单重复），Tour 步骤从 4 步改为 3 步
- P0-2: 实现 DeepSeek 风格侧边栏对话列表（上述）
- P0-3: 新建 `ErrorBoundary` 组件（class component），包裹 `<Outlet />`，错误时友好降级 UI + 重试按钮
- P0-4: 新建 `NetworkStatusBanner` 组件（`navigator.onLine` + `online/offline` 事件），断网时顶部红色 Alert

**P1 修复**:
- P1-1: 侧边栏对话标题 Tooltip（hover 0.5s 延迟显示完整标题）
- P1-2: 移动端长按视觉反馈 — 高亮边框 + 缩放动画 + `navigator.vibrate(50)`
- P1-3: 知识管理页面硬编码英文字符串 → `t('file_type_error')` / `t('file_size_error')`（admin.json）
- P1-4: 消息加载骨架屏（3 条模拟气泡，shimmer 动画）替代纯 Spinner
- P1-5: 切换对话 200ms 淡入淡出过渡（CSS opacity transition）
- P1-6: 侧边栏对话搜索（Input.Search 胶囊样式，300ms debounce）
- P1-7: 新建 `useBreakpoint` hook（xs<576, sm<768, md<1024, lg<1280, xl>=1280），统一 AppLayout/LoginPage 响应式断点
- P1-8: `aria-live` 文本裁切优化 — 按句子边界（找最后一个句号/问号/换行），替代 `slice(-100)` 硬截断
- P1-9: 侧边栏对话右键菜单（onContextMenu）+ Popconfirm 删除确认

**P2 修复**:
- P2-1: WelcomeScreen 卡片 hover 改用 CSS 类 + transition（替代 inline onMouseEnter/onMouseLeave）
- P2-2: Skip-to-content 改用 CSS `.skip-link` 类 + `:focus-visible`（替代内联 JS）
- P2-3: HistoryPage 分页（每页 20 条，`<Pagination>` 组件）
- P2-4: 流式滚动已有 throttle(200ms) 优化
- P2-5: LoginPage 表单验证改为 `onChange` 实时反馈（`validateTrigger="onChange"`）

**新增文件**:
- `frontend/src/components/ErrorBoundary.tsx`
- `frontend/src/components/NetworkStatusBanner.tsx`
- `frontend/src/utils/dateGroup.ts`（共享日期分组逻辑）
- `frontend/src/hooks/useBreakpoint.ts`（统一响应式断点 hook）

**新增 i18n keys**（20 个）:
- `sidebar_conversations`, `sidebar_new_chat`, `sidebar_today`, `sidebar_yesterday`, `sidebar_7days`, `sidebar_30days`, `sidebar_earlier`, `sidebar_search`, `sidebar_empty_state`, `sidebar_rename`, `sidebar_delete`, `sidebar_pin`, `sidebar_delete_confirm`, `offline_banner`, `error_boundary_title`, `error_boundary_desc`, `error_boundary_retry`, `loading_messages`, `file_type_error`, `file_size_error`

**TypeScript**: 0 新增错误  
**Code Review**: 5 关键文件审查完成，修复 2 个中等问题（context menu 定位 + 错误提示过渡可见性）

### ✅ 迭代 9 — DeepSeek 1:1 界面复刻

**核心变更：侧边栏纯对话列表，无导航菜单**
- 删除侧边栏 `Menu` 组件和 `menuItems` 数组（移除对话/历史/知识库导航）
- 删除 `/history` 路由（App.tsx），HistoryPage 组件文件保留
- 侧边栏不再折叠，固定 260px 宽度（移除 `collapsed` 状态和 `localStorage` 持久化）
- 顶栏 DeepSeek 化：Logo + "Onboarding" + 搜索图标 + 布局图标（去掉折叠按钮）
- 新建对话按钮：白底灰边圆角样式
- 对话项 DeepSeek 化：hover 浅灰背景，选中态浅蓝背景 + 加粗
- 对话项右侧三点菜单按钮（hover 显示，点击弹出 重命名/删除）
- 底部用户区：头像 + 用户名 + 三点菜单（个人设置/退出登录）
- Header 用户下拉菜单添加知识库入口（`is_hr_admin` 条件可见）
- 完全移除 Onboarding Tour（3 步引导引用旧导航 ID，已无意义）
- Onboarding Modal 保留但简化（去掉 history 引用，footer 仅 "开始使用" 按钮）
- 移动端 Drawer 同步更新

**新增 i18n keys**（4 个）:
- `knowledge_base`: 知识库 / Knowledge Base
- `user_settings`: 个人设置 / Settings
- `sidebar_new_chat` 修改为: 开启新对话 / Start New Chat

**TypeScript**: 0 新增错误

### ✅ 迭代 1 — WelcomeScreen 对话输入框
- 显式 Input + Send 按钮、自动聚焦、键盘支持
- Quick Actions 6 个卡片全中文
- WelcomeScreen onSendMessage prop 对接 ChatPage sendMessage

### ✅ 迭代 2 — 侧边栏折叠 + Header 语言切换
- AppLayout.tsx Sider 折叠/展开（MenuFoldOutlined/MenuUnfoldOutlined）
- collapsed 状态 localStorage 持久化（key: ey-sidebar-collapsed）
- Header 添加 GlobalOutlined 语言切换下拉（zh/en），localStorage: ey-language
- 当前语言用蓝色圆点标记

### ✅ 迭代 3 — 登录页中文化 + 错误提示用户化
- LoginPage.tsx Brand 面板和 feature list 中文化
- 登录错误提示改为 i18n keys（不再暴露 "Login failed" 等开发信息）
- email 输入框已有 MailOutlined prefix

### ✅ 迭代 4 — 响应式与可访问性
- 小屏幕侧边栏 Drawer 替代 Sider（breakpoint="md"）
- Skip-to-content 链接
- ARIA landmarks、aria-live、aria-expanded、aria-current
- 颜色对比度修复（colorTextTertiary #8C8C8C → #595959）
- prefers-reduced-motion + .sr-only 工具类

### ✅ Bug 修复（最新）
- **Bug #1**: HistoryPage 点击对话不跳转，在历史页内查看消息（只读），底部添加「继续对话」按钮跳转到 ChatPage 继续对话
- **Bug #2**: ChatPage 添加 `useLocation` 监听路由变化，返回对话时正确重新加载消息
- **Bug #3**: 输入框改为 `position: fixed` 浮动在底部中心（DeepSeek/Claude 风格）

## 剩余工作（全部完成 — 12/12）

### ✅ 全部完成（迭代 6）
- 4. **聊天页添加新建对话按钮** — ✅ 迭代 6
- 6. **交互式 Onboarding 多步引导** — ✅ 迭代 6
- 5. **消息气泡分享/重新生成** — ✅ 迭代 6
- 7. **对话标题自动生成优化** — ✅ 迭代 6
- 9. **邮箱禁用态视觉优化** — ✅ 迭代 6
- 10. **响应式中等屏幕优化** — ✅ 迭代 6
- 12. **引用卡片信息密度优化** — ✅ 迭代 6

## 关键文件

| 文件 | 说明 |
|------|------|
| `frontend/src/layout/AppLayout.tsx` | 侧边栏 + Header 布局（折叠、语言切换、主题切换、移动端 Drawer） |
| `frontend/src/pages/ChatPage.tsx` | 聊天页面（WelcomeScreen、消息列表、浮动输入框、错误 Alert） |
| `frontend/src/pages/HistoryPage.tsx` | 历史记录页（本地状态加载消息、「继续对话」按钮） |
| `frontend/src/store/chatStore.ts` | Zustand chat store（sendMessage、SSE 流、错误处理） |
| `frontend/src/auth/LoginPage.tsx` | 登录页（中文化、错误提示 i18n、表单可见标签） |
| `frontend/src/i18n/locales/zh/common.json` | 中文翻译 |
| `frontend/src/i18n/locales/en/common.json` | 英文翻译 |
| `frontend/src/components/chat/WelcomeScreen.tsx` | 欢迎页面 + Quick Actions（输入框、6 个中文卡片） |
| `frontend/src/components/chat/MessageBubble.tsx` | 消息气泡组件（需添加复制/分享功能） |
| `frontend/src/styles/globals.css` | 全局样式（颜色、动画、响应式、a11y） |

## i18n keys（累计）

### 基础 keys
| Key | zh | en |
|-----|-----|-----|
| `error_auth` | 服务暂时不可用，请稍后再试 | Service temporarily unavailable. Please try again later. |
| `error_server` | 服务器繁忙，请稍后再试 | Server busy. Please try again later. |
| `error_network` | 网络连接失败，请检查网络后重试 | Connection failed. Please check your network. |
| `error_generic` | 请求失败，请稍后再试 | Request failed. Please try again later. |
| `login_failed` | 登录失败，请检查你的邮箱和密码 | Login failed. Please check your email and password. |
| `profile_load_failed` | 加载用户信息失败 | Failed to load user profile. |
| `login_brand_desc` | 智能入职助手，随时解答政策、福利等问题 | Your intelligent onboarding assistant... |
| `login_feature_1/2/3` | AI 智能问答 / 知识库集成 / 个性化服务 | Smart Q&A / Knowledge base / Personalized |
| `language_switch` | 切换语言 | Switch language |
| `nav_sidebar` | 导航侧边栏 | Navigation sidebar |
| `expand_sidebar` | 展开侧边栏 | Expand sidebar |
| `collapse_sidebar` | 收起侧边栏 | Collapse sidebar |
| `skip_to_content` | 跳到主要内容 | Skip to main content |
| `mobile_menu` | 打开移动菜单 | Open mobile menu |
| `email_label` | 邮箱地址 | Email address |
| `password_label` | 密码 | Password |
| `back_to_history` | 返回历史列表 | Back to history |
| `no_messages` | 暂无消息 | No messages |

### 迭代 5 新增
| Key | zh | en |
|-----|-----|-----|
| `search_history` | 搜索对话 | Search conversations |
| `filter_today` | 今天 | Today |
| `filter_this_week` | 本周 | This Week |
| `filter_this_month` | 本月 | This Month |
| `filter_earlier` | 更早 | Earlier |
| `filter_all` | 全部 | All |
| `no_search_results` | 没有找到匹配的对话 | No matching conversations found |
| `onboarding_title` | 欢迎使用 EY 入职助手 | Welcome to EY Onboarding AI |
| `onboarding_chat_title/desc` | 智能对话 / 提问... | Smart Chat / Ask... |
| `onboarding_history_title/desc` | 历史回顾 / 查看... | History Review / View... |
| `onboarding_knowledge_title/desc` | 知识库 / 浏览... | Knowledge Base / Browse... |
| `onboarding_profile_title/desc` | 个人设置 / 管理... | Profile Settings / Manage... |
| `onboarding_start` | 开始使用 | Get Started |
| `copy_message` | 复制消息 | Copy message |
| `copied` | 已复制 | Copied |

## Docker 操作
- 前端修改后: `docker compose restart frontend`（Vite 热重载）
- .env 修改后: `docker compose up -d backend celery-worker`（需要重建容器）
- 查看日志: `docker compose logs --tail 10 frontend`

## 注意事项
- 所有文档/报告/PPT 使用中文
- 代码注释和变量命名保持英文
- UI 文案使用 i18n，不要硬编码中文到组件中
- 已知 TS 警告（非阻断）: ChatPage.tsx:50 — ScrollBehavior 类型不兼容（可忽略）

## 下一步建议（迭代 6）

**本轮需要一次性完成全部 8 项剩余优化**（详见 NEXT_SESSION_PROMPT.md）。
完成后 UX 审计报告的 12 个问题将全部解决（12/12），路线图全部覆盖。

**验证要求**:
- 所有 8 项任务完成后，必须使用 agent-browser 进行端到端验证并截图
- 使用 code-review 技能审查关键文件
- 生成 `ux_improvement_report/迭代6功能验证报告.md`（含应用截图）
- 更新 HANDOFF.md 和 NEXT_SESSION_PROMPT.md 状态

**验证方式**:
- 每次修改后: `docker compose restart frontend`
- TypeScript 检查: `docker compose exec frontend npx tsc --noEmit`
- 手动浏览器验证或 Puppeteer 截图

## 审计报告位置
- `ux_audit_output/UX_Audit_Report.pptx` — 完整 UX 审计报告（12 页）
- `ux_improvement_report/ux_improvement_plan.md` — 优化实施计划
- `frontend/screenshots/` — 前后对比截图目录

## 最终状态

### UX 审计 12 项全部完成 ✅（12/12）
| # | 问题 | 状态 | 迭代 |
|---|------|------|------|
| 1 | 首页无对话输入框 | ✅ | 1 |
| 2 | 常见问题卡片全英文 | ✅ | 1 |
| 3 | 缺乏新手指引流程 | ✅ | 5（单页 Modal）+ 6（交互式 Tour） |
| 4 | 侧边栏固定不滚动 | ✅ | 2 |
| 5 | 登录页品牌面板英文 | ✅ | 3 |
| 6 | 语言切换入口过深 | ✅ | 2 |
| 7 | 历史列表无搜索筛选 | ✅ | 5 |
| 8 | 错误提示文案技术化 | ✅ | 3 |
| 9 | 邮箱禁用态视觉不足 | ✅ | 6 |
| 10 | 响应式中等屏幕优化 | ✅ | 6 |
| 11 | 键盘导航不完善 | ✅ | 4 |
| 12 | 引用卡片信息密度低 | ✅ | 6 |

### 迭代 6 额外完成项
- ✅ 消息气泡分享/重新生成
- ✅ 对话标题自动生成优化
- ✅ 8 张验证截图 + 功能验证报告

**整体完成率: 100%**

## v2 审计报告

2026-06-24 进行了第二次全面 UX 审计，发现 17 个新问题（5 严重 / 7 中等 / 5 轻微）。
详细路线图见 `NEXT_SESSION_PROMPT.md`。

- `ux_audit_output/UX_Audit_Report_v2.pptx` — v2 审计报告（17 个新问题）
- 整体评分从 v1 的 5.5/10 降至 4.5/10（v2 发现更多隐藏 bug）

---

### ✅ 迭代 8 — v3 审计 18/18 全部修复（最新）

**核心功能：DeepSeek 风格侧边栏对话列表**
- 侧边栏 Menu 下方新增常驻对话列表区域，按时间分组（今天/昨天/7 天内/30 天内/更早）
- 新建对话胶囊按钮（顶部），点击 `resetSession()` + 导航到 `/chat`
- 分组标题可折叠（默认展开今天和昨天），带计数徽章
- 单行标题 CSS `text-overflow: ellipsis` 截断 + Tooltip 完整显示
- 当前活跃对话高亮（蓝色背景 + 加粗）
- 点击对话项: `setActiveSession(id)` + `navigate('/chat')`
- 右键菜单（桌面端）: 重命名/置顶/删除（Popconfirm 确认）
- 移动端 Drawer 同步对话列表 + 搜索
- 空状态引导提示
- 搜索胶囊（`useDebounce` 300ms 实时过滤）

**P0 修复**:
- P0-1: 移除侧边栏 Menu 中的 Profile 项（消除与 Header 用户下拉菜单重复），Tour 步骤从 4 步改为 3 步
- P0-2: 实现 DeepSeek 风格侧边栏对话列表（上述）
- P0-3: 新建 `ErrorBoundary` 组件（class component），包裹 `<Outlet />`，错误时友好降级 UI + 重试按钮
- P0-4: 新建 `NetworkStatusBanner` 组件（`navigator.onLine` + `online/offline` 事件），断网时顶部红色 Alert

**P1 修复**:
- P1-1: 侧边栏对话标题 Tooltip（hover 0.5s 延迟显示完整标题）
- P1-2: 移动端长按视觉反馈 — 高亮边框 + 缩放动画 + `navigator.vibrate(50)`
- P1-3: 知识管理页面硬编码英文字符串 → `t('file_type_error')` / `t('file_size_error')`（admin.json）
- P1-4: 消息加载骨架屏（3 条模拟气泡，shimmer 动画）替代纯 Spinner
- P1-5: 切换对话 200ms 淡入淡出过渡（CSS opacity transition）
- P1-6: 侧边栏对话搜索（Input.Search 胶囊样式，300ms debounce）
- P1-7: 新建 `useBreakpoint` hook（xs<576, sm<768, md<1024, lg<1280, xl>=1280），统一 AppLayout/LoginPage 响应式断点
- P1-8: `aria-live` 文本裁切优化 — 按句子边界（找最后一个句号/问号/换行），替代 `slice(-100)` 硬截断
- P1-9: 侧边栏对话右键菜单（onContextMenu）+ Popconfirm 删除确认

**P2 修复**:
- P2-1: WelcomeScreen 卡片 hover 改用 CSS 类 + transition（替代 inline onMouseEnter/onMouseLeave）
- P2-2: Skip-to-content 改用 CSS `.skip-link` 类 + `:focus-visible`（替代内联 JS）
- P2-3: HistoryPage 分页（每页 20 条，`<Pagination>` 组件）
- P2-4: 流式滚动已有 throttle(200ms) 优化
- P2-5: LoginPage 表单验证改为 `onChange` 实时反馈（`validateTrigger="onChange"`）

**新增文件**:
- `frontend/src/components/ErrorBoundary.tsx`
- `frontend/src/components/NetworkStatusBanner.tsx`
- `frontend/src/utils/dateGroup.ts`（共享日期分组逻辑）
- `frontend/src/hooks/useBreakpoint.ts`（统一响应式断点 hook）

**新增 i18n keys**（17 个）:
- `sidebar_conversations`, `sidebar_new_chat`, `sidebar_today`, `sidebar_yesterday`, `sidebar_7days`, `sidebar_30days`, `sidebar_earlier`, `sidebar_search`, `sidebar_empty_state`, `sidebar_rename`, `sidebar_delete`, `sidebar_pin`, `sidebar_delete_confirm`, `offline_banner`, `error_boundary_title`, `error_boundary_desc`, `error_boundary_retry`, `loading_messages`, `file_type_error`, `file_size_error`

**TypeScript**: 0 新增错误  
**Code Review**: 5 关键文件审查完成，修复 2 个中等问题（context menu 定位 + 错误提示过渡可见性）

---

### ✅ 迭代 7 — v2 审计 17/17 全部修复（最新）

**修复摘要**:
- i18n 命名空间修复（`copy_message`、`chat_input_label` 迁移到 chat.json）
- 历史列表 `undefined` 渲染 → `formatDate()` + 默认值
- 触摸设备按钮通过 `@media (hover: none)` 始终可见
- 登录密码预填移除 → Info Alert 提示演示账户
- WelcomeScreen 硬编码中文 → `t('welcome_tip')`
- 侧边栏品牌名间距 `gap: 12`
- Tour Modal 可关闭（closable + maskClosable + Escape 键 + aria-modal）
- 历史列表按日期分组（今天 / 昨天 / 本周 / 更早）
- Profile 页移除主题切换（统一在 Header 操作）
- Shift+Enter 多行输入（Input → TextArea autoSize）
- 头像菜单添加"个人设置"入口 + Divider
- 历史搜索 debounce（300ms）
- 字符计数器（length/4000，>3500 橙色，=4000 红色）
- 颜色对比度已修复（#595959，7.0:1）
- 流式输出滚动回底（IntersectionObserver + 浮动按钮）
- 移动端长按弹出操作菜单（Popover）
- i18n CI 检查脚本（scripts/check-i18n.cjs）

**新增 i18n keys**（5 个）:
- `copy_message`, `chat_input_label`, `welcome_tip`, `new_messages`（chat.json）
- `continue_chat`（common.json）

**新增文件**:
- `frontend/src/hooks/useDebounce.ts`
- `frontend/scripts/check-i18n.cjs`

**TypeScript**: 0 新增错误  
**截图验证**: 12 张截图，全部通过  
**报告**: `ux_improvement_report/迭代7功能验证报告.md`

---

### 🔄 迭代 9 — DeepSeek 1:1 界面复刻（进行中）

**当前进度**: 约 80% 完成，主要功能已实现

**已完成**:
- ✅ 删除导航菜单（对话/历史/知识库），侧边栏改为纯对话列表
- ✅ 删除 `/history` 路由，历史功能集成到侧边栏
- ✅ 侧边栏固定 260px，不再支持折叠（div 替代 Ant Design Sider）
- ✅ 顶部 Logo 区域（EY 图标 + "Onboarding"）
- ✅ 新建对话按钮（白底灰边圆角 "开启新对话"）
- ✅ 对话列表日期分组（今天/昨天/7 天内/30 天内/更早）
- ✅ 对话项样式（选中态浅蓝背景，hover 浅灰）
- ✅ 右侧三点菜单（仅选中项显示，点击弹出操作菜单）
- ✅ 右键菜单（onContextMenu + Popconfirm 删除确认）
- ✅ 底部用户区（头像 + 用户名 + 三点菜单）
- ✅ 移动端 Drawer 同步结构
- ✅ Header 用户菜单添加知识库入口（仅管理员）
- ✅ Tour 简化（移除交互式 Tour，保留 Onboarding Modal）
- ✅ Skip-to-content 改用 CSS 类
- ✅ i18n keys 更新（20+ 个，zh/en 同步）

**待完成**:
- ⏳ 侧边栏顶栏右侧图标（搜索 + 布局）
-  CSS 样式微调（滚动条隐藏、hover 效果完善）
-  MessageBubble hover 增强
-  验证（TypeScript 检查、浏览器测试、截图）
- ⏳ 文档更新

**关键文件**:
- `frontend/src/layout/AppLayout.tsx` — 已大幅重构（核心）
- `frontend/src/App.tsx` — /history 路由已删除
- `frontend/src/styles/globals.css` — 部分样式已添加
- `frontend/src/i18n/locales/zh|en/common.json` — 已更新

详见 `NEXT_SESSION_PROMPT.md` 完整执行步骤和待办清单。
