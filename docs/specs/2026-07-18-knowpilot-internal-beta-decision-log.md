# KnowPilot 内测 SPEC v3 开放问题决策日志

> 日期：2026-07-18（2026-07-19 D-002 修订）
> 状态：Accepted for SPEC；implementation pending
> 适用基线：`fix/v1.74.1-acceptance-bugs` / `82231f5`
> 主规范：`docs/specs/2026-07-16-knowpilot-optimization-spec.md` v3

本日志记录交接中仍开放的 1、3、4、5、6，并记录 2026-07-19 对问题 2 的
provider entitlement 修订。thinking 解耦结论不变，模型 ID 以 D-002 为准。

## D-002（问题 2 修订）：固定为已开通的 fast/deep 模型

**决策**：内测 fast 固定为精确 `qwen3.6-flash`，deep 固定为精确
`qwen3.7-plus`；thinking 仍与档位解耦且每个新问题默认 off。此前写入主 SPEC 的
`qwen3.7-Flash` 未在当前 DashScope 账户开通，不得作为可用模型、fallback 或通过的
provider 证据。

**依据**：2026-07-19 已在同一 DashScope entitlement 下验证：
`qwen3.6-flash` 可返回流式答案，`qwen3.7-plus` 已开通，`qwen3.7-Flash` 未开通。
固定模型的目的是真实、可审计的服务器权威，不是坚持一个部署账户无法调用的名称。

**后果**：seed、`ModelProfile`、`GovernancePolicy`、兼容 alias、readiness、Turn
effective snapshot、provider payload 与四组合测试必须一致使用
`qwen3.6-flash`/`qwen3.7-plus`。任何 `qwen-plus`、`qwen3.7-Flash` 或其他 fast
绑定继续 fail closed 为 `503 model_policy_not_ready`，不得 silent fallback。

## D-001（开放问题 1）：内测建空间采用超管审批

**决策**：内测采用 platform admin 审批，不采用信任制。规范角色代码是
`platform_admin`；“super admin/超管”只是产品显示别名。active 注册账号只
获得 `workspace.creation.request`，不能直接创建。另一名持
`platform.workspace_creation_requests.manage` 的 platform admin 完成影响预检和
approve/reject；申请人不得自批。

**当前路由**：用户只提交业务目的和可见的 controlled taxonomy。服务端由
`business_line_id` 推导 organization，但内测所有有效请求统一进入 platform queue；
浏览器不得提交审批 scope 或 owner。

**未来路由**：只有接入 Microsoft 邮箱 SSO、公司账号及权威组织/经理关系后，才
启用服务端“最近有效 scope”路由：business-line reviewer -> organization reviewer
-> platform fallback。自填 profile、workspace role 或前端 scope 均不能触发升级。

**依据**：

1. 内测用户是单体注册账号，没有可信 org/经理图，所谓“直属审批”目前不可判定。
2. 信任制会立即产生 workspace、owner、存储/模型成本和数据边界，撤销成本高；
   request 本身则不授予任何现有空间权限。
3. 内测规模允许 platform queue，以人工审核换取滥用、命名冲突和数据分类控制。
4. 共享 governed-action/impact/audit/outbox 基础设施可直接升级未来 routing，而无须
   把当前假组织关系写死。

**未选方案**：信任制。它缺少可信审批主体和成本/数据边界保护；以后若要开放
self-service，需新的额度、风险、计费和自动策略规范，不由本次兼容开关暗中实现。

**后果**：必须处理职责分离。仅剩一名 platform admin 时返回
`409 reviewer_separation_unavailable`，不得让其自批；break-glass 不在产品 API
范围。创建 policy 必须先有一个经审计的 active revision 与至少两名可用 reviewer；
human caller 的旧 `POST /spaces/` 仅适配成 request/`202`，不会成为 direct-create
旁路。详见主 SPEC §§20--21。

## D-003（开放问题 3）：审计组别/团队使用 controlled field，不使用 tag

**决策**：新增 `WorkGroup`，属于一个 `BusinessLine`；新增
`OfficeLocation`，属于一个 `Organization`，与 workspace 多对多。workspace 保留
现有 organization/business_line，并新增一个 primary `work_group`、多个 locations
及 `classification_state`。`Assurance Group 12345` 是 WorkGroup display name，
稳定身份是 UUID + business-line 内唯一 normalized code。

**层级与权限含义**：

```text
Organization（tenant/data boundary）
└─ BusinessLine（既有 authorization/reporting scope）
   └─ WorkGroup（controlled classification，不新增授权层级）

Organization
└─ OfficeLocation（controlled classification；workspace 可多选）
```

**依据**：

1. group/location 要用于建空间校验、筛选、审批影响、审计报表与未来 identity mapping，
   必须有稳定 ID、scope、active 状态、唯一约束和外键一致性。
2. tag 是自由文本，无法可靠约束同名、改名、跨组织、停用、层级或历史引用；把 tag
   当权限/审批依据会违反 scope 隔离。
3. 不把 WorkGroup 提升为第五级 governance scope，避免破坏已锁定的 §6 四级矩阵；
   BusinessLine 继续承担授权边界。
4. location 可能多选，而审计组/团队需要一个 primary 归类，因此数据形态不同。

**未选方案**：只加 tags；或把 WorkGroup 当新的授权层级。前者不可治理，后者会
重写能力矩阵且缺少当前业务授权需求。

**迁移后果**：历史空间标记 `legacy_unclassified`，不得从 name/tag 猜值；新普通
审批要求完整分类。PostgreSQL deferred trigger 校验 group-business-line 及
location-organization 一致。详见主 SPEC §§13、23。

## D-004（开放问题 4）：第 6 条是两个独立 BUG，分别定根因

**决策**：不把“弹窗关不掉”和“频繁切页加载失败”归为同一 race/SSE 问题；分别
建立回归契约。

### 4A. 访问码弹窗

**路径**：登录后的 header `SpaceSwitcher` -> “Join with access code” -> modal ->
X / Cancel / Esc / mask。

**根因**：`SpaceSwitcher.tsx` 给 Ant Design Modal 传入
`transitionName="fade"`，但源码及当前 dist 没有对应 enter/leave/appear CSS。
rc-motion 因有 motionName 进入 leave 并等待 transition/animation end，rc-dialog
没有 deadline；事件永远不来，`afterClose` 不执行，`animatedVisible`、Portal 和
scroll lock 留存。提交期间另有第二层：`confirmLoading=true` 会让 X、Cancel、Esc、
mask 全部忽略，而当前 busy 覆盖 join、space reload、switch、session reload 全链。

**证据级别**：确定的源码/依赖/构建产物因果链，不冒充实时点击复现。现有浏览器在
`/login`，登录会创建 `AuthSession`（DB 写）且浏览器控制被安全策略拒绝；24 小时
日志无 join POST。因此不能断言历史投诉发生在提交前或提交中，也不能伪造点击次数、
console 或截图。`git blame` 只用于定位：custom transition 由 `96f1dbf` 引入，
原 cancel setter 未变；仓库 14 个同模式 Modal 都进入回归范围。

### 4B. 频繁切页加载失败

**现有 Docker 直接证据**：2026-07-18 10:02:20Z--10:03:12Z（上海 18:02），
Chrome 128、`127.0.0.1:3003`、可访问 legacy admin 的已认证管理员（日志不含 email）
按下列顺序操作：

```text
dashboard -> codes -> announcements -> users -> business-lines
-> 同页刷新 -> templates -> business-lines
```

37.55 秒先成功 39 个 API GET；10:02:57.989 organizations 首个 429，
10:02:57.991 business-lines 同时仍 200，随后持续混合 200/429；quality 首批 4 个
请求有 3 个 429。页面请求组约 200 ms 后重复一次；日志能证明重复，不能唯一归因
StrictMode 或具体 mount 机制。

**根因**：全局 authenticated `UserRateThrottle=30/minute` 被每页 2--5 个并发且
重复 GET 正常耗尽；Gunicorn 2 workers 使用各自 `LocMemCache`，同一身份的限流历史
不共享，因此同秒随机交错 200/429。通用 client 不处理 429/`Retry-After`、coalescing
或 route abort，多个页面还把异常转成空数组。该窗口 `CAPABILITY_NAV=false`、无
chat SSE、无通知点击证据，因此不把 capability console、SSE 或通知当根因。

**SPEC 取舍**：

- modal 必须使用完整 default motion 或具 CSS + finite deadline 的自定义 motion；
  idle/pending 均可关闭，late result 不得重开/切空间/污染卸载页面；真实 Chromium
  覆盖无 transitionend、reduced motion、20 次循环和 scroll/focus/Portal 泄漏。
- 导航读请求使用 shared multi-worker limiter，内测契约为 240/min/user、
  60/10-second burst；安全敏感 action 继续独立限流。429 必须返回 Retry-After，前端
  不得伪装空态；每 logical resource/mount 最多一次，支持 coalescing、abort 和
  sequence guard。

**依据**：以上数字与原因都来自现有只读日志/运行设置/源码；SPEC 明确记录证据边界，
同时给出可自动化的成功条件。详见主 SPEC §26。

## D-005（开放问题 5）：超管对话必须显式加入空间

**决策**：platform authority 不隐式产生 `chat.ask`、`chat.history`、知识内容读取或
synthetic owner。超管若要聊天，必须以同一用户身份接受 owner 的 targeted
invitation，或提交 access request 并由 owner approve，得到有效 workspace
membership（包括策略允许时的受限 guest membership）。另一条合法但非聊天捷径的路径，是由**不同的**有权 actor 按
ownership-continuity 完成强制/承接转让并生成显式 owner membership；force actor
不得把自己设为 target。没有 platform self-join API。

**依据**：

1. platform admin 的职责是平台元数据、账号、模型与审计治理，不等于每个租户空间
   的内容参与者。
2. 隐式 chat 会绕过 owner 的成员边界，并与 §6 “scope 隔离、向上授权否定”冲突。
3. 显式 membership 让角色、停用、移除、历史和审计与普通用户完全一致；跨空间不
   会因一次平台身份泄漏。
4. 超管查看 Knowledge 归属的需求用专门 `platform.knowledge.read` metadata API
   满足，不必扩大到文档内容或聊天。

**未选方案**：把 platform scope 直接映射为 `chat.ask` 或在 resolver 中合成 owner。
v3 显式覆盖现行 SPEC 中可能暗示该路径的句子。

**后果**：平台用户未加入时，workspace chat/history/source 返回 scope-safe
403/404；加入后只使用显式 workspace role，而不是 platform role。通常该角色由
owner 授予；ownership recovery 则必须满足 actor-target 分离和完整 scope/reason/
version 约束。详见主 SPEC §§6、25.1、25.4。

## D-006（开放问题 6）：访问码需审批，targeted 邀请接受后直接生效

**决策**：确认该边界，但把“邀请码直接生效”精确定义为：owner 先向明确 user 或
verified email 发出带非 owner role 的 targeted invitation，目标用户显式 accept 后
原子创建/恢复 membership，无第二次 owner 审批。发送邀请本身不等于接受。

**访问码**：空间级随机 credential，只能创建/复用该用户的 pending
`SpaceAccessRequest`；不创建 membership、不切 active space。当前 canonical owner
使用 `workspace.access_requests.manage` approve/reject，且必须 row-lock/recheck code
policy、role ceiling、space/user 状态。request 自身状态为
`pending|approved|rejected|cancelled|expired|invalidated`；code 后续过期不自动决定一个
已提交 request，request 按自身 14 天期限和审批时重检规则处理。

**邀请码/邀请**：绑定目标和 `knowledge_admin|reviewer|member|guest` 中一个可授权
角色；token hash-only、最多 7 天、single-use。accept 时再次验证 inviter/owner 的
grant authority、目标身份、策略/ownership version 和空间 lifecycle。`owner` 永远
不能通过 invitation 或 member CRUD 授予，只能走 ownership transfer。规范化
`target_key` 阻止同一 user/email 的双 pending invitation；verified email 绑定用户时
合并而不是复制。已是 member 的目标 accept 会原子标记 invitation consumed/accepted，
并返回同一 membership，不创建重复行。

**兼容处理**：现有 reusable `InviteCode` + `/spaces/join/` 的直接 membership 行为
保留 §11 一版本，但产品名改为 **legacy invitation code**。新 UI/API 不得创建它或
把它称作访问码；已签发 code 仅到自身 expiry/revocation。移除仍需另批。

**依据**：

1. access code 往往可被转发，必须让 owner 对具体人作最终决定。
2. targeted invitation 已包含 owner 对目标和角色的授权；再要求 owner 审批会产生
   重复动作和 accept 后不确定状态。
3. 两套独立模型可给 secret、状态机、审计和并发约束准确语义，也能在兼容期清楚
   观测旧 direct code 用量。

**通知后果**：目标用户 notification -> Discovery invitation card -> accept/decline；
owner notification -> workspace access-request panel -> approve/reject。每个动作使用
独立 `Idempotency-Key`，锁住资源后重检 expected version；资源状态、audit 与 outbox
row 同事务提交，`on_commit` 只唤醒 delivery dispatcher。stale notification 不再显示
按钮，通知本身永远不是授权事实。详见主 SPEC §24。

## 决策一致性检查

这些决策共同保持以下边界：

- 普通创建申请、访问申请和邀请均不产生上级 scope；只有明确成功状态产生被约束的
  workspace/role。
- platform 可以审批“是否创建”，但不能据此拥有或聊天；workspace owner 决定成员，
  ownership transfer 决定 owner。
- WorkGroup/location 用于分类、检索和审批校验，不变成隐式 capability。
- 所有状态改变具备 audit、per-operation idempotency、版本/impact、PostgreSQL row
  lock 与并发测试；业务状态、audit、outbox row 原子提交，通知 delivery 在 commit 后
  异步发生且不是授权事实。
- legacy 兼容保留一版本，不因本日志而删除。
