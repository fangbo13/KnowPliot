# KnowPilot 上线前优化 SPEC（功能 + UI + 并发）

> **版本**: v1.0  
> **日期**: 2026-07-22  
> **分支**: `test/pre-launch-audit-2026-07-22`  
> **状态**: 设计稿（待实施）  
> **测试方法**: 真人视角浏览器操作 + DOM 验证 + 多分辨率响应式测试 + 深色模式对比度审计

---

## 一、测试结果总览

### 已验证通过的功能（✅）

| Bug # | 功能 | 验证结果 |
|-------|------|----------|
| #1 | 通知面板关闭按钮 | ✅ 存在"关闭"按钮 |
| #3 | Profile 安全页面 | ✅ MFA disabled + "暂未上线" + 安全保证消息 + Office Location 必填 |
| #4 | Fast/Deep/Thinking 按钮 | ✅ 三个按钮均可见且可切换 |
| #5 | Profile 布局压缩 | ✅ 4列紧凑布局 |
| #8 | i18n 中文翻译 | ✅ 手动切换后所有文本均为中文 |
| #9 | 所有权转让 | ✅ 单个转让 + 批量转让均已实现 |
| #10 | 移除 effective answer | ✅ 无 legacy 文本显示 |
| #11 | 管理入口权限控制 | ✅ 管理控制台入口仅管理员可见 |
| #13 | 成员角色默认 member | ✅ 无 guest 选项 |
| #14 | 空间管理页面加载 | ✅ 正常加载，无 Failed to load data |
| #16 | 返回按钮 | ✅ 页面顶部存在"返回"按钮 |
| #18 | 响应式布局 | ✅ 768px/375px 自适应 |
| #20 | 空间切换成功提示 | ✅ 显示"Space switched successfully" |
| #21 | 知识库上传功能 | ✅ 上传按钮 + MD推荐 + 上传指南 + "不再提示"按钮 |

### 发现的新问题（⚠️ 需优化）

| 编号 | 问题描述 | 严重度 |
|------|----------|--------|
| F-01 | i18n 语言不持久化：页面导航后语言重置为英文 | 高 |
| F-02 | AuthProvider 不同步 user.language_preference 到 i18n | 高 |
| F-03 | SpaceSwitcher 无搜索框，超过10个空间时无滚动条 | 中 |
| F-04 | 知识库文档列表为空时缺少引导教程 | 中 |
| F-05 | 登录页演示账户显示 admin@test.ey.com 但实际应为 admin@ey.com | 低 |
| UI-01 | 深色模式下 Ant Design Badge 组件文字为黑色 rgba(0,0,0,0.88)，对比度不足 | 高 |
| UI-02 | 通知面板风格与前端设计系统不完全统一 | 中 |
| UI-03 | Profile 页面偏好设置区域布局可进一步优化 | 低 |
| UI-04 | 移动端 SpaceSwitcher 在抽屉中的交互体验待优化 | 中 |
| C-01 | 后端 API 无速率限制，存在并发安全风险 | 高 |
| C-02 | 通知系统无 WebSocket/SSE 实时推送，依赖轮询 | 高 |
| C-03 | SQLite 数据库无法支撑高并发写入 | 高 |
| C-04 | 缺少 Redis 缓存层用于热点数据 | 中 |
| C-05 | 无连接池配置，数据库连接开销大 | 中 |

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

### 2.4 通知系统实时性增强（C-02, Bug #2）

**问题**: 通知系统依赖轮询，无实时推送机制。

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

4. 验证 WCAG 2.1 AA 对比度标准（≥ 4.5:1 对正文文本，≥ 3:1 对大文本）
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

**问题**: Profile 页面偏好设置区域布局仍有优化空间。

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

### 4.1 API 速率限制（C-01）

**问题**: 后端 API 无速率限制，存在并发安全和滥用风险。

**方案**:

```
1. 使用 django-ratelimit 库实现 API 速率限制
2. 限制策略：
   - 认证端点: 5 次/分钟（登录、注册、密码重置）
   - 聊天端点: 20 次/分钟（发送消息）
   - 知识库上传: 10 次/分钟
   - 空间操作: 30 次/分钟
   - 通用读取: 60 次/分钟
3. 基于 IP + User ID 双维度限流
4. 超出限制返回 429 Too Many Requests + Retry-After 头
5. Redis 作为限流计数器存储（如 Redis 不可用，降级为内存计数）
```

**涉及文件**:
- `backend/config/settings/base.py` — 安装 django-ratelimit
- `backend/apps/core/middleware.py` — 全局限流中间件
- `backend/apps/auth/views.py` — 认证端点限流
- `backend/apps/chat/views.py` — 聊天端点限流

**验收标准**:
- 超出限制返回 429
- 限流计数准确（并发请求不漏计）
- 正常使用不受影响

### 4.2 SSE 实时通知推送（C-02）

详见 2.4 节功能优化 SPEC。

### 4.3 数据库并发优化（C-03）

**问题**: SQLite 数据库在并发写入时存在锁竞争，无法支撑高并发场景。

**方案**:

```
阶段 A（当前 — SQLite 优化）:
1. 启用 WAL 模式: PRAGMA journal_mode=WAL
2. 设置 busy_timeout: 5000ms
3. 优化连接配置: settings/database.py 中 CONN_MAX_AGE=60
4. 对只读查询使用 @database_readonly 装饰器路由到只读连接

阶段 B（上线前 — PostgreSQL 迁移）:
1. 使用 PostgreSQL 15+ 作为生产数据库
2. 配置连接池:
   - DATABASES 配置使用 django-db-connection-pool
   - 最大连接数: 20
   - 最小空闲连接: 5
   - 连接超时: 30s
3. 创建以下索引（如不存在）:
   - spaces_membership (user_id, space_id) 复合索引
   - notifications (user_id, read, created_at) 复合索引
   - chat_session (space_id, user_id, updated_at) 复合索引
4. 配置 PostgreSQL pgBouncer 作为连接池中间件
```

**涉及文件**:
- `backend/config/settings/base.py` — 数据库配置
- `backend/config/settings/production.py` — 生产环境配置（新建）

**验收标准**:
- 100 并发用户下无数据库锁错误
- API 响应时间 P95 < 500ms
- 数据库连接数稳定在配置范围内

### 4.4 Redis 缓存层（C-04）

**问题**: 缺少缓存层，热点数据每次都从数据库读取。

**方案**:

```
1. Redis 缓存架构:
   - 会话缓存: django-session-engine 使用 Redis
   - API 响应缓存: 对 GET 请求结果缓存（TTL 60s）
   - 知识库检索缓存: 向量检索结果缓存（TTL 300s）
   - 用户权限缓存: AuthorizationAdapter 结果缓存（TTL 60s）
   - 空间列表缓存: 用户空间列表缓存（TTL 120s）

2. 缓存失效策略:
   - 写操作自动失效相关缓存键
   - 使用 cache key 前缀区分: "kp:user:{id}:*", "kp:space:{id}:*"
   - 支持手动清除: management command `python manage.py clear_cache`

3. Redis 配置:
   - 使用 django-redis 库
   - 连接池最大连接: 50
   - 序列化: django.core.serializers.json.JSONSerializer
   - 压缩: 启用 COMPRESS=1
```

**涉及文件**:
- `backend/config/settings/base.py` — CACHES 配置
- `backend/apps/core/cache.py` — 缓存工具类（新建）
- `backend/apps/spaces/discovery.py` — 空间列表缓存
- `backend/apps/auth/authorization.py` — 权限缓存

**验收标准**:
- 热点数据缓存命中率 > 80%
- API 平均响应时间降低 50%
- Redis 不可用时自动降级到直接查询

### 4.5 异步任务队列（C-05 扩展）

**问题**: 知识库文档解析、向量索引等耗时操作同步执行，阻塞 API 响应。

**方案**:

```
1. 使用 Celery + Redis 作为消息代理
2. 异步任务清单:
   - 知识库文档解析与分块（queue: "knowledge"）
   - 向量索引构建（queue: "knowledge"）
   - 通知批量发送（queue: "notification"）
   - 用户邀请邮件发送（queue: "email"）
   - 定时清理过期会话（queue: "maintenance"）

3. 任务监控:
   - Celery Flower 监控面板（仅管理员可访问）
   - 任务失败自动重试（max_retries=3, retry_backoff=True）
   - 长时间运行任务进度上报到 Redis（前端可查询进度）

4. 前端轮询任务状态:
   - 知识库上传后显示进度条
   - 上传完成通知（通过 SSE 推送）
```

**涉及文件**:
- `backend/config/celery.py` — Celery 配置（新建）
- `backend/apps/knowledge/tasks.py` — 知识库异步任务（新建）
- `backend/apps/notifications/tasks.py` — 通知异步任务（新建）

**验收标准**:
- 知识库上传 API 响应时间 < 2s（解析异步进行）
- 异步任务失败后自动重试
- 任务进度可查询

### 4.6 前端性能优化

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
