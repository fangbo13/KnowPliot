# KnowPilot 内测 SPEC v3 变更 Delta

> 日期：2026-07-18（2026-07-19 provider entitlement 修订）
> 基线：`docs/specs/2026-07-16-knowpilot-optimization-spec.md` v2
> 新规范：同文件 v3（2026-07-18 internal-beta normative rewrite）
> 目标实现基线：`fix/v1.74.1-acceptance-bugs`，commit `82231f5`
> 状态：仅 SPEC 变更；所有 v3 业务实现与发布证据均为 `pending`

## 1. 范围与优先级

本 delta 只描述规范变化，不代表代码已经实现。v3 只覆盖内测问题清单
一.1--7、二.A--J，以及交接要求锁定的 workspace 永久删除契约。未被显式
改写的 v2 条款继续有效，尤其是：

- §4 ChatTurn/SSE 的 durable identity、幂等、恢复与安全 phase；
- §6 四级能力矩阵、scope 隔离、向上授权否定；
- §11 SSE v1 与 legacy navigation/route adapter 的一版本兼容期；adapter
  始终消费服务端 exact capabilities，不保留 role-array、合成 owner 或隐式 chat 授权；
- 业务/审计证据不因账号或 workspace 删除而无控制级联消失；
- 审计、幂等、并发保护和 PostgreSQL 真实性要求。

发生冲突时，主 SPEC §19 明确列出的 v3 语义优先。ownership-continuity
SPEC 仍是 canonical owner、转让、离职承接的前置规范；v3 与其共享服务原语，
不复制或改名其聚合。

## 2. 已重写的既有章节

| 章节 | 变更摘要 |
|---|---|
| 顶部状态 | 版本升为 2026-07-18 v3；把 v2 测试数字降格为历史证据，禁止据此宣称 v3 已实现。 |
| §3 不变量 | 新增 fast 默认、deep opt-in、thinking 独立默认 off；浏览器不得提交模型/预算权威；platform/governance 不得合成 owner/chat；审批与删除共享 governed-action 原语。 |
| §4 ChatTurn | 请求新增 `thinking_enabled`；持久化 requested/effective mode、thinking、budget、fallback 与 `thinking_snapshot_known`；幂等摘要纳入 mode/thinking；平台身份无 membership 时不得发送或恢复聊天。 |
| §5 SSE | `meta` 必须返回 effective mode/model/thinking/budget/fallback；仍不得传原始 reasoning。 |
| §6 能力矩阵 | 新增普通账号 `workspace.creation.request`；新增显式平台创建审批/Knowledge metadata 权限、owner 永久删除权限和独立 `chat.thinking`；禁止把平台/治理 scope 合成 workspace owner。 |
| §7 模型策略 | 完整改写为 `fast=qwen3.6-flash`、`deep=qwen3.7-plus`；thinking 与 deep 解耦、两档默认 off；规定 capability、双端 flag、budget、readiness、fallback、四组合测试。 |
| §10 验收 | 增加创建审批、永久删除、taxonomy/discovery、通知/邀请、Knowledge/Templates、modal/navigation、PostgreSQL 并发与真实浏览器验收。 |
| §11 兼容/回滚 | 保留 SSE v1 与 legacy navigation/route adapter；重新定义 `DEEP_ANSWER_MODE` 仅控制 deep，新增 `THINKING_MODE`；既有 `POST /spaces/` 在审批开关启用后仅作为一版本 request adapter 返回 `202`，human caller 不再直接建空间；保留已签发 legacy direct invitation code，但新 UI 不再混称访问码。 |
| §12 API | 扩展 chat effective snapshot；补 governed create/delete、discovery/taxonomy、access/invitation/notification/member、platform Knowledge API；登录采用 safe `next -> default_console -> /chat`。 |
| §13 迁移 | 在 ownership 前置之后加入 thinking、template revision、taxonomy/usage、creation policy、governed request/locator/operation-idempotency、access/invitation、actionable notification、retention FK、purge job/checkpoint/tombstone 迁移；补 partial unique、deferred typed-detail/taxonomy/owner trigger、purge guard、`select_for_update(of=("self",))` 的 PostgreSQL 验证。 |
| §14 交互 | 补创建申请/审批、发现页、访问与邀请、成员 CRUD、archive/delete、Knowledge/Templates、route-owned loading、可关闭 modal；模型信息只读显示。 |
| §15 性能/隐私 | 给出 chunk 预算、route cancellation/429、分布式限流、隐私字段、配置 readiness、QA 测试账号治理、测试 profile 和命名约束。 |
| §16--§17 | 把已有实现证据明确限定为 v2 历史证据；新增 v3 PostgreSQL/provider/browser/data-hygiene gate，全部保持 pending。 |
| §18 决策/路线 | 写入已决 product policy；路线从“只剩部署”改为“实现、验证、部署均未由文档完成”。 |

## 3. 新增章节

| 新章节 | 新规范内容 |
|---|---|
| §19 | v3 优先级、目标基线、问题 ID 与一.1--7/二.A--J 落点。 |
| §20 | `GovernedActionRequest` 公共 envelope、typed detail、`WorkspaceLocatorReservation`、per-operation `WriteIdempotencyRecord`、事务内 outbox、impact、审计、明确状态机、全局 lock order、canonical owner 数据库约束。 |
| §21 | 内测建空间 platform-review 流；未来基于权威 SSO 的 business-line -> org -> platform 就近路由；职责分离与 atomic approval。 |
| §22 | owner-only archive -> impact -> typed locator -> retention -> purge；409 blockers、逐模型固定 FK/保留矩阵、墓碑、`WorkspacePurgeJob`/checkpoint manifest saga、PostgreSQL delete trigger。 |
| §23 | `WorkGroup`/`OfficeLocation` controlled taxonomy、与 org/business_line 关系、搜索授权顺序、frequent/popular 隐私排名和 PG 索引/trigger。 |
| §24 | 访问码与 targeted invitation 的语义边界、通知原子 action、成员生命周期、owner 保护、并发与 secret 处理。 |
| §25 | Platform Knowledge metadata 边界、Scenario Templates“克隆起点”说明，以及 A--J 的逐项行为/证据闭环。 |
| §26 | 第 6 条 BUG 的只读取证边界、精确路径、两条独立根因、modal 与多 worker 导航/限流回归契约。 |
| §27 | 每条需求对应 model/migration、API/capability、frontend/test 的发布证据矩阵。 |

## 4. 与 v2/现状的冲突及处理

### C-01 deep 与 thinking 耦合

- 旧语义：deep 隐含 thinking on，fast 隐含 off。
- 新语义：deep 只表示更强模型；thinking 是独立偏好，fast/deep 均可开，且
  每个新问题默认 off。
- 处理：v3 §7 覆盖旧 §7；Turn 同时保存 requested/effective 两组字段。迁移前历史
  Turn 使用 `thinking_snapshot_known=false` 与 `legacy_thinking_unknown`，不把 false
  storage sentinel 伪装成历史事实；迁移后省略 thinking 的 v1 请求是可证明的 known off。
- 理由：落实锁定产品决策，同时保留服务器策略权威和幂等重放真实性。

### C-02 fast 模型由环境或旧 profile 漂移

- 旧语义/现状：`qwen-plus`、未开通的 `qwen3.7-Flash` 与 ambient `.env` 可产生不同 fast。
- 新语义：经 2026-07-19 provider entitlement 实测，fast 只能是精确 `qwen3.6-flash`，deep 只能是精确
  `qwen3.7-plus`；不一致时 readiness degraded，新 Turn 在创建前返回
  `503 model_policy_not_ready`。
- 理由：不能用 silent fallback 破坏固定两档和 Turn 证据。

### C-03 platform/governance 隐式 chat/owner

- 旧冲突：v2 个别恢复/能力描述允许平台 scope 产生 `chat.ask`，现有 resolver
  还可能为选中空间合成 owner。
- 新语义：所有 workspace chat/history/source 都要求显式有效 membership（包括受限
  guest membership）；
  platform metadata 权限不是内容权限，也没有 self-join。ownership 强制交接若把
  platform 用户设为 owner，必须由不同的有权 actor 执行；force actor 不得把自己
  设为 target，成功后聊天依据是显式 owner membership，不是 platform role。
- 理由：保持 §6 scope 隔离和向上授权否定，避免平台职责意外成为租户内容读取。

### C-04 访问码与邀请码混用

- 旧语义：`InviteCode` 在 `/spaces/join/` 直接生成 membership，UI 称访问码。
- 新语义：访问码只生成 owner-reviewed `SpaceAccessRequest`；targeted invitation
  由目标用户 accept 后直接生效，无第二次 owner 审批。
- 兼容：旧 direct `InviteCode` 保留一版本并改称 legacy invitation code；新 UI
  不得创建或称其为访问码。

### C-05 普通用户直接建空间

- 旧语义：持有较高治理能力可直接 `POST /spaces/`，普通账号没有申请流。
- 新语义：普通 active account 只有 request entitlement；内测统一由另一位
  platform admin 审批。既有 `POST /spaces/` 只保留为一版本路由 adapter：审批功能
  开启时转成同一 creation request 并返回 `202`，任何 human caller 都不能直接创建。
  只有 provisioning worker 可执行一个已经审批完成的 request，且不能提交、自批、
  成为 owner 或绕过 audit/outbox；关闭审批开关也不会恢复不安全的 direct-create。

### C-06 workspace 删除依赖 ORM CASCADE

- 旧风险：space 下多类 FK 可无边界级联，ownership `PROTECT`、文件/索引和保留
  证据会造成部分删除或证据丢失。
- 新语义：owner-only、archive-first、影响版本、明确 blockers、30 天 archive +
  7 天确认后最短等待、manifest-driven 显式逻辑级联、retained evidence detach、
  永久 tombstone、PG `BEFORE DELETE` fail-closed trigger。
- 理由：同时满足用户确认、业务/审计保留、外部存储幂等和真实并发。

### C-07 创建/删除是否复用 `SpaceAccessRequest`

- 处理：不复用该表。创建和删除使用 common governed envelope + typed details；
  与 ownership/offboarding 共享 lock、impact、idempotency、audit、outbox 服务。
- 理由：三种聚合的状态、授权主体和数据约束不同，硬塞进 access request 会
  产生无效字段和越权分支。

### C-08 ownership lock order/owner mirror 只靠服务

- 新语义：§20.3 给出所有共享 workflow 的唯一全局锁序，并强制每次使用
  `select_for_update(of=("self",))`；增加一个 active owner mirror partial unique
  和 commit-time deferred owner/mirror trigger。
- 理由：消除不同服务锁序歧义，且让真实 PostgreSQL 阻止绕过 service 的双 owner。

### C-09 `CAPABILITY_NAV` 定义但未接线

- 新语义：它只控制 capability bootstrap 的 `navigation_mode` 和 route availability；
  不控制任何权限。前后端不配对时 fail closed，不双重 mount/fetch。
- 兼容：legacy navigation 保留一版本，后端 exact authorization 始终开启。

### C-10 登录固定 `/chat`

- 新语义：经过安全同源校验的 `next` 优先，其次服务端 `default_console`，最后
  `/chat`；禁止前端按 role 名硬编码和 open redirect。

### C-11 member CRUD 可把用户设为 owner

- 新语义：邀请、访问审批、member CRUD 均只允许非 owner 角色；canonical owner
  mirror 在成员页只读，所有 owner 变化走 ownership transfer。
- 理由：保持 ownership-continuity 的单一写入口和并发不变量。

### C-12 平台 Knowledge 与 workspace 内容权限

- 新语义：`platform.knowledge.read` 只读跨空间 metadata，并显示空间归属；预览、
  下载、聊天、引用源仍需该空间 membership 和对应 capability。

### C-13 模型信息“显示”与“选择”的边界

- 新语义：前端可从 server `meta` 只读展示 requested/effective mode、model ID、
  thinking、适用时的 budget 和 fallback；不得提供 model/profile/budget selector，
  也不得把这些字段回传为权威。

### C-14 `OwnershipTransfer.space=PROTECT` 与永久删除

- 旧 ownership 契约：transfer 对 space 使用 `PROTECT`，能避免历史被误删，但也会让
  任何有完成转让历史的 workspace 永远无法按新流程物理清除。
- 新删除专用语义：启用永久删除前，先为每条 transfer 回填不可变 space/org/locator
  snapshot，再把 **space FK** 改为 nullable `SET_NULL`；non-terminal transfer 仍是
  409 blocker，completed transfer 作为业务/审计证据脱离 live space 后继续保留。
- 防绕过：KnowledgeSpace purge guard、retention、manifest 和 executing governed
  request 仍阻止直接 ORM/Admin 删除；actor/from/to owner FK 的保留语义不变。

## 5. 数据库与兼容性 delta

新增的规范迁移依赖顺序是：ownership-continuity 前置完成后，先补 owner partial
unique/deferred mirror trigger 与 test-principal metadata，再依次添加
independent-thinking snapshot、immutable template revision、controlled taxonomy/
daily usage buckets、revisioned creation policy、governed request + typed details、
single-namespace locator、per-operation idempotency、hashed access code/targeted
invitation、actionable notifications、逐应用 retention FK、purge job/checkpoints、
workspace tombstone 和最终 purge guard。实际 migration 编号若在分支上冲突可重编号，
但不得改变依赖图、约束或 rollout 顺序。

以下必须在 PostgreSQL 验证，SQLite 不能代替：

- partial unique：每空间一个 active owner mirror、一个 live deletion request、每 policy
  scope 一个 active revision、access/invitation pending uniqueness；
- deferred trigger：canonical owner/mirror、typed envelope/detail shape、taxonomy 跨表
  一致性与所有 parent/through-table 变更事件；
- `WorkspaceLocatorReservation` 的单一 org/code namespace 与不可复用 tombstone；
- `WriteIdempotencyRecord` 的 `(actor, operation, key)` 唯一、digest 冲突和原响应重放；
- purge guard、registered model/FK matrix、`WorkspacePurgeJob` fenced lease 与每 store
  checkpoint/manifest 的失败恢复；
- approve/reject/cancel/confirm/retry/join/member/notification/ownership/offboarding/delete
  的真实并发；
- 所有相关 row lock 使用 `select_for_update(of=("self",))`，不锁 nullable join；
- 业务状态、audit 与 outbox row 同一事务提交；`on_commit` 只唤醒 dispatcher，不创建
  授权事实或 outbox 记录。

SSE v1、legacy navigation/route adapter、既有 `POST /spaces/` request adapter 和
已签发 legacy invitation code 均按 §11 保留一版本。旧 route 不等于旧授权：后端
exact capability enforcement 始终生效，且 route adapter 不能恢复 human direct-create。
移除仍需用量证据、回滚演练和单独批准。本 delta 没有批准删除任何兼容回退。

## 6. 第 6 条 BUG 的 delta

- modal：不是 `onCancel` 缺失；确定根因是自定义 `transitionName="fade"` 没有
  对应 CSS/transition event/deadline，导致 `afterClose`、Portal、scroll lock 不释放；
  提交时 `confirmLoading` 又会拦截所有关闭路径。因登录会写 DB，本次未伪造实时
  点击复现，依据为源码、依赖实现、当前构建产物与 blame 的完整静态链。
- navigation：现有 Docker 日志直接重现 legacy admin 路由快速切换后 429；直接
  根因是全局 `30/minute` 被页面 2--5 个并发且重复 GET 耗尽，2-worker
  `LocMemCache` 又让同一用户同秒随机混合 200/429；前端没有 429、Retry-After、
  coalescing、abort/sequence 通用契约，并把部分失败伪装为空数组。
- 两者不是同一根因。§26 固定了可复核的时间、路径、首个 429、证据边界以及
  built-Chromium/多 worker 回归矩阵。

## 7. 编写环境与非变更声明

交接指定目标分支为 `fix/v1.74.1-acceptance-bugs`/`82231f5`；编写时工作树实际
处于 `codex/ownership-continuity` 且已有用户未提交内容。为避免覆盖用户工作，本次
没有切分支、reset、stash 或改写这些内容；目标 commit 仍作为规范事实基线，其他
分支上的 ownership 代码只可作为非基线观察，不能记为已实现。

本次允许的产出只有：主 SPEC、本 delta、开放问题决策日志。未编写业务代码，未改
数据库、依赖、环境变量、Docker 生命周期或运行配置；第 6 条调查仅读取现有源码、
构建产物、设置与日志。
