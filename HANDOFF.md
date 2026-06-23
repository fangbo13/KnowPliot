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

### ✅ 迭代 6 — UX 审计全部完成（12/12）（最新）
- ChatPage 添加「+ 新建对话」按钮，点击 resetSession 回到 WelcomeScreen
- ProfilePage 邮箱禁用态优化（LockOutlined + 灰色背景 + 提示文字）
- 平板中等屏幕（768-1024px）侧边栏默认折叠，Content padding 优化
- MessageBubble 新增分享/重新生成按钮（navigator.share + fallback 复制）
- 引用卡片可折叠紧凑列表，分数转"高/中/低相关"标签
- 交互式 Onboarding Tour（4 步引导，高亮侧边栏导航项 + CSS 脉冲动画）
- chatStore.ts 智能对话标题生成（去除无意义词、问句截断、CJK/English 自适应）
- 新增 22 个 i18n keys（zh + en）
- TypeScript 检查通过（0 新增错误）
- 报告: `ux_improvement_report/迭代6功能验证报告.md`

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
