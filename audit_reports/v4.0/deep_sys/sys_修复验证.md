# V4.0 深层系统修复验证报告

> **修复版本**: V4.0 — deep_sys 修复落地
> **验证日期**: 2026-06-25
> **验证环境**: Docker Compose (5 services: db/pgvector, redis, backend, celery-worker, frontend)
> **验证方法**: 手动交互 + 截图验证
> **引用规则**: `[来源: V4.0/deep_sys_defect_list.md §DEFECT-XXX]`

---

## 1. XSS 防护验证 (DEFECT-002)

### 测试1: img onerror 注入拦截

- **操作**: 在聊天输入框发送 `<img src=x onerror=alert('V4_XSS_Test')>`
- **预期**: 消息气泡渲染为安全文本（`[x]` 或无显示），无 alert 弹窗
- **实际**: ___（待填写）
- **截图**: `fixed_v4_sec_xss_01.png`
  - **强制内容**: 截图必须同时包含"输入框原始恶意代码"和"渲染后的安全结果"；右侧 Console 面板无报错、无弹窗痕迹

### 测试2: javascript: 协议链接拦截

- **操作**: 在聊天输入框发送 `[click me](javascript:alert('V4_XSS_Test'))`
- **预期**: 链接渲染为 `<span>` 纯文本"click me"，不可点击，无 href 属性
- **实际**: ___（待填写）
- **截图**: `fixed_v4_sec_xss_02.png`
  - **强制内容**: 截图A必须同时包含"输入框原始恶意代码"和"渲染后的安全结果"；截图B Console 面板无报错

### 测试3: data: URI SVG 注入拦截

- **操作**: 在聊天输入框发送 `[img](data:image/svg+xml,<svg onload=alert('V4_XSS_Test')>)`
- **预期**: 渲染为 `[img]` 纯文本，不加载恶意 SVG
- **实际**: ___（待填写）
- **截图**: `fixed_v4_sec_xss_03.png`

### 测试4: 正常链接渲染确认

- **操作**: 在聊天输入框发送 `[EY官网](https://www.ey.com)`
- **预期**: 渲染为正常 `<a href="https://www.ey.com" target="_blank" rel="noopener noreferrer">EY官网</a>`，可点击
- **实际**: ___（待填写）
- **截图**: `fixed_v4_sec_xss_04.png`

---

## 2. 状态机并发验证 (DEFECT-006/008)

### 测试1: 跨 Tab session 切换 — stream abort

- **操作**:
  1. 打开 Tab A 和 Tab B，均登录同一账号
  2. 在 Tab A 发送消息 "V4_Race_A"（开始 streaming）
  3. 立即在 Tab B 点击侧栏另一个 session（切换）
- **预期**:
  - Tab A 的 SSE stream 被 abort（BroadcastChannel 通知）
  - Tab A 界面返回 idle 状态，无残留 Loading 指示器
- **实际**: ___（待填写）
- **截图**: `fixed_v4_sec_race_01.png`
  - **强制内容**: 截图必须同时包含"Network 面板显示请求 cancelled"和"界面无残留 Loading"

### 测试2: 跨 Tab session 删除 — stream abort + reset

- **操作**:
  1. 打开 Tab A 和 Tab B
  2. 在 Tab A 发送消息并等待回复完成
  3. 在 Tab B 删除 Tab A 当前活跃的 session
- **预期**:
  - Tab A 收到 BroadcastChannel `session-delete` 事件
  - Tab A 的 stream 被 abort + `resetSession()` 被调用
  - Tab A 返回空白状态（无孤 orphan stream，无 stale messages）
  - Tab A 侧栏 session 列表更新（`loadSessions()` 被调用）
- **实际**: ___（待填写）
- **截图**: `fixed_v4_sec_race_02.png`

### 测试3: 单 Tab 内快速切换验证

- **操作**:
  1. 在单个 Tab 发送消息 "V4_Race_A"
  2. 立即点击侧栏另一个 session（或点击"新建对话"）
  3. 再发送消息 "V4_Race_B"
- **预期**:
  - 第一个 SSE 请求被 AbortController 取消
  - Network 面板显示第一个请求状态 `(cancelled)`
  - 聊天窗口显示 "V4_Race_B" 的正确回复，无残留 Loading
- **实际**: ___（待填写）
- **截图**: `fixed_v4_sec_race_03.png`
  - **强制内容**: 截图必须同时包含"Network Cancelled"和"界面无残留 Loading"

---

## 3. 网络断连反馈验证 (DEFECT-007)

### 测试1: 离线发送 + 红色错误提示

- **操作**:
  1. 打开 Chrome DevTools → Network → 勾选 "Offline"
  2. 发送任意消息
- **预期**:
  - 聊天窗口出现红色 Alert banner，边框加粗（2px solid #ff4d4f）
  - Alert 描述显示"网络连接失败"或 `t('error_network')`
  - Alert 包含 retry 按钮
  - 发送框状态恢复正常（isSendLocked = false）
- **实际**: ___（待填写）
- **截图**: `fixed_v4_sec_net_01.png`
  - **强制内容**: 截图必须同时包含"红色错误提示 Alert"和"发送框恢复正常"

### 测试2: 恢复连接 + retry 成功

- **操作**:
  1. 取消 DevTools "Offline" 勾选
  2. 点击 Alert 上的 retry 按钮
- **预期**:
  - 消息重新发送成功
  - 聊天窗口显示正常回复
  - Alert 消失
- **实际**: ___（待填写）
- **截图**: `fixed_v4_sec_net_02.png`

---

## 4. 后端支撑验证 (DEFECT-001/012/013)

### 测试1: SSE 限流 429 验证

- **操作**: 使用 curl 或脚本在60秒内发送11次 POST `/api/v1/chat/sessions/{id}/send/`
- **预期**: 第11次返回 HTTP 429 `{"error": "Request was throttled."}`
- **实际**: ___（待填写）
- **截图**: （curl 输出截图）`fixed_v4_sec_throttle_01.png`

### 测试2: 500 响应不泄露 str(exc)

- **操作**: 触发一个 500 错误（如 malformed 请求到非 SSE 端点）
- **预期**: 响应 JSON 为 `{"error": "Internal server error"}`，不含 `detail` 字段
- **实际**: ___（待填写）
- **截图**: （curl 输出截图）

### 测试3: SSE error event 不泄露 str(e)

- **操作**: 触发 SSE stream 内部错误（如 session 不存在或 RAG pipeline 异常）
- **预期**: SSE `event: error` 数据为 `{"error": "stream_error"}`，不含异常详情
- **实际**: ___（待填写）
- **截图**: （Network 面板 SSE event 截图）

---

## 验证结论

| DEFECT | 修复状态 | 验证结果 | 截图证据 |
|--------|---------|---------|---------|
| 001 | ✅ 已修复 | ___ | `fixed_v4_sec_throttle_01.png` |
| 002 | ✅ 已修复 | ___ | `fixed_v4_sec_xss_01-04.png` |
| 006 | ✅ 已修复（文档化） | ___ | 代码注释确认 |
| 007 | ✅ 已修复（UI增强） | ___ | `fixed_v4_sec_net_01-02.png` |
| 008 | ✅ 已修复 | ___ | `fixed_v4_sec_race_01-03.png` |
| 012 | ✅ 已修复 | ___ | curl 输出 |
| 013 | ✅ 已修复 | ___ | SSE event 截图 |

**健康评分提升**: 6.3/10 (🟠 Moderate Risk) → ___/10 (预期 7.4 🟡 Good)

**签名**: ___
