# EY Onboarding AI V4.3 — UAT 验收问题修复 Prompt

> **来源**: UAT 验收测试 (`UAT_Test_Report_2026-06-26_Final.md`)
> **测试环境**: Docker SYS — Frontend :3030 / Backend :8030 / DB :5435 / Redis :6382
> **测试工具**: Playwright Chromium (headless: false, 1280x800)
> **测试账号**: admin@ey.com / admin123

---

## 测试结果概要

| 指标 | 数值 |
|------|------|
| 总步骤 | 24 |
| PASS | 19 |
| FAIL | 0 |
| WARN | 5 |
| 通过率 | 79.2% |
| 控制台错误 | 0 |
| 网络失败 | 0 |

## 需要修复的问题 (按优先级排序)

### 问题 1: AI 响应失败 — "当前无法获取响应" (P1)

**现象**: 发送消息后，AI 返回 "当前无法获取响应" 错误提示和 "重试" 按钮。

**截图证据**: `screenshots/uat_v42/S2_04_response.png`

**可能原因**:
- DashScope API Key 未配置、已过期或无效
- Docker 容器内无法访问 DashScope API（网络问题）
- 断路器 (Circuit Breaker) 已触发且未恢复（V4.2 新增的 `backend/apps/core/circuit_breaker.py`）
- SSE 超时配置问题（V4.2 新增的 `SSE_TIMEOUT_SECONDS = 60`）
- 后端日志中应有具体错误信息

**修复方向**:
1. 检查 `.env` 文件中的 `DASHSCOPE_API_KEY` 是否有效
2. 在 Docker 容器内测试 DashScope API 连通性：`docker compose exec backend python -c "import httpx; print(httpx.get('https://dashscope.aliyuncs.com').status_code)"`
3. 检查 `backend/apps/core/circuit_breaker.py` 的断路器状态，确认是否被意外触发
4. 检查 `backend/apps/chat/views.py` 中 SSE 超时配置
5. 查看后端日志：`docker compose logs backend --tail=50`

**验证方法**: 发送消息后应看到 AI 流式响应，而非 "当前无法获取响应" 错误

---

### 问题 2: Admin Dashboard 显示 "请求的页面未找到" (P1)

**现象**: 访问 `/admin/dashboard` 时显示 "请求的页面未找到 — 您访问的页面不存在或已被移除" 和 "返回首页" 按钮。

**截图证据**: `screenshots/uat_v42/S5_03_admin_dashboard.png`

**可能原因**:
- 前端路由配置中 `/admin/dashboard` 路由不存在或路径错误
- RoleGuard 将 admin@ey.com 重定向到了错误的页面
- admin@ey.com 的 `role_level` 字段未设置为 `'admin'`

**修复方向**:
1. 检查前端路由配置（`frontend/src/App.tsx` 或路由文件），确认 `/admin/dashboard` 路由是否存在
2. 检查 RoleGuard 组件的重定向逻辑
3. 确认 admin@ey.com 的数据库角色：
```bash
docker compose exec backend python manage.py shell -c "
from apps.users.models import User
u = User.objects.get(email='admin@ey.com')
print(f'role_level={u.role_level}')
u.role_level = 'admin'
u.save()
print('Updated to admin')
"
```

**验证方法**: 以 admin@ey.com 登录后访问 `/admin/dashboard`，应看到系统健康面板

---

### 问题 3: Knowledge Base Admin 页面无法访问 (P1)

**现象**: 访问 `/admin/knowledge` 时被重定向到 `/chat`

**可能原因**: 与问题 2 相同，RoleGuard 拦截

**修复方向**: 与问题 2 相同，确认 admin 角色权限

**验证方法**: 以 admin@ey.com 登录后访问 `/admin/knowledge`，应看到知识库管理界面

---

### 问题 4: 侧边栏会话不显示 (P2)

**现象**: 发送消息后，侧边栏显示 "暂无会话" 和 "开始新对话"，未出现已发送的会话记录

**可能原因**:
- 会话创建 API 返回了错误
- 侧边栏的会话列表查询 API 未正确返回数据
- 前端状态管理（chatStore）未正确更新会话列表
- SSE 响应失败导致会话未被创建

**修复方向**:
1. 检查浏览器 Network 面板中 `/api/v1/chat/sessions/` 的响应
2. 检查 `frontend/src/store/chatStore.ts` 中会话创建和列表更新逻辑
3. 确认后端 `/api/v1/chat/sessions/` API 正常返回数据

**验证方法**: 发送消息后侧边栏应显示新会话

---

### 问题 5: 字数计数器选择器匹配问题 (P3, 非功能 Bug)

**现象**: 测试脚本通过 `[class*="count"], [class*="counter"], [role="status"]` 选择器未能找到字数计数器元素

**实际情况**: 从截图 `S3_04_char_counter.png` 可以看到，输入框右下角确实显示了 "1/4000" 计数器，说明功能正常

**结论**: 这是测试脚本选择器问题，非应用 Bug。计数器的 DOM class 可能不包含 "count" 或 "counter" 字样

**建议**: 检查字数计数器的实际 DOM class 名称，更新测试脚本选择器

---

## 修复优先级

| 优先级 | 问题 | 影响范围 | 预估工时 |
--------|------|---------|---------|
| P1 | AI 响应失败 | 核心功能不可用 | 1-2h |
| P1 | Admin Dashboard 404 | 管理员无法使用 | 0.5h |
| P1 | Knowledge Base 无法访问 | 管理员无法管理知识库 | 0.5h (与上同源) |
| P2 | 侧边栏会话不显示 | 用户体验受损 | 1h |
| P3 | 字数计数器选择器 | 仅影响自动化测试 | 0.1h |

**总预估工时**: 3-4h

---

## 修复后验证

修复完成后，请运行以下命令重新执行 UAT 测试：
```bash
node tests/uat_final_e2e_v42.mjs
```

预期结果：
- AI 响应正常（流式输出，非 "当前无法获取响应"）
- Admin Dashboard 可访问，显示系统健康面板
- Knowledge Base 管理页面可访问
- 侧边栏显示会话记录
- 通过率 ≥ 85%

---

*生成时间: 2026-06-26 | 来源: UAT 验收测试*
