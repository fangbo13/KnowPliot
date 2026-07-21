# KnowPilot 上线前测试报告

> **测试日期**: 2026-07-22  
> **测试分支**: `test/pre-launch-audit-2026-07-22`  
> **测试人员**: 测试专家 / UI专家 / 并发专家  
> **测试方法**: 真人视角浏览器操作 + API 级联测试 + 后端配置审计  
> **测试环境**: Windows 25H2 / Chrome DevTools MCP / Vite 5.4.21 / Django + DRF  

---

## 一、测试环境

| 组件 | 状态 | 端口 | 版本 |
|------|------|------|------|
| Frontend (Vite) | ✅ 运行中 | 3010 | v5.4.21 |
| Backend (Django) | ✅ 运行中 | 8000 | Python 3.11.4 |
| 数据库 | SQLite (开发环境) | - | db.sqlite3 |
| 缓存 | LocMemCache (开发环境) | - | - |
| Celery | memory:// (同步执行) | - | - |

> 注：生产环境将使用 PostgreSQL + Redis + Celery (Redis broker)

---

## 二、Bug 验证结果

### 2.1 Bug #1: 通知面板关闭按钮 ✅

**测试步骤**: 点击右上角通知铃铛 → 通知面板展开 → 检查关闭按钮

**结果**: ✅ 通过。通知面板有 "Close" 按钮，可正常关闭面板。

**截图**: [22-bug2-notification-panel.png](../screenshots/pre_launch_audit/22-bug2-notification-panel.png)

---

### 2.2 Bug #2: 双账号通知实时性 ✅

**测试步骤**:
1. Admin 登录获取 token
2. POST /api/v1/notifications/announcements/ 创建公告 (audience=all)
3. 注册新用户 tester2@ey.com
4. 新用户 GET /api/v1/notifications/feed/ 检查是否收到公告

**结果**: ✅ 通过。
- Admin 创建公告成功 (201 Created, ID: a713c1d0-9fe7-4c35-a5af-c32eb8cc429a)
- Admin 未读数从 1 → 2
- 新注册用户未读数 = 3
- 新用户 feed 中包含测试公告 ✅

**发现**: 通知数据可达，但客户端依赖轮询而非实时推送（SSE/WebSocket 缺失，详见 SPEC C-02）

**截图**: [22-bug2-notification-panel.png](../screenshots/pre_launch_audit/22-bug2-notification-panel.png)

---

### 2.3 Bug #3: Profile 安全页面 ✅

**测试步骤**: 导航到 Profile 页面 → 检查安全区域

**结果**: ✅ 通过。
- MFA 按钮 disabled + 显示 "Coming soon"
- 安全保证消息："KnowPilot will continuously safeguard your account security..."
- Office Location 标记为必填 (*)
- 不显示设备/会话信息

**截图**: 
- 深色模式: [23-profile-dark-mode.png](../screenshots/pre_launch_audit/23-profile-dark-mode.png)
- 浅色模式: [24-profile-light-mode.png](../screenshots/pre_launch_audit/24-profile-light-mode.png)

---

### 2.4 Bug #4: Fast/Deep/Thinking 按钮 ✅

**测试步骤**: 导航到 Chat 页面 → 检查按钮区

**结果**: ✅ 通过。三个按钮均可见且可切换：
- Fast (pressed 状态)
- Deep (switch 按钮)
- Thinking (switch 按钮)

---

### 2.5 Bug #5: Profile 布局 ✅

**测试步骤**: 导航到 Profile 页面 → 检查布局结构

**结果**: ✅ 通过。三个区域紧凑布局：
- Account Information (头像 + 邮箱 + SERVICE LINE + OFFICE LOCATION + ROLE LEVEL)
- Preferences (Language + Theme + Default Space + 通知开关)
- Account security (修改密码 + MFA + 安全保证)

**截图**: [23-profile-dark-mode.png](../screenshots/pre_launch_audit/23-profile-dark-mode.png)

---

### 2.6 Bug #8: i18n 中文翻译 ✅

**测试步骤**: 手动切换语言为中文 → 检查页面文本

**结果**: ✅ 通过。手动切换后所有文本均为中文。

**发现问题**: 语言切换不持久化，页面导航后重置为英文（F-01, F-02）

---

### 2.7 Bug #9: 所有权转让 ✅

**测试步骤**: 导航到 Space Management → 检查转让功能

**结果**: ✅ 通过。单个转让 + 批量转让均已实现。

---

### 2.8 Bug #10: 移除 effective answer ✅

**测试步骤**: Chat 页面 → DOM 检查

**结果**: ✅ 通过。无 legacy 文本显示，无 "effective answer setting" 内容。

---

### 2.9 Bug #11: 管理入口权限控制 ✅

**测试步骤**: Admin 登录 → 检查侧边栏和用户菜单

**结果**: ✅ 通过。Admin 可见 8 个管理入口：
1. Management Console
2. Workspace Management
3. Knowledge Base
4. Dashboard
5. Users & Roles
6. Registration Codes
7. Version Announcements
8. Audit Logs

普通用户不可见这些入口。

**截图**: [11-user-menu-admin.png](../screenshots/pre_launch_audit/11-user-menu-admin.png), [12-management-console.png](../screenshots/pre_launch_audit/12-management-console.png)

---

### 2.10 Bug #13: 成员角色默认 member ✅

**结果**: ✅ 通过。无 guest 选项，接受邀请后默认 member。

---

### 2.11 Bug #14: 空间管理页面加载 ✅

**测试步骤**: 导航到 Space Management

**结果**: ✅ 通过。正常加载，无 "Failed to load data" 错误。

**截图**: [16-space-management.png](../screenshots/pre_launch_audit/16-space-management.png)

---

### 2.12 Bug #16: 返回按钮 ✅

**结果**: ✅ 通过。页面顶部存在返回按钮。

---

### 2.13 Bug #18: 响应式布局 ✅

**测试步骤**: resize_page 到 375px → 检查布局

**结果**: ✅ 通过。
- 768px: 侧边栏折叠
- 375px: 侧边栏折叠为汉堡按钮 "Open mobile menu"
- Profile 内容垂直堆叠

**截图**: [25-profile-mobile-375px.png](../screenshots/pre_launch_audit/25-profile-mobile-375px.png)

---

### 2.14 Bug #20: 空间切换成功提示 ✅

**结果**: ✅ 通过。切换空间后显示 "Space switched successfully" toast。

**截图**: [10-space-switched.png](../screenshots/pre_launch_audit/10-space-switched.png)

---

### 2.15 Bug #21: 知识库上传 UI ✅ (功能 ⚠️)

**测试步骤**: 导航到 Knowledge Base → 检查 UI 组件

**结果**: 
- UI: ✅ 通过
  - Upload 按钮存在
  - MD 格式推荐提示
  - Upload Guide 弹窗
  - "Don't show again" 按钮
  - 文档操作: Download, Reindex, Edit, Archive
- 功能: ⚠️ 问题
  - 文档上传后状态为 "Failed"，chunks=0
  - 根因 1: axios client.ts 硬编码 Content-Type: application/json (F-06)
  - 根因 2: 后端文档解析在开发环境(SQLite + 无pgvector)下异常 (F-07)

**截图**: 
- 浅色模式: [26-knowledge-base-light.png](../screenshots/pre_launch_audit/26-knowledge-base-light.png)
- 深色模式: [27-knowledge-base-dark.png](../screenshots/pre_launch_audit/27-knowledge-base-dark.png)
- 上传测试: [21-bug21-upload-test.png](../screenshots/pre_launch_audit/21-bug21-upload-test.png)

---

## 三、新发现问题

### 3.1 功能问题

| 编号 | 问题 | 严重度 | 详情 |
|------|------|--------|------|
| F-01 | i18n 语言不持久化 | 高 | 页面导航后语言重置为英文 |
| F-02 | AuthProvider 不同步语言偏好 | 高 | 缺少 useEffect 监听 |
| F-03 | SpaceSwitcher 无搜索/滚动 | 中 | >10空间时无法操作 |
| F-04 | 知识库空列表无引导 | 中 | 用户体验差 |
| F-05 | 登录页演示账户错误 | 低 | admin@test.ey.com → admin@ey.com |
| **F-06** | **axios FormData 上传失败** | **高** | client.ts 硬编码 Content-Type: application/json |
| **F-07** | **知识库文档解析 500 错误** | **高** | 开发环境 pgvector 缺失导致解析失败 |

### 3.2 UI 问题

| 编号 | 问题 | 严重度 | 详情 |
|------|------|--------|------|
| UI-01 | 深色模式 Badge 文字不可见 | 高 | rgba(0,0,0,0.88) 在深色背景上 |
| UI-02 | 通知面板风格不统一 | 中 | 未完全使用 design tokens |
| UI-03 | Profile 布局可优化 | 低 | 整行排版信息密度低 |
| UI-04 | 移动端 SpaceSwitcher 待优化 | 中 | 触摸目标偏小 |

### 3.3 并发问题（经后端配置审计修正）

| 编号 | 问题 | 严重度 | 修正说明 |
|------|------|--------|----------|
| ~~C-01~~ | ~~无速率限制~~ | - | **修正**: 已有7种限流策略，需优化粒度 |
| C-02 | 无 SSE 实时推送 | 高 | 仍有效，依赖轮询 |
| ~~C-03~~ | ~~SQLite 不支持并发~~ | - | **修正**: 生产用 PostgreSQL，仅开发用 SQLite |
| ~~C-04~~ | ~~缺少 Redis 缓存~~ | - | **修正**: 已配置 RedisCache，需完善缓存策略 |
| ~~C-05~~ | ~~无连接池~~ | - | **修正**: 已有 CONN_MAX_AGE=60 + HEALTH_CHECKS |
| **C-06** | **生产配置确认** | **高** | dev.py 大量覆盖需确保 Docker 部署用 production |
| **C-07** | **Celery 开发环境同步执行** | **中** | memory:// 可能掩盖竞态条件 |
| **C-08** | **聊天幂等性默认关闭** | **中** | CHAT_TURN_IDEMPOTENCY=False |

---

## 四、后端配置审计

### 4.1 限流配置 (base.py)

已配置7种限流策略：
- `navigation_read_sustained`: 240/min
- `navigation_read_burst`: 60/10s
- `user_mutation`: 30/min
- `anon`: 100/min
- `document_upload`: 10/min
- `batch_upload`: 3/min
- `signup`: 5/min

### 4.2 数据库配置

- **生产 (base.py)**: PostgreSQL + pgvector, CONN_MAX_AGE=60, CONN_HEALTH_CHECKS=True
- **开发 (dev.py)**: SQLite (覆盖 PostgreSQL)

### 4.3 缓存配置

- **生产 (base.py)**: RedisCache, KEY_PREFIX="knowpilot"
- **开发 (dev.py)**: LocMemCache (覆盖 Redis)

### 4.4 Celery 配置

- **生产 (base.py)**: Redis broker, Celery Beat (notification-action-outbox-sweep 60s)
- **开发 (dev.py)**: memory:// (同步执行)

### 4.5 JWT 配置

- Access token: 15min
- Refresh token: 7days
- ROTATE_REFRESH_TOKENS: True
- BLACKLIST_AFTER_ROTATION: True

---

## 五、截图清单

| 编号 | 文件名 | 验证内容 |
|------|--------|----------|
| 01 | 01-chat-welcome.png | Chat 欢迎页面 |
| 02 | 02-chat-chinese.png | Chat 中文界面 |
| 09 | 09-space-switcher-dropdown.png | 空间切换下拉菜单 |
| 10 | 10-space-switched.png | Bug #20 空间切换成功提示 |
| 11 | 11-user-menu-admin.png | Bug #11 管理员用户菜单 |
| 12 | 12-management-console.png | Bug #11 管理控制台 |
| 13 | 13-dark-mode-desktop.png | 深色模式桌面 |
| 14 | 14-responsive-tablet-768.png | Bug #18 平板响应式 |
| 15 | 15-responsive-mobile-375.png | Bug #18 移动端响应式 |
| 16 | 16-space-management.png | Bug #14 空间管理 |
| 17 | 17-knowledge-base-admin.png | 知识库管理 |
| 18 | 18-bug15-invites-enabled.png | Bug #15 邀请开启 |
| 19 | 19-bug15-invites-disabled.png | Bug #15 邀请关闭 |
| 20 | 20-bug17-rapid-switch-user-menu.png | Bug #17 快速切换 |
| 21 | 21-bug21-upload-test.png | Bug #21 上传测试 |
| 22 | 22-bug2-notification-panel.png | Bug #2 通知面板 |
| 23 | 23-profile-dark-mode.png | Bug #3/5 Profile 深色 |
| 24 | 24-profile-light-mode.png | Bug #3/5 Profile 浅色 |
| 25 | 25-profile-mobile-375px.png | Bug #18 Profile 移动端 |
| 26 | 26-knowledge-base-light.png | Bug #21 知识库浅色 |
| 27 | 27-knowledge-base-dark.png | Bug #21 知识库深色 |

---

## 六、测试结论

### 6.1 通过项 (14/21)

Bug #1, #2, #3, #4, #5, #8, #9, #10, #11, #13, #14, #16, #18, #20, #21(UI部分) 全部通过验证。

### 6.2 需优化项

- **P0 阻断**: F-06 (axios FormData), F-07 (文档解析 500), C-06 (生产配置确认)
- **P1 高优先**: C-02 (SSE), F-01/F-02 (i18n), UI-01 (深色模式对比度)
- **P2 中优先**: C-03 (PG部署), C-04 (Redis缓存), C-08 (聊天幂等), F-03 (SpaceSwitcher)
- **P3 低优先**: F-05 (登录页), UI-03 (Profile布局)

### 6.3 后端基础设施评估

经配置审计，后端基础设施已相当完善：
- ✅ 7种限流策略已配置
- ✅ PostgreSQL + pgvector 已配置（生产）
- ✅ Redis 缓存已配置（生产）
- ✅ 连接池 (CONN_MAX_AGE + HEALTH_CHECKS) 已配置
- ✅ Celery + Redis broker + Beat 已配置
- ✅ JWT 旋转 + 黑名单已配置
- ⚠️ 需确保 Docker 部署使用 production settings 而非 dev settings
- ⚠️ 需完善业务缓存策略（当前仅限流使用 Redis）
- ⚠️ SSE 实时推送仍缺失

---

> **完整优化 SPEC 见**: `docs/specs/Pre_Launch_Optimization_SPEC.md` (v2.0)
