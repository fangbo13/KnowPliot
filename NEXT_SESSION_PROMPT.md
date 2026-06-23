# EY Onboarding AI — 迭代 6 Prompt（完整路线图）

你好！你是 EY Onboarding AI 项目的 UX 优化工程师。请严格按以下上下文工作。

## ⚡ 核心指令：本迭代需要一次性完成 UX 审计报告中剩余的所有 8 项优化。

---

## 一句话背景
一个 React 18 + TypeScript + Ant Design 5 + Vite 5 的新员工入职 AI 助手，当前在 `Version_2.4` 分支（建议先创建 `Version_2.5` 分支再开始），Docker 运行于 frontend:3000 / backend:8000，登录 admin@ey.com / admin123。

## 第一步：读取交接文档
请先完整阅读以下文件：

1. **HANDOFF.md** — 项目概览、已完成工作、关键文件、i18n keys、Docker 操作
2. **ux_audit_output/UX_Audit_Report.pptx** — 12 页 UX 审计报告（用 Python 提取文本阅读）
3. **ux_improvement_report/ux_improvement_plan.md** — 优化计划与状态

---

## 当前状态总览

### ✅ 已完成（迭代 1-5）

| 迭代 | 内容 |
|------|------|
| 1 | 欢迎页输入框 + Quick Actions 6 卡片中文化 |
| 2 | 侧边栏折叠/展开 + Header 语言切换快捷下拉 |
| 3 | 登录页品牌面板中文化 + 错误提示文案用户化 |
| 4 | 移动端 Drawer + ARIA 可访问性 + 颜色对比度修复 + prefers-reduced-motion |
| Bug | HistoryPage 内联查看+继续对话、ChatPage 消息正确重载、输入框浮动居中 |
| **5** | **历史对话搜索/筛选**（Input.Search + Segmented 时间过滤） |
| **5** | **新手指引浮层**（Modal 4 功能卡片，localStorage 标记首次登录） |
| **5** | **消息气泡复制**（hover 显示 CopyOutlined + clipboard API + Toast） |
| **5** | **成果 PPT**（ux_improvement_report/UX优化成果汇报.pptx，7 页） |

### ✅ UX 审计 12 项已完成（9/12）

| # | 审计问题 | 状态 | 迭代 |
|---|---------|------|------|
| 1 | 首页无对话输入框 | ✅ | 1 |
| 2 | 常见问题卡片全英文 | ✅ | 1 |
| 3 | 缺乏新手指引流程 | ✅ | 5（单页 Modal） |
| 4 | 侧边栏固定不滚动 | ✅ | 2 |
| 5 | 登录页品牌面板英文 | ✅ | 3 |
| 6 | 语言切换入口过深 | ✅ | 2 |
| 7 | 历史列表无搜索筛选 | ✅ | 5 |
| 8 | 错误提示文案技术化 | ✅ | 3 |
| 11 | 键盘导航不完善 | ✅ | 4 |

### ❌ UX 审计 12 项剩余（3/12）— 本轮必须完成

| # | 审计问题 | 严重程度 |
|---|---------|---------|
| 9 | 邮箱禁用态视觉不足 | 🟢 低 |
| 10 | 响应式中等屏幕优化 | 🟢 低 |
| 12 | 引用卡片信息密度低 | 🟢 低 |

### ⚠️ 重要：迭代 5 的修改尚未 commit
以下文件已修改但未提交：
- `frontend/src/pages/HistoryPage.tsx` — 搜索/筛选
- `frontend/src/layout/AppLayout.tsx` — 新手指引 Modal
- `frontend/src/components/chat/MessageBubble.tsx` — 复制按钮
- `frontend/src/styles/globals.css` — 新增 `.msg-bubble-wrapper` hover 样式
- `frontend/src/i18n/locales/zh/common.json` — +17 keys
- `frontend/src/i18n/locales/en/common.json` — +17 keys

**建议先 commit**: `git add -A && git commit -m "feat: v2.5 - history search, onboarding tour, message copy"`

---

## 本轮待执行任务清单（8 项，必须全部完成）

### 🔴 高优先级

#### 1. 聊天页添加「新建对话」按钮
- **问题**: 对话进行中时没有明显的「+ 新建对话」入口
- **建议**: 在 ChatPage 添加按钮，点击清空当前会话并回到 WelcomeScreen
- **文件**: `frontend/src/pages/ChatPage.tsx`
- **改动量**: 小
- **i18n**: 新增 `new_chat` / `New Chat`

#### 2. 交互式 Onboarding 引导流程
- **问题**: 当前只有单页 Modal（迭代 5），缺少交互式多步引导
- **建议**: 使用 react-joyride 或自建 Tour 组件，逐步高亮介绍侧边栏的 4 个导航项（对话、历史、知识库、个人设置）
- **文件**: `frontend/src/layout/AppLayout.tsx`, `frontend/src/pages/ChatPage.tsx`
- **改动量**: 中
- **注意**: 可考虑安装 `react-joyride`，或自建轻量 Tour 组件

### 🟡 中优先级

#### 3. 消息气泡分享/重新生成
- **问题**: 消息气泡只有复制，缺少分享和重新生成
- **建议**: 在已有 hover 按钮旁添加 ShareOutlined 和 ReloadOutlined，复用 msg-bubble-wrapper hover 模式
- **分享**: 调用 `navigator.share`（如果支持），否则回退到复制链接
- **重新生成**: 对最后一条助手消息，重新发送最后一条用户消息
- **文件**: `frontend/src/components/chat/MessageBubble.tsx`
- **改动量**: 中
- **i18n**: 新增 `share_message` / `Share`, `regenerate` / `Regenerate`

#### 4. 对话标题自动生成优化
- **问题**: 对话标题是用户输入的前 50 字符，部分无意义（如 "Test"）
- **建议**: 前端截断时优先取有意义的词组（去除 "Test"、"test"、"hi" 等无意义词），或在后端用 LLM 生成简短摘要
- **最低实现**: chatStore.ts 中 createSession 时对 title 做智能截断（取前 5-8 个有意义的词，而非固定 50 字符）
- **文件**: `frontend/src/store/chatStore.ts`（前端截断优化），`backend/` 相关路由（可选后端优化）
- **改动量**: 小-中

### 🟢 低优先级

#### 5. 邮箱字段禁用态视觉优化
- **问题**: ProfilePage 邮箱字段 `<Input disabled />` 视觉区分不明显
- **建议**:
  - Input 添加 `style={{ background: 'var(--color-bg-elevated)', cursor: 'not-allowed' }}`
  - 添加 `LockOutlined` prefix 图标
  - 添加 helper text：「邮箱地址由系统分配，不可修改」
- **文件**: `frontend/src/pages/ProfilePage.tsx`
- **改动量**: 小
- **i18n**: 新增 `email_readonly_hint` / "Email is system-assigned and cannot be changed"

#### 6. 引用来源卡片信息密度优化
- **问题**: 引用卡片较大，占用空间多，"Score: 0.85" 对用户无意义
- **建议**:
  - 将多个引用折叠为一个可展开列表（默认显示 "📎 3 个来源 ▾"）
  - 点击展开后以紧凑列表展示
  - 相关性分数转为标签：>0.8 → "高相关"，>0.5 → "中相关"，≤0.5 → "低相关"
- **文件**: `frontend/src/components/chat/MessageBubble.tsx`
- **改动量**: 中
- **i18n**: 新增 `sources_count` / "{{count}} sources", `high_relevance` / "High", `medium_relevance` / "Medium", `low_relevance` / "Low"

#### 7. 平板/中等屏幕专属布局优化
- **问题**: 768px breakpoint 边界行为不佳，中等屏幕（Surface/iPad）空间利用差
- **建议**:
  - 在 `AppLayout.tsx` 中添加中间断点检测（768-1024px），此范围内默认折叠侧边栏
  - 在 `globals.css` 中添加 `@media (min-width: 768px) and (max-width: 1024px)` 规则
  - 确保折叠/展开行为在中等屏幕下合理
- **文件**: `frontend/src/layout/AppLayout.tsx`, `frontend/src/styles/globals.css`
- **改动量**: 小

---

## 建议执行顺序

**第一轮**（改动小、无依赖）:
1. 新建对话按钮（ChatPage）
2. 邮箱禁用态视觉优化（ProfilePage）
3. 平板布局优化（AppLayout.tsx + globals.css）

**第二轮**（消息气泡增强）:
4. 消息气泡分享/重新生成（MessageBubble.tsx）
5. 引用卡片信息密度优化（MessageBubble.tsx）

**第三轮**（核心体验）:
6. 交互式 Onboarding 引导流程
7. 对话标题自动生成优化

---

## 工作规则
1. 每次修改后: `docker compose restart frontend`
2. TypeScript 检查: `docker compose exec frontend npx tsc --noEmit`（忽略已知 ScrollBehavior 警告）
3. 浏览器验证或 Puppeteer 截图确认
4. **所有文档/PPT 用中文，代码注释用英文**
5. **UI 文案走 i18n，不硬编码中文到组件中**
6. 新增的 i18n keys 同步更新 zh + en 两个文件
7. 每完成一项任务，请在本文件中更新状态（将 ❌ 改为 ✅ 并标注迭代）

## Docker 操作
- 前端修改后: `docker compose restart frontend`（Vite 热重载）
- .env 修改后: `docker compose up -d backend celery-worker`（需要重建容器）
- 查看日志: `docker compose logs --tail 10 frontend`

## 关键文件
| 文件 | 说明 |
|------|------|
| `frontend/src/layout/AppLayout.tsx` | 侧边栏 + Header + 新手指引 Modal + 新手指引 Tour |
| `frontend/src/pages/ChatPage.tsx` | 聊天页面（需要 +新建对话 按钮） |
| `frontend/src/pages/HistoryPage.tsx` | 历史页（已有搜索/筛选） |
| `frontend/src/pages/ProfilePage.tsx` | 个人设置页（需要邮箱禁用态优化） |
| `frontend/src/components/chat/MessageBubble.tsx` | 消息气泡（需要分享/重新生成 + 引用优化） |
| `frontend/src/components/chat/WelcomeScreen.tsx` | 欢迎页 + Quick Actions |
| `frontend/src/store/chatStore.ts` | Zustand store（需要标题生成优化） |
| `frontend/src/auth/LoginPage.tsx` | 登录页 |
| `frontend/src/i18n/locales/zh|en/common.json` | 翻译文件 |
| `frontend/src/styles/globals.css` | 全局样式 |

## 审计报告位置
- `ux_audit_output/UX_Audit_Report.pptx` — 12 页完整审计报告
- `ux_improvement_report/ux_improvement_plan.md` — 优化实施计划
- `ux_improvement_report/UX优化成果汇报.pptx` — 迭代 5 成果汇报
- `frontend/screenshots/` — 前后对比截图目录

请从 **HANDOFF.md** 开始阅读，然后按上述顺序执行全部 8 项任务。

---

## 📸 验证阶段：所有 8 项任务完成后必须执行

### 第一步：agent-browser 功能验证截图

使用 **agent-browser** 技能，依次对每个功能进行端到端验证并截图保存到 `frontend/screenshots/iteration6/` 目录：

```
使用 agent-browser 执行以下验证：

1. 启动浏览器，打开 http://localhost:3000
2. 登录：admin@ey.com / admin123

截图 1 — 新建对话按钮：
3. 导航到 /chat，发送一条消息进入对话状态
4. 截图：展示「+ 新建对话」按钮的可见位置
5. 点击新建对话按钮，验证是否回到 WelcomeScreen
6. 截图：验证回到了欢迎页

截图 2 — 交互式 Onboarding 引导：
7. 清除 localStorage('ey-onboarding-seen')，刷新页面
8. 截图：展示 Tour 引导的第一步（高亮侧边栏某个导航项）
9. 逐步点击 Next 完成全部引导步骤，每步截图
10. 截图：引导完成后的状态

截图 3 — 消息气泡分享/重新生成：
11. 进入一个已有对话，hover 助手消息
12. 截图：展示 hover 后出现的操作按钮（复制 | 分享 | 重新生成）
13. 点击复制按钮，截图 Toast 反馈

截图 4 — 对话标题自动生成：
14. 导航到 /history
15. 截图：展示对话列表，验证标题不再有无意义的词（如 "Test"）

截图 5 — 邮箱禁用态视觉优化：
16. 导航到 /profile
17. 截图：展示邮箱字段带锁图标、灰色背景、提示文字

截图 6 — 引用卡片信息密度优化：
18. 发送一个会触发引用的问题（如 "报销流程是什么？"）
19. 截图：展示折叠状态的引用来源
20. 点击展开，截图：展示紧凑列表样式

截图 7 — 平板中等屏幕优化：
21. 调整浏览器窗口到 900px 宽度
22. 截图：展示中等屏幕下侧边栏默认折叠的状态

截图 8 — 历史对话搜索/筛选（回归测试）：
23. 导航到 /history
24. 在搜索框输入关键词，截图验证过滤效果
25. 点击时间筛选按钮，截图验证

保存所有截图到: frontend/screenshots/iteration6/
命名格式: 01_new_chat.png, 02_onboarding_tour.png, ...
```

### 第二步：TypeScript 检查

```bash
docker compose exec frontend npx tsc --noEmit
```
记录输出中所有 `error TS` 行（排除已知的 ScrollBehavior 警告）。

### 第三步：代码审查

使用 **code-review** 技能对以下文件进行审查：
- `frontend/src/pages/ChatPage.tsx`（新建对话按钮）
- `frontend/src/layout/AppLayout.tsx`（Onboarding Tour + 平板优化）
- `frontend/src/components/chat/MessageBubble.tsx`（分享/重新生成 + 引用优化）
- `frontend/src/pages/ProfilePage.tsx`（邮箱禁用态）
- `frontend/src/store/chatStore.ts`（标题生成优化）

### 第四步：生成功能验证报告

在所有验证和审查完成后，生成 `ux_improvement_report/迭代6功能验证报告.md`，内容格式如下：

```markdown
# 迭代 6 功能验证报告

## 执行摘要
- 验证日期：YYYY-MM-DD
- 验证人：[AI Agent]
- 总任务数：8
- 通过：X/8
- 未通过：Y/8（列出原因）

## 功能验证结果

### 1. 新建对话按钮 ✅/❌
- 描述：...
- 截图：`frontend/screenshots/iteration6/01_new_chat.png`
- 验证结果：...

### 2. 交互式 Onboarding 引导 ✅/❌
- 描述：...
- 截图：`frontend/screenshots/iteration6/02_onboarding_tour_step1.png` 等
- 验证结果：...

（每项同上...）

## TypeScript 检查结果
- 新增错误数：X
- 错误详情：（如有）

## 代码审查结果
- 审查文件数：X
- 发现的问题数：X
- 问题详情：（如有）

## 应用截图总览

| # | 功能 | 截图路径 |
|---|------|---------|
| 1 | 新建对话按钮 | screenshots/iteration6/01_new_chat.png |
| 2 | 交互式 Onboarding | screenshots/iteration6/02_onboarding_tour.png |
| 3 | 消息气泡操作 | screenshots/iteration6/03_message_actions.png |
| 4 | 对话标题优化 | screenshots/iteration6/04_smart_titles.png |
| 5 | 邮箱禁用态 | screenshots/iteration6/05_email_disabled.png |
| 6 | 引用卡片优化 | screenshots/iteration6/06_citations.png |
| 7 | 平板布局 | screenshots/iteration6/07_tablet_layout.png |
| 8 | 历史搜索回归 | screenshots/iteration6/08_history_search.png |

## 总结
（总体评价、遗留问题、下一步建议）
```

### 第五步：更新交接文档

验证报告生成后，更新以下文件：
- **HANDOFF.md** — 将 8 项任务全部标记为 ✅ 迭代 6
- **NEXT_SESSION_PROMPT.md** — 更新状态表
- **ux_improvement_report/ux_improvement_plan.md** — 更新问题清单状态

---

## 注意事项

- 如果某个功能验证失败（截图不符合预期），请记录失败原因并尝试修复后再验证
- agent-browser 截图时需要确保页面完全加载（等待 networkidle0 或关键元素出现）
- 所有截图使用 1440×900 分辨率（桌面端标准），平板截图使用 900×768
- 验证报告中引用的截图路径必须是相对于项目根目录的相对路径
