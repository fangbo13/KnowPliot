# KnowPilot 高频导航与对话切换可靠性设计

**日期：** 2026-07-22  
**状态：** 已确认（方案 A）  
**目标分支：** `test/pre-launch-audit-2026-07-22`

## 1. 问题与证据

用户在高频切换对话、个人设置及管理页面时会遇到请求报错、刷新失败，且一次页面渲染异常可能让后续路由持续停留在全局错误页。

当前证据链如下：

1. 既有 Docker 日志在 37.55 秒内记录到 39 个普通导航 GET，随后 `/api/v1/admin/organizations/` 首次返回 429；同一时刻另一 worker 仍返回 200。旧配置的 `30/minute` 用户限流与每进程 `LocMemCache` 共同造成混合 200/429。
2. 当前生产构建的 mock-browser 压测在 10.034 秒内执行 66 次 SPA 路由切换，产生 190 个 API GET，峰值 7 个并发；44 个请求最终被取消。现有 `60/10seconds` burst 仍不足以承载该请求风暴，且请求被浏览器取消前通常已到达后端并消耗限流预算。
3. `coalescedGet()` 只合并尚未完成的同键 GET。请求一旦完成，短时间内重新进入同一路由仍会再次访问后端。
4. 部分页面已经使用 `AbortController + sequence`，但 AdminAudit、AdminQuality、GovernancePolicies、ModelProfiles、ScopedUsers 等页面仍各自实现加载生命周期，存在卸载后弹错、旧响应覆盖或重复获取共享参考数据的风险。
5. `ErrorBoundary` 只在用户点击重试时重置；路由改变不会清除 `hasError`。浏览器测试已证明 URL 从故障页切换到 `/profile` 后，视图仍停留在全局错误页。
6. 前端 351 项测试当前全部通过，但测试 stderr 仍包含 jsdom `getComputedStyle(..., pseudoElt)` 错误以及 Router/i18n 警告。测试绿灯不能替代“控制台零未解释 error/warn”的验收。

## 2. 范围

本期只处理与高频导航、对话切换、请求并发及错误恢复直接相关的可靠性问题：

- 普通幂等导航 GET 的请求合并、短时复用和失效；
- 路由请求的取消、序列所有权与错误分类；
- 429/`Retry-After` 的可恢复 UI；
- 路由级 ErrorBoundary 自动恢复；
- 对话列表及消息加载的旧响应隔离；
- 可重复的前端和 Docker 压力测试。

不引入 TanStack Query/SWR，不重写全部数据层，不改变聊天 POST/SSE 的幂等与重放协议，也不通过无限提高后端限流掩盖客户端请求风暴。

## 3. 设计原则

1. **正确性优先。** 旧路由响应不得写入新路由；旧空间或旧用户的响应不得复用。
2. **取消不等于节流。** AbortController 负责资源释放，短时缓存和共享参考数据负责减少已经到达后端的请求。
3. **显式缓存。** 只有调用方明确选择缓存的 GET 才可在完成后复用；默认 `coalescedGet` 仍保持只合并 in-flight 请求。
4. **写后失效。** mutation 成功、空间切换、登录身份变化与退出时必须清理相应缓存。
5. **失败不能伪装成功。** 429、403、404、5xx、超时和网络错误不得落成空数组。
6. **错误边界按路由隔离。** 离开故障路由应自动恢复；同一路由内仍保留显式重试。

## 4. 客户端请求可靠性层

### 4.1 完成态短时缓存

在 `frontend/src/api/client.ts` 的现有逻辑键基础上增加独立的完成态 GET 缓存。缓存键继续包含：HTTP 方法、URL、排序后的 params/headers、responseType、active space 和 auth fingerprint。

`coalescedGet` 新增显式选项：

```ts
interface CoalescedGetOptions {
  preserveSignal?: boolean;
  cacheTtlMs?: number;
}
```

- `cacheTtlMs` 缺省或为 0：只合并 in-flight，不保存完成响应。
- `cacheTtlMs > 0`：成功响应在 TTL 内复用；失败、取消和 401/403/404/429/5xx 永不缓存。
- 每个订阅者仍拥有独立取消语义；取消一个订阅者不能取消仍有订阅者的共享 transport。
- 缓存保存 AxiosResponse 的只读引用；调用方不得修改响应对象。
- 通过最大 128 项的 LRU/过期清理限制内存。插入前和读取时都清除过期项。

### 4.2 TTL 分类

| 数据类别 | TTL | 示例 |
|---|---:|---|
| 跨管理页共享参考数据 | 30 秒 | organizations、business lines、taxonomy options |
| 普通导航列表/概览 | 5 秒 | users、templates、audit page、quality summary、health/metrics |
| 通知未读计数 | 2 秒 | unread-count |
| 对话 session 列表 | 2 秒 | chat sessions；创建、重命名、删除后立即失效 |
| 对话 messages、SSE、下载、敏感状态 | 0 | 永不使用完成态缓存 |

### 4.3 失效接口

请求层提供：

```ts
invalidateGetCache(predicate?: (key: string) => boolean): void
clearInFlightGets(): void
```

- `clearInFlightGets()` 同时清理完成态缓存，用于退出和身份切换。
- 空间切换清理所有包含旧空间指纹的项。
- API mutation 成功后只失效受影响的资源族，例如 chat session mutation 失效 `/chat/sessions/`，组织 mutation 失效 organizations/business-lines 相关键。

## 5. 路由请求所有权

新增一个轻量 `useRouteRequestGuard` hook，统一提供：

- 当前 generation；
- 新一轮加载前终止旧 controller；
- `isCurrent(generation, controller)`；
- unmount 时递增 generation 并 abort；
- abort 静默，429 提供 `retryAfterSeconds`，其他错误按现有分类展示。

优先迁移实际压力路径：AdminAudit、AdminQuality、GovernancePolicies、ModelProfiles、ScopedUsers、ScopedMetrics、ScopedAudit、ScopedQuality。已正确实现 guard 的页面只对齐接口，不做无关重构。

每个页面必须满足：

1. 同一 logical resource 每次有效 mount 最多一个 transport；
2. filter/query 改变会取消旧请求；
3. 只有当前 generation 可以更新 data/loading/error；
4. unmount 后不弹 toast、不写 state；
5. 429 显示明确的重试状态及受限的 `Retry-After`。

## 6. ErrorBoundary 路由恢复

`ErrorBoundary` 增加可选 `resetKey`。`componentDidUpdate` 检测 key 改变时清除 `hasError/error`。App 根边界和 AppLayout 内容边界都使用当前 `location.pathname` 作为 resetKey。

行为契约：

- 同一路由的重渲染不会反复自动重试；
- 用户点击 Retry 仍可原地重新挂载子树；
- 路由改变后自动离开错误页；
- ErrorBoundary 不清理 Zustand、认证或其他 session 的 SSE 状态；
- 每次错误仍记录一次安全的 console/telemetry 事件。

## 7. 后端限流与 Docker 一致性

维持普通认证导航读的 `240/minute` sustained 与 `60/10seconds` burst；先减少客户端请求，不把 burst 任意提高。生产/Compose 必须使用 Redis cache，不能使用 per-process LocMemCache。

Docker readiness 必须验证：

- 两个或更多 web worker 使用相同 Redis rate-limit store；
- 相同用户和相同历史在不同 worker 上得到一致限流决定；
- 429 响应包含稳定 `code=rate_limited` 和整数 `Retry-After`；
- 登录、聊天 mutation、访问码和治理 mutation 继续使用各自更严格的限流。

## 8. 测试与压力验收

### 8.1 TDD 回归测试

必须先看到以下测试在修复前失败：

1. 完成态缓存 TTL 内只发一个 transport，过期后重新请求；错误/429 不缓存；身份或空间变化不复用。
2. mutation/显式 invalidation 后下一次 GET 访问后端。
3. 路由 A 的延迟响应不能覆盖路由 B；unmount 后没有 toast/state write。
4. ErrorBoundary 在 `resetKey` 改变后离开 fallback，同 key 不自动循环重试。
5. chat session 列表快速重复加载满足序列所有权并静默处理 abort。
6. 强制 429 显示 retry guidance，不显示空成功。

### 8.2 浏览器压力测试

目标流程：`/chat -> /profile -> /admin/dashboard -> codes -> announcements -> users -> business-lines -> templates -> quality -> audit -> knowledge -> /chat`。

两种节奏各执行 10 轮：

- 正常：每次停留 250ms；
- 快速：每次停留 50–100ms，并为 API 注入 25–125ms 延迟。

通过条件：

- 0 个未解释 console error/pageerror/framework overlay；
- 取消请求只表现为预期 `ERR_ABORTED`，不触发 toast 或 ErrorBoundary；
- 10 秒窗口内普通导航 GET 不超过 60；
- 同一共享参考资源在 TTL 内最多一个成功 transport；
- 最终 URL、页面标题和主内容与最后一次导航一致；
- 注入 429 时出现 Retry-After 指引，等待后显式重试成功；
- 注入一次渲染错误后切换路由可自动恢复。

### 8.3 Docker 压力测试

提供可重复脚本，至少覆盖：

1. 单用户快速导航：复放上述 API 序列，验证无意外 429；
2. 100 虚拟用户并发导航 60 秒：记录吞吐、p50/p95/p99、错误率和 429 分类；
3. 双 worker 共享 Redis：同一用户并发历史得到一致决定；
4. 并发对话切换：messages/session 列表无旧响应覆盖；聊天 POST 不自动重试。

默认通过阈值：HTTP 5xx 为 0；非预期 429 为 0；导航 GET p95 小于 1 秒（本机 Compose）；前端 console/pageerror 为 0。外部 LLM 延迟不计入导航 GET 指标。

## 9. 可观测性

压力脚本输出机器可读 JSON，包括测试版本、commit、场景、总请求、每 endpoint 次数、峰值并发、状态码分布、p50/p95/p99、console errors、page errors 和最终路由。日志不得包含 token、密码、访问码、聊天内容或完整用户标识。

## 10. 回滚

- 完成态缓存可通过将所有 `cacheTtlMs` 设为 0 回退，不影响 in-flight coalescing。
- route guard 可逐页回退，不改变 API wire contract。
- ErrorBoundary resetKey 可独立回退为手动 Retry。
- 后端限流数值不在本次无证据调整，避免客户端回滚时暴露失控流量。

## 11. 完成定义

只有在以下全部成立时才视为完成：

- spec 对应的单元/组件/构建测试通过且输出中无未解释 error；
- 生产构建及 bundle budget 通过；
- 浏览器两种节奏压力测试通过；
- Docker 单用户、100 用户和双 worker Redis 测试通过；
- 工作树 diff 仅包含本期明确文件且未覆盖既有用户改动；
- 最终报告明确区分已验证事实、环境限制和剩余风险。
