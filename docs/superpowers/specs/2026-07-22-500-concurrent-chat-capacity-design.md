# 500 路并发聊天容量优化设计

**日期：** 2026-07-22
**状态：** 待用户书面确认
**目标分支：** `test/pre-launch-audit-2026-07-22`

## 1. 目标与验收口径

本轮目标是让 KnowPilot 在隔离、可横向扩容的容器架构中承受 **500 名用户同时发送聊天请求，并同时保持 AI 生成流**。500 是持续目标，不只是瞬时接收 500 个 HTTP 请求。

由于尚未选定生产硬件，本轮先建立可重复的单副本容量模型，再计算满足 500 路目标所需的副本数。平台自身使用仿真模型验证 500 路完整生成；真实模型仅做 20 路单轮抽样，500 路真实模型能力仍取决于供应商配额。

### 1.1 稳态门槛

- 500 个不同用户在 60 秒内完成发送爬升，并保持 500 条生成流 30 分钟；
- 发送接纳接口 p95 不高于 800ms，普通读取 API p95 不高于 500ms、p99 不高于 1.5s；
- 仿真模型首个应用事件 p95 不高于 1.5s，成功终态比例不低于 99%；
- 非预期 HTTP 5xx、网络错误、重复生成、事件丢失合计不高于 0.1%；
- SSE 断线重连不得重复渲染或丢失已确认事件；实例重启后 Turn 必须收敛到完成、取消或可重试失败；
- PostgreSQL 连接、Redis 内存、生成队列和进程内存均保持有界，不允许以无限队列换取表面成功。

### 1.2 过载门槛

1000 路发送作为两倍突刺，持续 2 分钟。系统可以拒绝超过已配置容量的请求，但必须返回 `429 generation_capacity_reached` 和稳定的 `Retry-After`，不得出现错误风暴、服务雪崩或超过 60 秒的恢复时间。

## 2. 当前瓶颈

当前 Docker 后端由 2 个 Gunicorn worker、每个 8 个 gthread 线程提供服务，理论上只能同时承载 16 条长期 SSE。`send_message` 在请求线程中完成数据库读写、RAG 检索、外部模型调用和 SSE 输出，因此浏览器断开、滚动发布和慢模型都会长期占用 Web 容量。

其他已确认的容量限制包括：PostgreSQL `max_connections=100` 且没有 PgBouncer；共享 `httpx.Client` 最大连接数为 20；Redis 同时承担缓存、限流、Celery broker、聊天租约和事件重放且没有内存边界；生成任务与文档导入共用 Celery 队列；缺少平台级 Prometheus 指标和可复现的混合负载工具。

## 3. 选定架构

### 3.1 服务拆分

采用“快速接纳 + 异步生成 + 独立 SSE 网关”架构：

1. **Web API** 只负责鉴权、幂等创建 Turn、容量预留和 Celery 入队，立即返回 `202`；
2. **生成 worker** 从专用 `chat_generation` 队列取任务，执行现有 RAG/模型逻辑并把事件写入 Redis Stream；
3. **SSE 网关** 以 ASGI 运行，只负责鉴权、重放和阻塞读取 Redis Stream，不执行模型调用；
4. **PostgreSQL** 通过 PgBouncer transaction pooling 提供短连接，SSE 生命周期不绑定数据库连接；
5. **Redis broker** 与 **Redis events/cache** 分离，broker 使用 `noeviction`，事件实例使用显式内存上限和 `volatile-lru`。

Web、SSE 网关和生成 worker 使用同一代码镜像，但以不同启动命令和健康检查独立扩容。文档导入继续使用原 `default` 队列，不能占用聊天生成槽位。

### 3.2 生成并发与背压

默认配置：

- `CHAT_GENERATION_TARGET_ACTIVE=500`；
- `CHAT_GENERATION_MAX_OUTSTANDING=625`；
- `CHAT_GENERATION_RESERVATION_TTL_SECONDS=180`；
- 单个生成 worker 初始采用 Celery threads pool、并发 25；实际生产副本数使用压测得到的安全并发计算；
- 单 worker 的模型 HTTP 池默认 32 个连接、16 个 keep-alive 连接，且不得小于 worker 并发；
- 单 Turn 总生成期限 90 秒，外部连接/读取采用更短的分阶段超时。

容量预留使用 Redis 有序集合和 Lua 原子脚本。成员是 `turn_id`，score 是过期时间；每 30 秒续租，任务进入终态时删除。接纳前清理过期成员并检查总数，达到 625 时拒绝新 Turn。后台清理任务同时根据数据库终态修复泄漏预留。

500 路是目标活跃生成数；625 提供 25% 排队和恢复余量。队列等待 p95 超过 5 秒时触发告警，不能自动扩大未完成上限。

### 3.3 事件存储

v3 使用独立 Redis Stream 键 `chat:v3:turn:{turn_id}:events`。Lua 脚本递增现有整数序号，并以 `{sequence}-0` 作为 Redis Stream ID，因此 SSE `Last-Event-ID` 继续是整数。

每个事件流：

- 保留 15 分钟；
- 最多保留 4096 条记录；
- 终态事件落库前后均可重放；
- `answer_delta` 在 worker 端按“最多 50ms 或 256 字符”批量写入，避免每 token 一次 Redis 命令；
- 只允许既有安全事件名，继续禁止 prompt、异常详情、原始 reasoning/CoT 等字段。

现有 v2 ZSET 事件存储保持不变，避免滚动发布期间破坏正在运行的 v1/v2 Turn。

## 4. v3 公共接口

### 4.1 接纳生成

`POST /api/v1/chat/sessions/{session_id}/send/` 和重新生成端点继续复用原 URL。v3 请求设置：

```json
{
  "content": "...",
  "client_request_id": "uuid",
  "answer_mode": "fast",
  "thinking_enabled": false,
  "protocol_version": 3
}
```

成功返回 `202 Accepted`，`Location` 指向状态端点：

```json
{
  "turn_id": "uuid",
  "session_id": "uuid",
  "client_request_id": "uuid",
  "status": "accepted",
  "events_url": "/api/v1/chat/turns/{turn_id}/events/",
  "status_url": "/api/v1/chat/turns/{turn_id}/",
  "cancel_url": "/api/v1/chat/turns/{turn_id}/cancel/"
}
```

数据库事务提交后通过 `transaction.on_commit` 入队。入队失败释放容量并把 Turn 标记为可重试的 `queue_unavailable`。相同 `client_request_id` 的重复请求始终复用同一 Turn，不得重复写用户消息或重复调用模型。

容量满返回：

```json
{
  "code": "generation_capacity_reached",
  "retryable": true,
  "retry_after_seconds": 5
}
```

响应状态为 `429`，同时携带 `Retry-After: 5`。

### 4.2 实时事件

`GET /api/v1/chat/turns/{turn_id}/events/?after={sequence}` 在 v3 Turn 上提供实时 SSE。它先重放大于 cursor 的事件，再通过 Redis 阻塞读取等待新事件；每 15 秒发送 SSE comment 心跳，每 30 秒重新验证当前空间权限。权限撤销时关闭连接，后续状态/重放请求返回现有非泄漏式拒绝结果。

v3 复用事件名 `meta`、`phase`、`answer_delta`、`citations`、`quality`、`usage`、`done`、`error`。`meta.protocol_version` 为 3，并允许 `phase: queued`。终态后网关发送完整终态事件并关闭连接。

### 4.3 显式取消

新增 `POST /api/v1/chat/turns/{turn_id}/cancel/`。拥有 Turn 且仍有当前空间权限的用户可取消；重复取消是幂等的。接口返回 `202 {"status":"cancelling"}`。worker 在检索前、模型流每次迭代及保存前检查取消标记，最终写入 `cancelled` 并发出 `error` 事件：

```json
{"code":"cancelled","retryable":false}
```

浏览器导航、刷新或网络断开只取消订阅，不取消后台生成；只有显式停止操作才调用 cancel。

## 5. 任务可靠性

生成逻辑从 `views.py` 的生成器抽成以 `turn_id` 为输入的可重入服务。Celery 任务使用 late ack、worker-loss 重投和最多 3 次指数退避。Redis 会话租约仍保证同一 session 单写；任务重投时若原租约仍有效则延迟重试，租约不存在且 Turn 未终态时才接管。

任务在每次状态转换前重新读取 Turn，不覆盖并发完成或取消。所有终态路径都释放会话租约、容量预留和数据库连接。生成 worker 使用 `CONN_MAX_AGE=0`，并在长时间外部等待前关闭闲置数据库连接。

Redis broker 故障、事件存储故障和数据库故障均失败关闭：不允许在无法证明幂等和单写时继续调用模型。事件写入失败时 Turn 进入可重试失败，不能生成一个客户端永远无法恢复的“幽灵回答”。

## 6. 前端行为与兼容

前端增加 `VITE_CHAT_STREAM_V3`，默认关闭。开启后：

1. 发送 v3 请求并接收 `202`；
2. 将本地消息绑定到 `turn_id`，随后用带 Authorization 的 `fetch` 连接 `events_url`；
3. 记录最高确认事件 ID，断线按 1、2、4、8 秒退避重连，最高 8 秒；
4. 路由切换只分离当前视图，Turn 管理器继续持有后台状态；返回会话时按 cursor 恢复；
5. 用户点击停止时调用 cancel；
6. `429` 展示服务繁忙和可重试倒计时，不自动形成请求风暴。

v1/v2 保留一个发布周期。上线顺序是：后端 v3 关闭开关部署、SSE 网关/worker 就绪、内部用户 5%、25%、50%、100% 放量。任一核心 SLO 连续 5 分钟失败即关闭前端 v3 开关，v2 行为不受影响。

## 7. 数据库、Redis 与查询优化

- 引入 PgBouncer transaction pooling；Django 设置 `CONN_MAX_AGE=0` 和 `DISABLE_SERVER_SIDE_CURSORS=True`；连接池总量不得超过 PostgreSQL `max_connections` 的 80%；
- 压测数据包含 5000 用户、每用户 20 个会话、每会话 40 条消息、10 个空间及足够的通知/审计记录；
- 对会话列表、消息分页、Turn 状态、权限检查和通知未读查询采集 `EXPLAIN (ANALYZE, BUFFERS)`；只有出现顺序扫描且目标查询 p95 超标时才添加复合索引；
- Redis broker 使用独立实例和 `noeviction`；events/cache Redis 配置明确内存上限、`volatile-lru`、15 分钟事件 TTL，并监控 blocked clients、evictions、connected clients 和命令延迟；
- RBAC/空间参考数据继续使用短 TTL 缓存，用户可变状态不得跨用户共享缓存。

## 8. 可观测性

增加仅内部网络可访问的 Prometheus 指标端点，至少记录：

- HTTP 请求量、状态和按路由延迟；
- 当前 SSE 连接数、重连数、心跳关闭数；
- 生成 outstanding/queued/active、排队时间、总时长、首事件和首答案延迟；
- provider 请求量、429、超时、熔断和连接池等待；
- Turn 完成、失败、取消、重投、重复抑制和租约丢失；
- PostgreSQL/PgBouncer 连接与等待、Redis 内存/逐出/阻塞客户端、Celery 队列深度；
- 每个容器的 CPU、RSS、网络和重启次数。

日志必须包含安全的 `turn_id`、`session_id`、阶段和错误码，不记录 token、prompt、原始模型响应、凭据或原始 reasoning。

## 9. 隔离压测设计

新增独立 Compose 压测栈，使用独立 PostgreSQL 卷、独立 broker/events Redis、PgBouncer、仿真模型服务和固定资源限制。所有用户、空间和文档均为合成数据；测试结束删除栈和临时卷，不接触当前开发数据库。

压测工具分工：

- Grafana k6 负责登录外的普通 REST 混合流量、发送接纳和固定到达率场景；
- Node SSE runner 负责持有 500 条流、解析事件序号、测量首事件/首答案/完成延迟以及断线恢复；
- Prometheus 采集服务指标，测试协调器输出机器可读 JSON 和 Markdown 报告。

执行顺序：

1. **烟雾**：10 用户、2 条流、2 分钟；
2. **基线**：记录优化前单实例在 25/50/100 路流的饱和点；
3. **阶梯**：50→100→200→300→400→500 路，每档 5 分钟，找到第一个 SLO 失败点；
4. **目标稳态**：500 路流和配套读取流量保持 30 分钟；
5. **两倍突刺**：从 500 突增至 1000，保持 2 分钟，验证 429 与 60 秒恢复；
6. **故障注入**：稳态期间依次重启一个 Web、SSE 网关和生成 worker，验证重连、重投及无重复生成；
7. **真实模型抽样**：显式设置 `ENABLE_REAL_PROVIDER_STRESS=1` 后，20 个用户各发送一轮，输入不超过 300 字符、输出上限 512 token；不得自动扩大调用量。

容量报告必须给出每类副本的安全并发、CPU/内存、数据库连接、Redis 内存、provider 连接占用和 30% 余量后的副本公式。例如，若单生成 worker 在 SLO 内安全承载 `C` 路，则推荐副本数为 `ceil(500 / (C * 0.7))`。在生产预演硬件完成同一套测试前，不宣称真实部署已经获得 500 路容量认证。

## 10. 测试与交付门槛

- 单元测试覆盖容量 Lua 脚本、事件顺序/TTL/批量、任务重投、取消、幂等和错误清理；
- PostgreSQL + Redis 集成测试覆盖多 worker 竞争、断线重放、租约接管、队列失败和 PgBouncer 兼容；
- 前端测试覆盖 202 接纳、事件恢复、路由切换、显式取消、429 倒计时和 v2 回退；
- 完整前后端回归、类型检查、生产构建和迁移一致性必须通过；
- 目标稳态、过载突刺和故障注入均满足第 1 节门槛，且报告不含凭据或用户数据；
- 20 路真实模型抽样单独报告 provider 429、首答案延迟和费用估算，不把它伪装成 500 路供应商认证。

## 11. 非目标

本轮不删除 v1/v2，不重写整个 RAG 为原生 async，不引入 Kubernetes，不承诺未提供配额的外部模型可同时处理 500 路，也不通过提高 PostgreSQL `max_connections`、取消限流或无限增加 Redis 内存来掩盖架构瓶颈。

## 12. 已选取的默认值

- 硬目标：500 条同时生成流；
- 过载突刺：1000 条，允许对超额部分返回 429；
- 协议：新增 v3 灰度，v1/v2 保留一个发布周期；
- 架构：异步 Turn + 专用生成队列 + Redis Stream + ASGI SSE 网关；
- 测试：隔离 Compose 栈，仿真 500 路，真实模型最多 20 路单轮；
- 资源结论：先测单副本容量模型，再计算生产规格，不以当前 Docker Desktop 结果直接认证生产硬件。
