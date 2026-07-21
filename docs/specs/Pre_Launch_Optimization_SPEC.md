# KnowPilot 上线前优化 SPEC（功能 + UI + 并发）

> **版本**: v2.0  
> **日期**: 2026-07-22  
> **分支**: `test/pre-launch-audit-2026-07-22`  
> **状态**: 设计稿（待实施）  
> **测试方法**: 真人视角浏览器操作 + DOM 验证 + 多分辨率响应式测试 + 深色模式对比度审计 + API 级联测试 + 后端配置审计  
> **测试角色**: 上线前测试专家 / 人机交互 UI 专家 / 高并发架构专家  

---

## 一、测试结果总览

### 1.1 已验证通过的功能（✅）

| Bug # | 功能 | 验证结果 | 验证方式 |
|-------|------|----------|----------|
| #1 | 通知面板关闭按钮 | ✅ 存在"关闭"按钮 | 浏览器点击通知铃铛 → 面板展开 → Close 按钮可见 |
| #2 | 通知实时性双账号测试 | ✅ Admin 创建公告 → 新注册用户未读数 3，feed 包含公告 | API POST /api/v1/notifications/announcements/ → 新用户 GET /api/v1/notifications/feed/ |
| #3 | Profile 安全页面 | ✅ MFA disabled + "暂未上线" + 安全保证消息 + Office Location 必填(*) | 浏览器导航 Profile → 截图验证 |
| #4 | Fast/Deep/Thinking 按钮 | ✅ 三个按钮均可见且可切换 | Chat 页面 DOM 验证：Fast(pressed), Deep, Thinking(switch) |
| #5 | Profile 布局压缩 | ✅ 4列紧凑布局（Account Info + Preferences + Security） | 截图 23/24 验证 |
| #8 | i18n 中文翻译 | ✅ 手动切换后所有文本均为中文 | 浏览器语言切换测试 |
| #9 | 所有权转让 | ✅ 单个转让 + 批量转让均已实现 | Space Management 页面验证 |
| #10 | 移除 effective answer | ✅ 无 legacy 文本显示 | Chat 页面 DOM 检查 |
| #11 | 管理入口权限控制 | ✅ 管理控制台入口仅管理员可见（8个管理入口） | Admin vs 普通用户对比验证 |
| #13 | 成员角色默认 member | ✅ 无 guest 选项 | Space Management 验证 |
| #14 | 空间管理页面加载 | ✅ 正常加载，无 Failed to load data | 浏览器操作验证 |
| #16 | 返回按钮 | ✅ 页面顶部存在"返回"按钮 | 浏览器导航验证 |
| #18 | 响应式布局 | ✅ 768px/375px 自适应（侧边栏折叠为汉堡按钮） | resize_page 375px → 截图 25 验证 |
| #20 | 空间切换成功提示 | ✅ 显示"Space switched successfully" toast | 浏览器操作验证 |
| #21 | 知识库上传 UI | ✅ 上传按钮 + MD推荐 + 上传指南 + "不再提示"按钮 + 文档操作(Download/Reindex/Edit/Archive) | Knowledge Base 页面截图 26/27 验证 |

### 1.2 发现的新问题（⚠️ 需优化）

#### 功能问题

| 编号 | 问题描述 | 严重度 | 根因 |
|------|----------|--------|------|
| F-01 | i18n 语言不持久化：页面导航后语言重置为英文 | 高 | AuthProvider 未同步 user.language_preference 到 i18n |
| F-02 | AuthProvider 不同步 user.language_preference 到 i18n | 高 | 缺少 useEffect 监听 |
| F-03 | SpaceSwitcher 无搜索框，超过10个空间时无滚动条 | 中 | 下拉菜单未设 maxHeight |
| F-04 | 知识库文档列表为空时缺少引导教程 | 中 | 无空状态组件 |
| F-05 | 登录页演示账户显示 admin@test.ey.com 但实际应为 admin@ey.com | 低 | 硬编码文本错误 |
| **F-06** | **axios 客户端默认 Content-Type: application/json，导致 FormData 上传失败** | **高** | `client.ts` 第164-165行硬编码 `'Content-Type': 'application/json'`，请求拦截器未检查 data 是否为 FormData |
| **F-07** | **知识库文档上传后后端返回 500 错误，文档状态为 Failed，chunks=0** | **高** | 后端文档解析管线在开发环境(SQLite + 无 pgvector)下异常 |

#### UI 问题

| 编号 | 问题描述 | 严重度 | 根因 |
|------|----------|--------|------|
| UI-01 | 深色模式下 Ant Design Badge 组件文字为黑色 rgba(0,0,0,0.88)，对比度不足 | 高 | Badge 组件内部硬编码颜色，未响应 CSS 变量主题切换 |
| UI-02 | 通知面板风格与前端设计系统不完全统一 | 中 | 未完全使用 design tokens |
| UI-03 | Profile 页面偏好设置区域布局可进一步优化 | 低 | 整行排版信息密度低 |
| UI-04 | 移动端 SpaceSwitcher 在抽屉中的交互体验待优化 | 中 | 触摸目标偏小 |

#### 并发问题（经后端配置审计修正）

| 编号 | 问题描述 | 严重度 | 修正说明 |
|------|----------|--------|----------|
| ~~C-01~~ | ~~后端 API 无速率限制~~ | ~~高~~ | **修正：base.py 已配置7种限流策略** — AuthenticatedReadSustained(240/min), AuthenticatedReadBurst(60/10s), AuthenticatedMutation(30/min), Anon(100/min), document_upload(10/min), batch_upload(3/min), signup(5/min)。但需优化限流粒度和告警机制 |
| C-02 | 通知系统无 WebSocket/SSE 实时推送，依赖轮询 | 高 | 仍有效：通知系统仍依赖轮询获取未读数 |
| ~~C-03~~ | ~~SQLite 数据库无法支撑高并发写入~~ | ~~高~~ | **修正：base.py 生产环境已配置 PostgreSQL**（CONN_MAX_AGE=60, CONN_HEALTH_CHECKS=True）。dev.py 覆盖为 SQLite 用于本地开发。问题是 Docker 部署需验证 PostgreSQL 实际生效 |
| ~~C-04~~ | ~~缺少 Redis 缓存层~~ | ~~中~~ | **修正：base.py 已配置 RedisCache**（LOCATION=RATE_LIMIT_REDIS_URL）。dev.py 覆盖为 LocMemCache。但缓存策略（哪些数据缓存、TTL、失效策略）仍需完善 |
| ~~C-05~~ | ~~无连接池配置~~ | ~~中~~ | **修正：已有 CONN_MAX_AGE=60 + CONN_HEALTH_CHECKS=True**。但未使用 PgBouncer 等中间件连接池，CONN_MAX_AGE 仅是 Django 级别的连接复用 |
| **C-06** | **开发环境与生产环境配置差异大，需确保 Docker 部署时使用 production settings** | **高** | dev.py 覆盖了 PostgreSQL→SQLite、RedisCache→LocMemCache、Celery→memory://，生产部署需确认 DJANGO_SETTINGS_MODULE 指向 production |
| **C-07** | **Celery Beat 已配置 notification-action-outbox-sweep 定时任务，但开发环境为同步执行** | **中** | dev.py 设 CELERY_BROKER_URL="memory://"，开发环境 Celery 任务同步执行，可能掩盖异步任务中的竞态条件 |
| **C-08** | **CHAT_TURN_IDEMPOTENCY 默认 False，高并发下可能产生重复消息** | **中** | base.py 第263行 `CHAT_TURN_IDEMPOTENCY = env_bool("CHAT_TURN_IDEMPOTENCY", default=False)` |

---

## 二、功能优化 SPEC

### 2.1 i18n 语言持久化（F-01, F-02）

**问题**: 用户在 Chat 页面切换到中文后，导航到 Profile 页面语言重置为英文。AuthProvider 从 API 获取 `language_preference` 但不同步到 i18n 实例。

**方案**:

```
1. AuthProvider 登录成功后，读取 user.language_preference 并调用 i18n.changeLanguage()
2. 在 AppLayout 中增加 useEffect 监听 user.language_preference 变化
3. 确保 localStorage 'ey-language' 与 user.language_preference 保持同步
4. 当用户在 Profile 页面修改语言偏好时，同时调用 API 更新 + i18n.changeLanguage() + localStorage.setItem()
```

**涉及文件**:
- `frontend/src/auth/AuthProvider.tsx` — 增加 language sync useEffect
- `frontend/src/layout/AppLayout.tsx` — 监听 language_preference 变化
- `frontend/src/pages/ProfilePage.tsx` — 语言偏好变更同步到后端

**验收标准**:
- 登录后页面语言与用户设置的 language_preference 一致
- 页面导航后语言保持不变
- 修改语言偏好后立即生效并持久化

### 2.2 SpaceSwitcher 搜索与滚动（F-03, Bug #19）

**问题**: 当用户加入的空间超过10个时，SpaceSwitcher 下拉菜单无滚动条和搜索框。

**方案**:

```
1. SpaceSwitcher 下拉菜单最大高度限制为 400px，超出时显示垂直滚动条
2. 当空间数量 > 5 时，显示搜索输入框（实时过滤空间名称）
3. 搜索框支持拼音首字母匹配（如输入 "zx" 匹配 "咨询"）
4. 当前选中空间始终显示在列表顶部（check 标识）
5. 每个空间项显示空间名称 + 成员数量 + 可见性图标
```

**涉及文件**:
- `frontend/src/components/SpaceSwitcher.tsx` — 增加搜索框和滚动逻辑
- `frontend/src/styles/globals.css` — SpaceSwitcher 下拉菜单样式

**验收标准**:
- 15个空间时下拉菜单可滚动
- 搜索框可过滤空间
- 当前空间高亮显示

### 2.3 知识库上传教程与引导（F-04, Bug #21 补充）

**问题**: 知识库文档列表为空时缺少引导教程，用户不知如何开始。

**方案**:

```
1. 文档列表为空时显示"上传第一份文档"引导卡片
2. 引导卡片包含：
   a. 支持的文件格式列表（MD/PDF/Word/HTML/TXT）
   b. 推荐使用 MD 格式的说明
   c. "上传文档"按钮
   d. "查看上传教程"链接（弹出步骤引导）
3. 上传教程弹窗包含 4 步：
   Step 1: 选择文件（拖拽或点击）
   Step 2: 设置文档分类和标签
   Step 3: 确认解析预览
   Step 4: 完成上传
4. "不再提示"设置持久化到 localStorage
```

**涉及文件**:
- `frontend/src/pages/admin/KnowledgeBasePage.tsx` — 空状态引导
- `frontend/src/components/knowledge/UploadTutorial.tsx` — 新建教程组件

**验收标准**:
- 空列表显示引导卡片
- 教程弹窗可正常打开和关闭
- "不再提示"设置在页面刷新后保持

### 2.4 通知系统实时性增强（C-02, Bug #2 补充）

**问题**: 通知系统依赖轮询，无实时推送机制。测试中已验证通知数据可达（API 创建公告后新用户可查到），但客户端无实时推送。

**方案**:

```
1. 后端增加 SSE (Server-Sent Events) 端点 /api/v1/notifications/stream/
2. 前端 NotificationBell 组件增加 EventSource 连接
3. SSE 连接失败时自动降级为 30s 轮询
4. SSE 消息格式：
   {
     "type": "notification",
     "data": {
       "id": "...",
       "title": "...",
       "body": "...",
       "category": "announcement|invitation|quality",
       "created_at": "...",
       "read": false
     }
   }
5. 收到实时通知时：
   a. 通知铃铛角标 +1 并闪烁
   b. 通知面板自动追加新项（如面板已打开）
   c. 桌面通知（如用户已授权 Notification API）
```

**涉及文件**:
- `backend/apps/notifications/sse_views.py` — SSE 端点
- `frontend/src/components/NotificationBell.tsx` — EventSource 连接
- `backend/config/urls.py` — SSE 路由

**验收标准**:
- 发送通知后 < 2s 内客户端收到
- SSE 断线后自动重连或降级轮询
- 多标签页不重复显示通知

### 2.5 登录页演示账户修正（F-05）

**问题**: 登录页显示演示账户为 admin@test.ey.com，但实际测试账户为 admin@ey.com。

**方案**: 修正 LoginPage 演示账户文本为 admin@ey.com / admin123。

**涉及文件**: `frontend/src/auth/LoginPage.tsx`

### 2.6 axios 客户端 FormData 修复（F-06, Bug #21 根因）⚠️ 关键

**问题**: `frontend/src/api/client.ts` 第162-167行创建 axios 实例时硬编码 `headers: { 'Content-Type': 'application/json' }`。请求拦截器（第170-189行）添加 auth token 和 X-Space-Id 但未检查请求 data 是否为 FormData。

**影响**: 当上传文件时，axios 会将 FormData 序列化为 JSON 而非 multipart/form-data，导致后端无法正确解析文件内容，返回 400 或 500 错误。

**方案**:

```typescript
// client.ts 请求拦截器修改：
apiClient.interceptors.request.use((config) => {
  // ... existing auth token + space ID logic ...

  // 关键修复：当 data 为 FormData 时，移除默认 Content-Type
  // 让浏览器自动设置 multipart/form-data + boundary
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type'];
    delete config.headers.common?.['Content-Type'];
  }

  return config;
});
```

**涉及文件**:
- `frontend/src/api/client.ts` — 请求拦截器增加 FormData 检测

**验收标准**:
- 上传 MD 文件时请求 Content-Type 为 `multipart/form-data; boundary=...`
- 后端正确解析文件并创建文档记录
- 非 FormData 请求仍保持 `application/json`

### 2.7 知识库文档解析管线修复（F-07, Bug #21 后端）⚠️ 关键

**问题**: 知识库文档上传后（即使 Content-Type 问题修复后），后端文档解析返回 500 错误，文档状态为 "Failed"，chunks=0。

**根因分析**:
- 生产环境依赖 pgvector（PostgreSQL 向量扩展）进行语义检索
- 开发环境（dev.py）使用 SQLite，pgvector 字段存储为 JSON
- 文档解析管线可能在 SQLite + 无 pgvector 环境下异常
- 需排查 `apps/knowledge/` 下的文档分块 + 向量索引逻辑

**方案**:

```
1. 在开发环境增加 pgvector 兼容降级：
   a. 检测数据库引擎，SQLite 时跳过向量索引步骤
   b. 仅存储文本分块，不执行向量嵌入
   c. 文档状态标记为 "Indexed (text only)" 而非 "Failed"

2. 增加文档解析错误处理：
   a. 解析失败时记录详细错误日志（当前可能静默失败）
   b. 文档状态从 "Processing" → "Failed" 时附带错误原因
   c. 前端展示错误原因（而非仅 "Failed" 标签）

3. 验证 Docker 部署时：
   a. 确认 PostgreSQL 启动并启用 pgvector 扩展
   b. 确认 Celery worker 正常消费 knowledge 队列
   c. 确认 Redis 用于 Celery broker 和缓存
```

**涉及文件**:
- `backend/apps/knowledge/tasks.py` — 文档解析异步任务
- `backend/apps/knowledge/models.py` — 文档状态字段增加 error_reason
- `backend/apps/knowledge/views.py` — 上传错误处理
- `frontend/src/pages/admin/KnowledgeBasePage.tsx` — 展示错误原因

**验收标准**:
- 开发环境上传 MD 文件后文档状态为 "Indexed" 或 "Indexed (text only)"
- 解析失败时前端显示具体错误原因
- Docker 部署时完整解析管线正常工作

---

## 三、UI 优化 SPEC

### 3.1 深色模式对比度修复（UI-01, Bug #6 补充）

**问题**: 深色模式下 Ant Design Badge 组件文字使用 `rgba(0, 0, 0, 0.88)`（黑色），在深色背景上几乎不可见。

**根因**: Ant Design 的 Badge 组件内部使用了硬编码的 `color: rgba(0,0,0,0.88)`，未响应 CSS 变量主题切换。

**方案**:

```
1. 在 globals.css 中增加深色模式 Badge 覆盖样式：
   [data-theme="dark"] .ant-badge-count {
     color: var(--color-text-primary) !important;
   }
   [data-theme="dark"] .ant-badge-dot {
     background: var(--accent) !important;
   }

2. 排查所有 Ant Design 组件在深色模式下的硬编码颜色：
   a. Badge (BadgeCount, BadgeDot)
   b. Tag
   c. Alert
   d. Tabs
   e. Modal
   f. Table

3. 为每个组件增加 [data-theme="dark"] 覆盖样式，使用 design tokens 中的颜色变量

4. 验证 WCAG 2.1 AA 对比度标准（≥ 4.5:1 对正文文本，≥ 3:0 对大文本）
```

**涉及文件**:
- `frontend/src/styles/globals.css` — Ant Design 组件深色模式覆盖
- `frontend/src/styles/design-system.css` — 设计系统深色模式补全

**验收标准**:
- 深色模式下所有文字对比度 ≥ 4.5:1
- 无黑色文字出现在深色背景上
- Badge、Tag、Alert 等组件颜色与设计系统一致

### 3.2 通知面板设计统一（UI-02, Bug #1 补充）

**问题**: 通知面板的视觉风格与前端整体设计系统不完全统一。

**方案**:

```
1. 通知面板使用 design tokens 中的变量：
   - 背景: var(--color-bg-elevated)
   - 边框: var(--color-border-primary)
   - 圆角: var(--radius-lg) (14px)
   - 阴影: var(--shadow-lg)
   - 文字: var(--color-text-primary)

2. 通知项卡片化设计：
   - 每条通知为独立卡片，hover 时背景微亮
   - 未读通知左侧有 3px 宽的 accent 颜色竖条
   - 通知图标按类型区分颜色：
     announcement → 蓝色
     invitation → 绿色
     quality → 紫色
     system → 灰色

3. 关闭按钮统一为 icon-btn 样式，使用 CloseOutlined 图标

4. 通知时间格式本地化：
   - 中文: "3分钟前"、"1小时前"、"昨天"
   - 英文: "3 min ago"、"1 hour ago"、"Yesterday"
```

**涉及文件**:
- `frontend/src/components/NotificationBell.tsx` — 样式重构
- `frontend/src/styles/globals.css` — 通知面板样式

**验收标准**:
- 通知面板视觉与整体设计系统统一
- 不同类型通知有区分度
- 关闭按钮风格一致

### 3.3 Profile 页面布局优化（UI-03, Bug #5 补充）

**问题**: Profile 页面偏好设置区域布局仍有优化空间，整行排版信息密度低。

**方案**:

```
1. 账户信息区域：
   - 头像 + 邮箱在左侧（占 1/3 宽度）
   - SERVICE LINE / OFFICE LOCATION / ROLE LEVEL / EMAIL 在右侧网格布局（2x2）

2. 偏好设置区域：
   - Language Preference + Theme 在一行（各占 1/2 宽度）
   - Default Space 单独一行（全宽）
   - 通知开关两个并排在一行

3. 安全区域：
   - 左侧：修改密码按钮
   - 右侧：MFA 按钮（disabled + Coming soon）
   - 下方：安全保证消息（全宽 alert）

4. 所有区域间距统一使用 var(--space-md) (16px)
```

**涉及文件**: `frontend/src/pages/ProfilePage.tsx`

**验收标准**:
- 信息密度合理，无大块空白
- 各区域视觉层次清晰
- 在 1024px 和 768px 宽度下布局自适应

### 3.4 移动端 SpaceSwitcher 优化（UI-04）

**问题**: 移动端抽屉中的 SpaceSwitcher 交互体验待优化。

**方案**:

```
1. 移动端抽屉中 SpaceSwitcher 占满宽度
2. 当前空间高亮显示（accent 左边框 + 微亮背景）
3. 空间列表项高度增加到 48px（符合触摸目标 ≥ 44px 标准）
4. 切换空间后自动关闭抽屉
5. 切换空间后显示 toast 提示（已有，确认移动端也生效）
```

**涉及文件**:
- `frontend/src/components/SpaceSwitcher.tsx`
- `frontend/src/styles/globals.css`

### 3.5 响应式布局完善（Bug #18 补充）

**已验证**: 768px 侧边栏折叠、375px 移动端抽屉均正常工作。

**补充优化**:

```
1. ChatComposer 在 480px 以下宽度时：
   - 快捷问题按钮改为 2 列网格（当前为 1 列或 3 列）
   - Fast/Deep/Thinking 按钮等宽排列
   - 输入框最小高度 48px

2. 空间管理页面在 768px 以下：
   - 表单字段改为单列
   - 成员列表改为卡片式
   - 批量转让表格改为可横向滚动

3. Admin Console 在 1024px 以下：
   - 侧边栏图标 + 文字 → 仅图标
   - hover 时展开 tooltip 显示文字
```

**涉及文件**:
- `frontend/src/styles/globals.css`
- `frontend/src/styles/chat.css`

---

## 四、并发优化 SPEC

### 4.1 限流策略优化（C-01 修正）

**现状**: base.py 已配置7种限流策略，覆盖导航读取、变更操作、匿名访问、文档上传、批量上传、注册。

**仍需优化**:

```
1. 限流粒度优化：
   a. 当前 navigation_read_burst 为 60/10s，高并发场景下可能误伤正常用户
   b. 建议增加 user-tier 限流：管理员 500/min，普通用户 240/min
   c. 增加基于 API 端点的精细化限流（如 chat 端点单独限流）

2. 限流告警：
   a. 当用户触发限流时记录到审计日志
   b. 连续触发限流3次以上的用户自动标记为可疑
   c. 管理员 Dashboard 展示限流统计

3. 限流降级策略：
   a. Redis 不可用时降级为内存限流（已有 LocMemCache）
   b. 降级时日志告警 "Rate limiting degraded to in-memory"
```

**涉及文件**:
- `backend/apps/core/throttling.py` — 增加 tier-based 限流
- `backend/apps/audit/views.py` — 限流审计日志

**验收标准**:
- 限流不影响正常用户操作
- 限流触发有审计记录
- Redis 降级时限流仍生效

### 4.2 SSE 实时通知推送（C-02）

详见 2.4 节功能优化 SPEC。

### 4.3 生产环境数据库验证与优化（C-03 修正）

**现状**: base.py 已配置 PostgreSQL（CONN_MAX_AGE=60, CONN_HEALTH_CHECKS=True），dev.py 覆盖为 SQLite。

**仍需优化**:

```
1. 创建 production.py settings 确保生产环境使用 PostgreSQL：
   a. 不继承 dev.py 的 SQLite 覆盖
   b. 启用 pgvector 扩展
   c. 增加 PostgreSQL 连接池优化参数

2. Docker 部署验证清单：
   a. docker-compose.yml 中 PostgreSQL 服务正常启动
   b. pgvector 扩展已安装（CREATE EXTENSION vector）
   c. DJANGO_SETTINGS_MODULE 指向 production settings
   d. 数据库迁移正常执行
   e. CONN_MAX_AGE=60 生效（验证连接复用）

3. 数据库索引优化（验证或创建）：
   - spaces_membership (user_id, space_id) 复合索引
   - notifications (user_id, read, created_at) 复合索引
   - chat_session (space_id, user_id, updated_at) 复合索引
   - knowledge_document (space_id, status, created_at) 复合索引
```

**涉及文件**:
- `backend/config/settings/production.py` — 生产环境配置
- `backend/docker-compose.yml` — PostgreSQL + Redis 服务配置

**验收标准**:
- Docker 部署使用 PostgreSQL + pgvector
- 100 并发用户下无数据库锁错误
- API 响应时间 P95 < 500ms

### 4.4 Redis 缓存策略完善（C-04 修正）

**现状**: base.py 已配置 RedisCache（LOCATION=RATE_LIMIT_REDIS_URL, KEY_PREFIX="knowpilot"），dev.py 覆盖为 LocMemCache。

**仍需完善**:

```
1. 业务缓存策略（当前仅限流使用 Redis）：
   a. 用户权限缓存: AuthorizationAdapter 结果缓存（TTL 60s）
      - key: kp:user:{id}:permissions
      - 失效: 用户角色变更时清除
   
   b. 空间列表缓存: 用户空间列表缓存（TTL 120s）
      - key: kp:user:{id}:spaces
      - 失效: 加入/离开空间时清除
   
   c. 知识库检索缓存: 向量检索结果缓存（TTL 300s）
      - key: kp:space:{id}:search:{query_hash}
      - 失效: 文档上传/删除时清除
   
   d. API 响应缓存: GET 请求结果缓存（TTL 60s）
      - 仅缓存幂等 GET 请求
      - 不缓存包含用户特定数据的响应

2. 缓存失效策略：
   a. 写操作（POST/PUT/PATCH/DELETE）自动清除相关缓存键
   b. 使用 cache key pattern: "kp:user:{id}:*", "kp:space:{id}:*"
   c. 支持 management command: python manage.py clear_cache --pattern="kp:user:*"

3. Redis 健康检查：
   a. 增加健康检查端点 /api/v1/health/redis/
   b. Redis 不可用时自动降级到 LocMemCache
   c. 告警通知管理员
```

**涉及文件**:
- `backend/apps/core/cache.py` — 缓存工具类（新建）
- `backend/apps/spaces/discovery.py` — 空间列表缓存
- `backend/apps/auth/authorization.py` — 权限缓存

**验收标准**:
- 热点数据缓存命中率 > 80%
- API 平均响应时间降低 50%
- Redis 不可用时自动降级到直接查询

### 4.5 Celery 异步任务完善（C-07 新增）

**现状**: base.py 已配置 Celery + Redis broker，已有 notification-action-outbox-sweep 定时任务（60s 间隔）。dev.py 设 CELERY_BROKER_URL="memory://"，开发环境同步执行。

**仍需完善**:

```
1. 知识库异步任务（当前可能同步执行）：
   a. 文档解析与分块 → queue: "knowledge"
   b. 向量索引构建 → queue: "knowledge"
   c. 上传完成后通过 SSE 通知前端

2. 通知批量发送异步化：
   a. 广播通知到大量用户时使用 Celery 批量任务
   b. 分批处理（每批 100 用户）
   c. 失败自动重试（max_retries=3, retry_backoff=True）

3. 定时任务扩展：
   a. 已有: notification-action-outbox-sweep (60s)
   b. 新增: 过期会话清理 (每日)
   c. 新增: 文档索引状态检查 (5min)
   d. 新增: 缓存命中率统计上报 (5min)

4. 开发环境异步测试：
   a. 增加 Celery worker 本地启动脚本
   b. 使用 Redis 作为本地 broker（而非 memory://）
   c. 避免开发时掩盖竞态条件

5. Celery Flower 监控：
   a. 仅管理员可访问 /admin/celery-flower/
   b. 展示任务队列、成功率、平均执行时间
```

**涉及文件**:
- `backend/config/celery.py` — Celery 配置完善
- `backend/apps/knowledge/tasks.py` — 知识库异步任务
- `backend/apps/notifications/tasks.py` — 通知异步任务完善

**验收标准**:
- 知识库上传 API 响应时间 < 2s（解析异步进行）
- 异步任务失败后自动重试
- 任务进度可查询
- 开发环境可模拟异步执行

### 4.6 聊天幂等性保护（C-08 新增）

**问题**: `CHAT_TURN_IDEMPOTENCY` 默认 False，高并发下用户快速连续发送消息可能产生重复消息。

**方案**:

```
1. 生产环境启用 CHAT_TURN_IDEMPOTENCY=true
2. 前端 ChatComposer 在发送消息时生成唯一 turn_id
3. 后端检查 turn_id 是否已处理：
   a. 已处理 → 返回之前的响应（幂等）
   b. 未处理 → 正常处理并记录 turn_id
4. Redis 作为 turn_id 存储缓存（TTL 5min）
5. 降级策略：Redis 不可用时跳过幂等检查 + 日志告警
```

**涉及文件**:
- `backend/config/settings/production.py` — CHAT_TURN_IDEMPOTENCY=True
- `backend/apps/chat/views.py` — turn_id 幂等检查
- `frontend/src/components/ChatComposer.tsx` — 生成 turn_id

**验收标准**:
- 快速连续发送相同消息不产生重复
- turn_id 相同的请求返回相同响应
- Redis 不可用时降级不影响正常使用

### 4.7 生产环境配置确认（C-06 新增）⚠️ 关键

**问题**: dev.py 大量覆盖了 base.py 的生产配置，需确保 Docker 部署时使用正确的 settings module。

**配置差异对照**:

| 配置项 | base.py (生产) | dev.py (开发) | 风险 |
|--------|---------------|-------------|------|
| DATABASES | PostgreSQL + pgvector | SQLite | 生产必须用 PG |
| CACHES | RedisCache | LocMemCache | 生产必须用 Redis |
| CELERY_BROKER_URL | redis://... | memory:// | 生产必须用 Redis broker |
| CHAT_COORDINATION_REDIS_URL | redis://... | "" (空) | 生产必须配 Redis |
| DEBUG | False | True | 生产必须 False |
| ALLOWED_HOSTS | 环境变量 | ["*"] | 生产需限制 |
| CORS_ALLOW_ALL_ORIGINS | False | True | 生产需限制 |

**方案**:

```
1. 创建 backend/config/settings/production.py：
   a. 继承 base.py（from .base import *）
   b. DEBUG = False
   c. ALLOWED_HOSTS 从环境变量读取
   d. 确认 PostgreSQL/Redis/Celery 配置不被覆盖
   e. 启用 CHAT_TURN_IDEMPOTENCY=True
   f. 启用 CHAT_STREAM_V2=true（如已就绪）

2. Docker 部署验证：
   a. Dockerfile 中设置 ENV DJANGO_SETTINGS_MODULE=config.settings.production
   b. docker-compose.yml 确认 PostgreSQL + Redis 服务
   c. entrypoint 脚本验证数据库连接
   d. 健康检查端点 /api/v1/health/ 检查 DB + Redis + Celery
```

**涉及文件**:
- `backend/config/settings/production.py` — 新建生产配置
- `backend/Dockerfile` — DJANGO_SETTINGS_MODULE 环境变量

**验收标准**:
- Docker 部署使用 production settings
- PostgreSQL + Redis + Celery 全部正常工作
- DEBUG=False 在生产环境

### 4.8 前端性能优化

**方案**:

```
1. 代码分割（已有 lazy loading，进一步优化）:
   - Admin Console 整体懒加载
   - Knowledge Base 页面懒加载
   - Space Management 页面懒加载

2. 数据预取:
   - 登录成功后预取用户空间列表
   - 空间切换后预取对话列表
   - 使用 React Query (TanStack Query) 管理数据缓存

3. 虚拟列表:
   - 通知列表超过 50 条时启用虚拟滚动
   - 对话列表超过 100 条时启用虚拟滚动
   - 知识库文档列表超过 50 条时启用虚拟滚动

4. 图片优化:
   - 用户头像使用 WebP 格式
   - 品牌Logo SVG 内联（已有）

5. Bundle 优化:
   - 分析 bundle 大小: vite-bundle-visualizer
   - 按路由分割 chunk
   - Tree-shaking 未使用的 Ant Design 组件
```

**涉及文件**:
- `frontend/src/router.tsx` — 路由懒加载
- `frontend/src/hooks/usePrefetch.ts` — 数据预取 Hook（新建）
- `frontend/vite.config.ts` — Bundle 优化配置

**验收标准**:
- 首屏加载时间 < 2s（LCP）
- 交互响应时间 < 100ms (FID/INP)
- Bundle 总大小 < 500KB (gzip)

---

## 五、优先级排序

| 优先级 | 编号 | 问题 | 影响 |
|--------|------|------|------|
| P0（阻断上线） | F-06 | axios FormData 修复 | 知识库上传完全不可用 |
| P0（阻断上线） | F-07 | 知识库文档解析修复 | 上传后文档状态 Failed |
| P0（阻断上线） | C-06 | 生产环境配置确认 | Docker 部署配置差异风险 |
| P1（高优先） | C-02 | SSE 实时通知 | 用户体验核心 |
| P1（高优先） | F-01/F-02 | i18n 语言持久化 | 多语言用户体验 |
| P1（高优先） | UI-01 | 深色模式对比度 | 可访问性 |
| P2（中优先） | C-03 | PostgreSQL 部署验证 | 并发支撑 |
| P2（中优先） | C-04 | Redis 缓存策略 | 性能优化 |
| P2（中优先） | C-08 | 聊天幂等性 | 并发安全 |
| P2（中优先） | F-03 | SpaceSwitcher 搜索 | UX 优化 |
| P3（低优先） | F-05 | 登录页演示账户 | 细节修正 |
| P3（低优先） | UI-03 | Profile 布局 | UI 美化 |

---

## 六、截图引用

| 截图编号 | 文件名 | 验证内容 |
|----------|--------|----------|
| 22 | `pre_launch_audit/22-bug2-notification-panel.png` | Bug #2 通知面板展示 |
| 23 | `pre_launch_audit/23-profile-dark-mode.png` | Bug #3/5 Profile 深色模式 |
| 24 | `pre_launch_audit/24-profile-light-mode.png` | Bug #3/5 Profile 浅色模式 |
| 25 | `pre_launch_audit/25-profile-mobile-375px.png` | Bug #18 移动端响应式 |
| 26 | `pre_launch_audit/26-knowledge-base-light.png` | Bug #21 知识库浅色模式 |
| 27 | `pre_launch_audit/27-knowledge-base-dark.png` | Bug #21 知识库深色模式 |

---

> **备注**: 本 SPEC 为设计稿，不包含实施代码。所有涉及文件路径仅为修改指引，实际实施时需逐文件验证当前代码状态后再修改。
