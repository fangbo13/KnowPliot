# KnowPilot 所有权连续性与账号离职编排 SPEC

> 版本：2026-07-17 v1.0
>
> 状态：设计已确认；尚未实现
>
> 适用基线：Version1.74.1，基线提交 135372e
>
> 上位文档：[KnowPilot Optimization Specification Addendum](../../specs/2026-07-16-knowpilot-optimization-spec.md)
>
> 实现交接：[Version1.74.1 所有权连续性实现 Prompt](../../operations/Version1.74.1_ownership_continuity_implementation_handoff.md)

本文是 KnowPilot Version1.74.1 的规范性增补，解决空间房主账号停用或删除后，空间失去实际管理人的问题，并把同类风险扩展到平台管理员、组织管理员、业务线管理员、凭据、分享和待办任务。

如果本文与既有 SPEC 在“空间所有权、账号停用、账号删除、管理员继任、会话或凭据撤销”方面发生冲突，以本文为准。本文只定义产品和工程契约，本次交付不包含业务代码、数据库迁移或运行环境操作。

## 1. 目标与非目标

### 1.1 必须实现的结果

1. 每个未清除的空间始终拥有且只拥有一个有效的权威房主。
2. 房主主动转让采用“请求—接收”流程；接收完成前旧房主继续负责。
3. 管理员执行离职或紧急处置时，可以在授权范围内强制、原子地完成房主交接。
4. 账号停用前必须完成影响预检；任何唯一管理权缺少继任者时，停用不得发生。
5. 平台、组织、业务线和空间四层管理权都必须遵守“最后有效管理员不可直接撤销”的规则。
6. 账号停用必须同步撤销登录会话、有效分享和离职者签发的未使用高权限凭据。
7. 个人内容、业务内容和审计归属必须采用不同的离职策略，不能把所有用户外键一律级联删除或一律转移。
8. 重新启用账号不得自动恢复旧房主身份、管理角色、登录会话或已撤销凭据。
9. 所有交接、阻止、强制接管和凭据撤销都必须可审计、可幂等、可并发保护。
10. 前端必须提供可搜索的候选人选择、影响预览和确认摘要，不再要求操作人手填用户 UUID。

### 1.2 明确不做

- 不引入多房主、共同房主或投票式所有权。
- 不把退出登录等同于停用账号。
- 不允许空间房主或业务线管理员直接停用全局用户账号。
- 不把私人对话自动转交给继任者。
- 不在本阶段建设 HR、IAM、SCIM 或工单系统集成。
- 不跨组织转移空间。
- 不新增个人 API Key、PAT 或自动化任务模型；只为未来模型规定连续性原则。
- 不通过 Django signal 单独承担核心一致性；核心流程必须经过显式服务和数据库约束。
- 不在数据迁移中任意选择“最早创建者”作为房主。

## 2. 术语与生命周期

| 术语 | 规范定义 |
|---|---|
| 创建者 | KnowledgeSpace.created_by，仅表示创建来源，不等于当前房主。 |
| 权威房主 | KnowledgeSpace.owner 指向的唯一用户，是空间所有权的唯一事实来源。 |
| owner 成员镜像 | SpaceMembership 中 role=owner 的兼容记录，必须与权威房主保持一致，但不再是独立事实来源。 |
| 有效用户 | User.is_active=true 且未进入离职完成状态。 |
| 有效成员 | 用户有效、membership.status=active，且 expires_at 为空或晚于当前时间。 |
| 有效房主 | 同时满足“权威房主”和“有效成员”的用户。 |
| 管理权继任 | 将组织或业务线的同级管理员职责交给另一名符合范围要求的用户。 |
| 主动转让 | 当前房主发起、目标用户明确接收后生效的转让。 |
| 强制交接 | 具备治理权限的管理员因离职、失联或紧急处置而立即完成的原子转让。 |
| 停用 | 禁止继续认证并撤回有效权限；用户记录和受保留策略约束的数据仍存在。 |
| 匿名化 | 保留业务或审计记录，但去除不再需要的直接个人标识。 |
| 硬删除 | 物理删除用户记录；不是常规离职动作，本阶段默认禁止。 |
| 影响预检 | 在停用前计算所有管理权、凭据、分享、任务和受保护引用的只读快照。 |

“退出登录”只撤销当前会话；“停用”是管理员治理操作；“匿名化或硬删除”是满足保留期后的独立合规流程。产品文案不得继续用一个“注销”同时表达这三种动作。

## 3. 当前实现审计

### 3.1 已有能力

- 创建空间时会把创建者加入 SpaceMembership 并设置 role=owner。
- POST /api/v1/spaces/{id}/transfer-owner/ 已能把一个 active 成员提升为 owner，并降级其他 active owner。
- 成员删除或降级接口会阻止删除其查询结果中的最后一个 active owner。
- 账号管理提供 activate 和 deactivate，但不提供业务层硬删除 API。
- 用户安全模块已有 revoke_all_sessions()，但停用接口没有调用它。

### 3.2 问题登记

| ID | 当前问题 | 代码证据 | 影响 |
|---|---|---|---|
| KP-O01 | 空间没有显式 owner 字段，权限依赖可级联删除的 SpaceMembership。 | backend/apps/spaces/models.py:113、135、165 | 用户删除可移除 owner 记录；创建者和当前房主语义混乱。 |
| KP-O02 | “最后房主”只检查 membership.status，没有检查 user.is_active 或过期时间。 | backend/apps/spaces/views.py:494 | 已停用用户仍被统计为有效房主。 |
| KP-O03 | transfer-owner 没有锁定空间和成员行，也没有版本比较或幂等键。 | backend/apps/spaces/views.py:241 | 并发转让、成员撤销和账号停用可能互相覆盖。 |
| KP-O04 | 账号停用只设置 is_active=false 并停用全局 UserRole。 | backend/apps/rbac/views.py:342 | 不处理唯一房主、组织/业务管理员、scoped memberships、会话和凭据。 |
| KP-O05 | 重新启用只恢复 is_active。 | backend/apps/rbac/views.py:285 | 原 scoped memberships 仍为 active，权限可意外复活；旧会话也未明确失效。 |
| KP-O06 | 组织管理员分配可直接删除到零；全局角色撤销也没有最后平台管理员保护。 | backend/apps/spaces/admin_views.py:773、backend/apps/rbac/views.py:198 | 管理范围可能失去可用管理员。 |
| KP-O07 | 前端房主转让要求填写用户 UUID。 | frontend/src/pages/console/WorkspaceLifecyclePage.tsx:55 | 操作困难，容易转给错误用户，无法查看资格和影响。 |
| KP-O08 | Django Admin 使用标准 UserAdmin，未关闭用户删除；模型同时存在 CASCADE、PROTECT 和 SET_NULL。 | backend/apps/users/admin.py:10 及各 app models.py | 硬删除可能级联丢数据，也可能因 PROTECT 中途失败，行为不可预测。 |
| KP-O09 | 有效分享、邀请码、管理员注册码和待办任务没有离职处置。 | backend/apps/chat/models.py:285、backend/apps/spaces/models.py:259、312 | 离职者创建的入口或外链可能继续有效。 |
| KP-O10 | 私人对话、合规导出等记录使用 CASCADE 用户外键。 | backend/apps/chat/models.py:18、643 | 硬删除用户会删除历史或合规记录，和审计保留要求冲突。 |

### 3.3 根因

当前系统把三件事拆散在不同接口中：

1. 空间成员角色变化；
2. 用户账号停用；
3. 管理员作用域撤销。

它们没有共享“有效管理人”的定义，也没有一个可以锁行、重新检查并一次提交的离职编排服务。因此成员接口中的最后房主保护可以被账号停用、角色撤销、Django Admin 删除或直接 ORM 操作绕过。

## 4. 方案比较与设计决策

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A. 停用前阻断 | 继续以 SpaceMembership.role=owner 为事实来源，只给 deactivate 增加检查。 | 改动最小。 | 无法可靠抵御硬删除、并发和其他撤权入口；创建者/房主语义仍混乱。 |
| B. 显式唯一房主 + 离职编排 | 增加权威 owner、转让状态机、统一预检和事务化离职服务。 | 规则清晰，可数据库保护，可覆盖所有入口和同类管理权。 | 需要分阶段迁移和兼容旧 owner 角色。 |
| C. 多房主 | 允许多个同级 owner，只保证至少一人有效。 | 可用性高，降低单点风险。 | 责任边界、审计、最终决策权和离职判断更模糊。 |

采用方案 B。房主主动转让需要目标用户接收；治理管理员在授权范围内可因离职或紧急情况强制交接。空间保持单一权威房主，平台/组织/业务线管理员采用“至少一名有效同级管理员”的连续性规则。

## 5. 锁定不变量

以下规则属于安全和数据完整性要求，不得通过 GovernancePolicy 关闭：

1. 每个 active 或 archived 空间的 KnowledgeSpace.owner 均非空。
2. 同一空间在任意提交点只有一个权威房主。
3. 权威房主必须是有效用户，并拥有该空间的有效成员关系。
4. SpaceMembership 中最多一个 active owner 镜像，且必须对应 KnowledgeSpace.owner。
5. pending 转让不改变任何权限；只有 accepted 或 forced 完成才切换房主。
6. 主动转让完成前，旧房主不能被移除、降级、停用或删除。
7. 停用操作必须重新计算影响，不能只信任前端预检结果。
8. 任何唯一房主或最后管理员未解决时，停用、撤权和硬删除都必须失败且不产生部分更改。
9. 所有权切换、旧角色降级、离职者权限撤回和账号停用必须处于同一数据库事务。
10. 事务必须按稳定顺序锁定用户、空间、成员和管理员分配，避免死锁。
11. 同一个 Idempotency-Key 重复提交只产生一次逻辑转让或离职操作。
12. 失败事务不得发出成功通知；通知仅在 transaction.on_commit 后发送。
13. 重新启用账号需要重新认证和显式授权，不恢复已撤销的房主、管理员、会话、分享或凭据。
14. 个人对话默认不向继任者开放；业务管理权交接不等于个人数据交接。
15. 审计日志保留 actor、subject、旧/新责任人、scope、reason_code 和 request_id，但不得记录密钥、邀请码正文、token、密码或不受控自由文本。

## 6. 权限边界

### 6.1 新能力代码

| Capability | 用途 |
|---|---|
| workspace.ownership.read | 查看当前房主、转让状态和候选人。 |
| workspace.ownership.transfer.request | 当前房主发起或取消主动转让。 |
| workspace.ownership.transfer.accept | 目标用户接收或拒绝指向自己的转让。 |
| workspace.ownership.transfer.force | 治理管理员在授权范围内强制交接。 |
| governance.admin_succession.manage | 管理组织或业务线管理员继任。 |
| governance.users.suspend | 只撤销用户在本治理范围内的访问，不停用全局账号。 |
| platform.users.offboard | 执行全局影响预检和账号离职。 |

### 6.2 角色矩阵

| 操作 | 空间房主 | 业务线管理员 | 组织管理员 | 平台管理员 | 目标用户 |
|---|---:|---:|---:|---:|---:|
| 查看空间所有权 | 本空间 | 本业务线 | 本组织 | 全平台 | 指向自己的转让 |
| 发起主动转让 | 是 | 否 | 否 | 否 | 否 |
| 接收/拒绝转让 | 否 | 否 | 否 | 否 | 仅本人 |
| 强制空间交接 | 否 | 本业务线 | 本组织 | 全平台 | 否 |
| 撤销空间访问 | 本空间，受最后房主保护 | 本业务线 | 本组织 | 全平台 | 否 |
| 管理业务线管理员继任 | 否 | 否 | 本组织 | 全平台 | 否 |
| 管理组织管理员继任 | 否 | 否 | 否 | 全平台 | 否 |
| 范围内暂停访问 | 否 | 本业务线 | 本组织 | 全平台 | 否 |
| 停用全局账号 | 否 | 否 | 否 | 是 | 否 |
| 硬删除用户 | 否 | 否 | 否 | 默认也禁止 | 否 |

空间房主、业务线管理员和组织管理员不能通过旧的全局 RBAC 权限或前端路由推断获得 platform.users.offboard。服务端必须对每次操作进行真实 scope 检查。

## 7. 数据模型

### 7.1 KnowledgeSpace

新增字段：

| 字段 | 契约 |
|---|---|
| owner | 指向 User 的非空 ForeignKey，on_delete=PROTECT；是唯一权威房主。 |
| ownership_version | 正整数，初始为 1；每次成功切换房主递增，用于并发比较。 |

created_by 保持不变，仅用于来源审计，不随房主转让修改。

SpaceMembership.role=owner 在兼容期内保留。数据库增加条件唯一约束：每个空间最多一个 status=active 且 role=owner 的成员记录。所有权限解析先读取 KnowledgeSpace.owner；owner 成员记录只作为成员列表和旧客户端兼容镜像。

### 7.2 OwnershipTransfer

新增持久化记录：

| 字段 | 契约 |
|---|---|
| id | UUID。 |
| space | 目标空间；on_delete=PROTECT。 |
| from_owner | 发起时的权威房主；on_delete=PROTECT。 |
| to_owner | 目标用户；on_delete=PROTECT。 |
| requested_by | 实际操作人；on_delete=PROTECT。 |
| accepted_by | 主动转让中完成接收的用户；强制交接为空；on_delete=PROTECT。 |
| mode | voluntary、forced 或 offboarding。 |
| status | pending、completed、declined、cancelled、expired 或 invalidated。 |
| expected_ownership_version | 发起时的空间 ownership_version。 |
| reason_code | 枚举值，如 voluntary、employment_ended、account_compromised、admin_recovery。 |
| reason_note | 最长 500 字；只允许必要的安全说明，不得存放秘密或敏感人事细节。 |
| idempotency_key | 调用方生成的 UUID。 |
| expires_at | 主动转让默认 72 小时；强制交接为空。 |
| created_at、completed_at | 审计时间。 |

约束：

- 一个空间最多存在一条 pending 转让。
- requested_by 与 idempotency_key 唯一。
- from_owner 不能等于 to_owner。
- completed 必须具有 completed_at。
- pending 只能用于 voluntary。

### 7.3 用户离职元数据

User 增加最小必要字段：

| 字段 | 契约 |
|---|---|
| deactivated_at | 管理员停用完成时间；待审批账号保持为空。 |
| deactivated_by | 执行停用的用户，SET_NULL。 |
| deactivation_reason_code | 受控枚举，不保存详细人事信息。 |

本阶段不新增复杂的 HR 离职工单表。影响预检是可重算 DTO；提交时通过 impact_version 防止使用过期结果。审计日志和 OwnershipTransfer 提供持久证据。

## 8. 房主转让状态机

### 8.1 主动转让

| 当前状态 | 操作 | 下一状态 | 所有权变化 |
|---|---|---|---|
| 无 pending | 当前房主发起 | pending | 无 |
| pending | 目标用户接收 | completed | 原子切换 |
| pending | 目标用户拒绝 | declined | 无 |
| pending | 发起人取消 | cancelled | 无 |
| pending | 超过 expires_at | expired | 无 |
| pending | 房主、目标资格或版本已变化 | invalidated | 无 |

目标用户必须满足：

- User.is_active=true；
- 属于同一组织；
- 是该空间未过期的 active 成员；
- 角色不能是 guest；
- 不等于当前房主。

接收时必须重新验证全部条件并锁定空间。只要条件不再成立，记录变为 invalidated，返回 409，不切换所有权。

过期必须同时采用惰性和定时处理：读取或接收 pending 转让时先比较 expires_at 并原子标记 expired；每小时运行的清理任务补充处理无人访问的记录。两条路径都必须幂等，且不得改变任何权限。

### 8.2 强制或离职交接

具备 workspace.ownership.transfer.force 的管理员可以选择同组织的 active 用户。目标尚不是空间成员时，服务可在同一事务中创建 active member 记录，再将其设为 owner。

强制交接必须提供 reason_code；reason_note 在 account_compromised、admin_recovery 等紧急情形下必填。强制交接不创建 pending 状态，成功后直接写 completed，并通知旧房主、目标房主和相应治理管理员。

### 8.3 原子切换顺序

1. 使用 select_for_update 锁定 KnowledgeSpace，并比较 expected_ownership_version。
2. 使用 select_for_update 锁定旧房主和目标用户的 SpaceMembership。
3. 重新验证操作人权限、目标资格和空间状态。
4. 创建或激活目标成员关系。
5. 把旧 owner 镜像降级为 member；离职模式下改为 revoked。
6. 把目标成员镜像设为 owner。
7. 更新 KnowledgeSpace.owner 并递增 ownership_version。
8. 使同空间其他 pending 转让失效。
9. 写 OwnershipTransfer 和审计事件。
10. 提交后发送通知。

任一步骤失败时全部回滚。

### 8.4 所有权 API

| Method and path | 权限 | 契约 |
|---|---|---|
| GET /api/v1/spaces/{id}/ownership/ | workspace.ownership.read | 返回当前权威房主、ownership_version、pending 转让和当前调用人的允许动作。 |
| GET /api/v1/spaces/{id}/ownership-candidates/?purpose=voluntary&q=&cursor= | workspace.ownership.transfer.request | 只返回本空间 active、未过期、非 guest 成员。 |
| GET /api/v1/spaces/{id}/ownership-candidates/?purpose=forced&q=&cursor= | workspace.ownership.transfer.force | 返回同组织 active 用户；明确标记是否需要创建成员关系。 |
| POST /api/v1/spaces/{id}/ownership-transfers/ | workspace.ownership.transfer.request | 当前房主创建 voluntary pending，返回 202。 |
| POST /api/v1/spaces/{id}/ownership-transfers/force/ | workspace.ownership.transfer.force | 治理管理员直接完成强制交接，返回 200。 |
| POST /api/v1/spaces/{id}/ownership-transfers/{transfer_id}/accept/ | workspace.ownership.transfer.accept 且目标为本人 | 接收 pending 转让并原子切换房主。 |
| POST /api/v1/spaces/{id}/ownership-transfers/{transfer_id}/decline/ | workspace.ownership.transfer.accept 且目标为本人 | 拒绝，不改变所有权。 |
| POST /api/v1/spaces/{id}/ownership-transfers/{transfer_id}/cancel/ | 发起人或具备 workspace.ownership.transfer.force | 取消 pending，不改变所有权。 |

主动转让请求体：

~~~json
{
  "to_user_id": "uuid",
  "expected_ownership_version": 4,
  "reason_code": "voluntary"
}
~~~

强制交接请求体：

~~~json
{
  "to_user_id": "uuid",
  "expected_ownership_version": 4,
  "reason_code": "employment_ended",
  "reason_note": "Safe operational explanation"
}
~~~

客户端不能在主动转让接口中提交 mode=forced。force 只能由专用 endpoint 和服务端 capability 判定。GET ownership 的 owner 对象只返回安全展示字段，不返回不必要的人事资料。

## 9. 账号离职编排

### 9.1 影响预检

平台管理员在停用全局账号前必须调用：

GET /api/v1/admin/users/{user_id}/offboarding-impact/

响应至少包含：

~~~json
{
  "subject": {
    "id": "uuid",
    "display_name": "Safe display name",
    "is_active": true
  },
  "impact_version": "sha256-of-normalized-impact",
  "blockers": {
    "owned_spaces": [],
    "last_platform_admin": false,
    "last_organization_admin_scopes": [],
    "last_business_admin_scopes": []
  },
  "actions": {
    "active_sessions": 3,
    "active_conversation_shares": 2,
    "active_invite_codes": 1,
    "active_admin_registration_codes": 0,
    "pending_email_invites": 4,
    "open_feedback_reviews": 1,
    "open_knowledge_gap_tickets": 2,
    "running_jobs": 1
  },
  "protected_history": {
    "documents": 8,
    "crawls": 2,
    "audit_records": 36,
    "completed_export_jobs": 1
  },
  "can_deactivate_without_successor": false
}
~~~

impact_version 必须由排序后的资源 ID、所有权版本、管理员分配更新时间和相关计数组成；不得把 email、reason_note 或 token 放入哈希输入日志。

候选人通过独立、分页、可搜索接口获取，服务端只返回操作人有权查看的用户：

GET /api/v1/spaces/{space_id}/ownership-candidates/?purpose=forced&q=&cursor=

### 9.2 提交离职

新增规范入口：

POST /api/v1/admin/users/{user_id}/offboard/

~~~json
{
  "impact_version": "value returned by preflight",
  "reason_code": "employment_ended",
  "reason_note": "Optional safe operational note",
  "space_transfers": [
    {
      "space_id": "uuid",
      "successor_user_id": "uuid",
      "expected_ownership_version": 4
    }
  ],
  "organization_admin_successions": [
    {
      "organization_id": "uuid",
      "successor_user_id": "uuid"
    }
  ],
  "business_admin_successions": [
    {
      "business_line_id": "uuid",
      "successor_user_id": "uuid"
    }
  ],
  "revoke_issued_credentials": true
}
~~~

服务端执行：

~~~mermaid
flowchart LR
    A["锁定目标用户"] --> B["重新计算影响"]
    B --> C{"impact_version 一致？"}
    C -- "否" --> X["409：重新预检"]
    C -- "是" --> D["按 UUID 排序锁定 scope 与空间"]
    D --> E["完成管理员继任和房主强制交接"]
    E --> F["撤销 scoped memberships、角色、会话、分享和凭据"]
    F --> G["处理开放任务和运行任务"]
    G --> H["设置账号 inactive 与离职元数据"]
    H --> I["写审计并提交"]
    I --> J["发送通知"]
~~~

如果目标是最后一个有效平台管理员，offboard 永远返回 409；必须先通过独立、高审计等级的管理员授予流程建立第二名有效平台管理员。离职接口不得暗中把普通用户提升为平台管理员。

组织和业务线继任可以在离职事务中授予同级角色，但必须满足：

- 操作人拥有该 scope 的继任管理能力；
- 目标用户 active 且属于相应组织；
- 不授予高于离职者原角色或操作人能力的权限；
- 同一继任映射可幂等重放。

### 9.3 旧接口兼容

- POST /api/v1/rbac/users/{id}/deactivate/ 必须改为调用同一 OffboardingService。
- 无 blocker 时旧接口可完成停用。
- 有 blocker 时返回 409、error_code=offboarding_required 和 impact_url，不能继续静默停用。
- POST /api/v1/spaces/{id}/transfer-owner/ 在一个兼容版本内路由到 OwnershipTransferService：
  - 当前房主调用时创建 voluntary pending，返回 202；
  - 具备 force capability 的治理管理员调用时直接完成，返回 200；
  - 响应加入 Deprecation 和 successor endpoint 信息。
- 所有新前端必须使用新 ownership endpoints，不再调用旧接口。

### 9.4 停用事务中的撤回顺序

1. 完成全部房主和管理员继任。
2. 使离职者的 SpaceMembership 和 OrganizationMembership 失效。
3. 停用全部 UserRole，包括兼容角色。
4. 调用 revoke_all_sessions()，撤销全部 AuthSession。
5. 撤销全部有效 ConversationShare。
6. 撤销离职者签发且尚未使用的 InviteCode、AdminRegistrationCode 和 pending SpaceEmailInvite。
7. 重新排队或解除开放任务分配。
8. 按资源矩阵处理排队/运行任务。
9. 设置 User.is_active=false 和离职元数据。
10. 写入一个总离职事件和各 scope/资源子事件。

## 10. 同类资源治理矩阵

| 资源 | 实际归属 | 离职处理 | 是否需要“转移” |
|---|---|---|---|
| 平台管理员 | 平台职责 | 至少保留一名有效平台管理员；运维健康目标为两名独立 break-glass 管理员。 | 不是对象所有权；需要最后管理员保护。 |
| 组织管理员 | Organization | 活跃组织必须保留有效 org_admin；离职事务可授予同级继任者。 | 需要管理员继任。 |
| 业务线管理员 | BusinessLine | 有 active 空间的业务线必须保留有效 business_admin；org_admin 可指定继任者。 | 需要管理员继任。 |
| KnowledgeSpace | 唯一权威房主 | 主动转让或强制交接。 | 必须转移。 |
| Document、CrawledDocument、AnswerTemplate | 空间或平台业务资产；uploaded_by/created_by 是来源 | 不改变作者；管理权跟随 scope。Phase 1 保留 PROTECT，后续匿名化只改变身份展示，不重写作者。 | 不转移作者身份。 |
| ScenarioTemplate、GovernancePolicy、ModelProfile | platform/org/business-line/space scope | 保留创建审计；只保证 scope 有有效管理员。 | 不转移。 |
| ChatSession、Message、ChatTurn、Feedback | 用户个人或受限协作内容 | 停用时保留并限制访问；后续按保留策略匿名化。不得自动开放给继任者。 | 不转移。 |
| ConversationShare | 用户签发的临时访问能力 | 停用时立即 revoke；不让继任者继承 token。 | 撤销，不转移。 |
| InviteCode、AdminRegistrationCode、SpaceEmailInvite | scope 凭据 | 离职者签发且未使用的凭据默认撤销；继任者重新签发。 | 撤销并重发。 |
| Feedback reviewer、KnowledgeGap assignee | 开放工作项 | 解除分配并回到 scope 队列；管理员可重新分配。 | 重新排队，不自动转给房主。 |
| IngestionJob、crawl、RAGEvaluationRun | scope 工作和审计 | 可继续的 scope 任务继续；requested_by 改为可保留历史归属。 | 不转移任务所有权。 |
| ComplianceExportJob | 高敏感个人请求和合规证据 | queued/processing 任务取消并删除未完成结果；已完成记录保留审计 tombstone，不随用户 CASCADE。 | 取消或保留，不转移下载权。 |
| AuditLog、ReviewEvent | 不可变审计证据 | 保留 actor ID/tombstone 和事件，不随用户删除。 | 永不转移。 |
| API Key、PAT、Webhook、计划任务 | 当前仓库不存在用户所有模型 | 未来新增时必须声明 scope、custodian、继任和停用撤销策略，否则不得上线。 | 按未来资源类型定义。 |

## 11. 硬删除、匿名化与重新启用

### 11.1 硬删除

Phase 1 默认禁止通过 API、Django Admin 和普通 ORM 管理命令硬删除 User：

- Django Admin 去除 delete permission 或改为调用离职预检。
- User 删除前必须受到 KnowledgeSpace.owner 的 PROTECT。
- 任何合规删除需求先完成停用、保留期、导出和匿名化评估。
- 不得依赖当前 CASCADE 关系清理数据。

后续若引入最终清除任务，必须逐类处理用户外键：

- 业务和审计记录保留匿名 actor/tombstone；
- 私人数据依据批准的保留政策删除或匿名化；
- share/token/secret 物理撤销；
- 所有清除动作写审计摘要，不记录被清除的敏感正文。

### 11.2 重新启用

activate 只恢复登录资格，不恢复：

- KnowledgeSpace.owner；
- SpaceMembership 或 OrganizationMembership；
- UserRole；
- AuthSession；
- ConversationShare；
- InviteCode、AdminRegistrationCode 或 SpaceEmailInvite。

管理员必须显式重新授予所需 scope。用户必须重新登录并完成当前 MFA 要求。

## 12. API 错误、并发与幂等契约

| HTTP | error_code | 条件 |
|---|---|---|
| 400 | invalid_successor | 目标与本人相同、guest、跨组织或字段格式错误。 |
| 403 | insufficient_scope | 操作人没有对应 scope 能力。 |
| 404 | resource_not_found | 对无权获知的空间、用户或转让采用不泄露的 404。 |
| 409 | ownership_changed | expected_ownership_version 已过期。 |
| 409 | transfer_already_pending | 空间已有 pending 主动转让。 |
| 409 | transfer_invalidated | 房主或目标资格已变化。 |
| 409 | offboarding_required | 旧 deactivate 发现未解决 blocker。 |
| 409 | offboarding_impact_changed | 提交时 impact_version 与当前状态不同。 |
| 409 | last_platform_admin | 操作会使有效平台管理员变为零。 |
| 409 | last_scope_admin | 操作会使组织或业务线有效管理员变为零。 |
| 409 | owner_successor_required | 仍有唯一房主空间没有 successor。 |
| 422 | unsafe_reason | reason_note 超过 500 字、包含控制字符，或在必须提供说明的强制场景中为空。 |

所有写接口接受 Idempotency-Key 请求头。相同 key、actor 和规范化请求体返回原结果；相同 key 配不同请求体返回 409 idempotency_conflict。

锁顺序固定为：

1. subject User；
2. Organization；
3. BusinessLine；
4. KnowledgeSpace，按 UUID 升序；
5. OrganizationMembership；
6. SpaceMembership；
7. OwnershipTransfer。

## 13. 审计、通知与可观测性

### 13.1 审计事件

至少新增：

- space_ownership_transfer_requested
- space_ownership_transfer_accepted
- space_ownership_transfer_declined
- space_ownership_transfer_cancelled
- space_ownership_transfer_expired
- space_ownership_transfer_forced
- admin_succession_completed
- user_offboarding_blocked
- user_offboarding_completed
- user_reactivated
- credential_revoked_for_offboarding
- share_revoked_for_offboarding
- work_item_requeued_for_offboarding

每条事件包含 request_id、actor_id、subject_id、scope_type、scope_id、result、reason_code、old_principal_id 和 new_principal_id。自由文本 reason_note 只保存在受限离职记录或受控审计详情中，普通列表不返回。

### 13.2 通知

- 主动转让：目标用户收到待接收通知；发起人收到接收、拒绝、过期或失效结果。
- 强制交接：旧房主、目标房主、执行人所在治理范围的管理员收到结果通知。
- 离职完成：执行人收到汇总；继任者按 scope 分别收到新职责通知。
- 通知只包含空间或 scope 名称、动作和安全链接，不包含 reason_note、人事信息或凭据。

### 13.3 指标和健康检查

新增指标：

- ownerless_spaces，发布门禁必须为 0；
- inactive_space_owners，发布门禁必须为 0；
- spaces_with_multiple_owner_memberships，发布门禁必须为 0；
- active_orgs_without_admin，发布门禁必须为 0；
- active_business_lines_without_admin，发布门禁必须为 0；
- pending_ownership_transfers_total；
- pending_ownership_transfers_over_72h；
- offboarding_blocked_total，按 blocker 类型聚合；
- offboarding_failed_total，按安全错误码聚合。

健康接口只返回计数和状态，不返回用户或空间明细。

## 14. 前端产品契约

### 14.1 空间所有权卡片

位置：/workspace/{spaceId}/manage/lifecycle 或等价 workspace 管理页。

必须显示：

- 当前房主的安全展示名和账号状态；
- 是否存在 pending 转让、目标用户和过期时间；
- ownership_version 不直接展示，但随请求提交；
- “转移房主”按钮只对 request capability 可见；
- 治理管理员看到“强制交接”，并要求选择 reason_code 和二次确认。

转让向导：

1. 搜索并选择合格候选人；
2. 展示目标用户、现有角色、组织和将获得的能力摘要；
3. 主动转让展示“接收前旧房主仍负责”；
4. 强制交接展示不可逆影响和审计提示；
5. 成功后刷新成员、能力、导航和 ownership 状态。

不得出现原始 UUID 输入框。

### 14.2 用户离职抽屉

平台用户管理页点击“停用”后先打开影响抽屉，不能直接弹出普通 Popconfirm。

抽屉分为：

1. 唯一管理权 blocker；
2. 将撤销的会话、分享和凭据；
3. 将重新排队或取消的任务；
4. 将保留的历史和审计数据；
5. successor 映射；
6. 最终确认摘要。

所有 blocker 解决且 impact_version 未过期时才启用“完成交接并停用”。提交期间按钮只允许一次点击。409 impact changed 必须保留用户已选映射，刷新差异后要求重新确认。

### 14.3 范围内暂停

组织/业务线管理控制台使用“移出本组织/业务线”或“暂停本范围访问”，不得显示“停用账号”。如果用户仍属于其他组织，界面明确说明其全局账号不受影响。

### 14.4 可用性

- 候选人 Select 支持键盘、搜索、加载、空状态和分页。
- 错误摘要使用稳定 error_code 映射 i18n 文案。
- 中英文 key 同步；中文不得再混用“注销、停用、删除”。
- 确认对话框默认焦点不放在破坏性按钮。
- reduced motion 下不播放步骤切换动画。
- 360px 宽度下仍能完成预检、候选人选择和确认。

## 15. 数据迁移与兼容发布

采用三阶段迁移，禁止在 schema migration 中任意决定异常空间房主。

### 15.1 阶段 A：可空字段与审计命令

1. 添加 nullable KnowledgeSpace.owner 和 ownership_version。
2. 添加 OwnershipTransfer 和用户离职元数据。
3. 提供 audit_ownership_continuity 管理命令，报告：
   - 没有 owner 成员的空间；
   - 多个 active owner 成员的空间；
   - owner 用户 inactive；
   - owner membership 过期或 revoked；
   - active 组织/业务线没有有效管理员；
   - 用户硬删除的 PROTECT/CASCADE 风险计数。
4. 仅当空间恰好存在一名有效 owner 时自动回填 owner。
5. 异常项输出机器可读 JSON/CSV，但不包含 token、邀请码正文或不必要 PII。

### 15.2 阶段 B：服务双写与修复

1. 所有创建、转让、成员角色修改、管理员撤权和账号停用改走统一服务。
2. owner FK 和 owner membership 镜像双写。
3. 运维人员通过有审计的修复命令或管理流程解决 0/多 owner 异常。
4. 在筼筜 PostgreSQL 执行授权的 dry-run 和事务回滚演练。

### 15.3 阶段 C：收紧约束

1. owner 改为 non-null、PROTECT。
2. 添加 active owner membership 条件唯一约束。
3. 权限解析切换为 owner FK 权威。
4. 旧 transfer-owner 和直接 deactivate 客户端进入一个版本的弃用期。
5. 监控确认旧入口无流量后移除兼容逻辑。

本地 SQLite 测试不能替代 PostgreSQL 条件约束、锁竞争和迁移演练证据。

## 16. 验收矩阵

### 16.1 后端

必须覆盖：

1. 创建空间同时建立 owner FK 和唯一 owner membership。
2. 主动转让在接收前不改变权限。
3. 接收后旧房主降级、目标成为唯一房主、version 递增。
4. 拒绝、取消、过期和 invalidated 都不改变房主。
5. guest、inactive、revoked、expired、跨组织和本人目标被拒绝。
6. business/org/platform 管理员只能在自己的 scope 强制交接。
7. 两个并发转让只有一个成功，另一个返回 409。
8. 幂等重放不产生第二条转让或第二次通知。
9. 唯一房主未映射时 offboard 返回 409，数据库完全不变。
10. 提供全部 successor 后，交接、撤权、会话/分享/凭据撤销和账号停用一次提交。
11. 任一中间步骤异常时整个离职事务回滚。
12. 直接成员删除、角色撤销、旧 deactivate、Django Admin 和用户 delete 都不能绕过最后管理员规则。
13. 最后 platform、org 或 business admin 不可被停用或撤权。
14. archived 空间也必须保持有效房主。
15. 停用后全部 AuthSession 立即失效。
16. reactivation 不恢复任何旧 scope、会话、分享或凭据。
17. 私人对话不因房主交接向继任者开放。
18. 完成的合规记录和审计记录不随用户硬删除消失。

### 16.2 前端

必须覆盖：

1. 房主转让使用可搜索候选人，不出现 UUID 输入。
2. 不合格候选人不显示或明确禁用。
3. 主动转让、强制交接和离职流程具有不同确认文案。
4. 用户停用先加载 impact，存在 blocker 时不能提交。
5. 409 impact changed 会重新加载并保留可复用选择。
6. scoped admin 不显示全局停用操作。
7. capability denial 不能被前端角色数组绕过。
8. 重复点击只发送一个转让或离职请求。
9. 中英文、键盘、屏幕阅读器、reduced motion 和移动布局通过。

### 16.3 发布门禁

- audit_ownership_continuity 无未豁免异常；
- ownerless_spaces=0；
- inactive_space_owners=0；
- active scopes without admin=0；
- Django migration drift=0；
- PostgreSQL migration rehearsal通过；
- 完整后端、前端、类型检查、i18n 和生产构建通过；
- 筼筜浏览器 UAT 覆盖主动转让、强制交接、账号停用、阻断和重新启用。

## 17. 实施路线

| 阶段 | 交付 | 完成定义 |
|---|---|---|
| 0. 回归保护 | 现状失败测试、Django Admin 用户删除保护、审计命令骨架、错误码契约 | 测试能稳定复现停用唯一房主和最后管理员缺口，且新实现期间不能继续硬删除用户。 |
| 1. 数据与服务 | owner 字段、OwnershipTransfer、锁和统一 predicate/service | 所有权状态机和并发测试通过。 |
| 2. 所有权 API/UI | 新 endpoints、capabilities、候选人和转让向导 | 不再手填 UUID，主动/强制流程可用。 |
| 3. 离职编排 | impact、offboard、管理员继任、撤销和任务处理 | 唯一管理权无法被绕过，事务回滚完整。 |
| 4. 数据安全 | Django Admin 限制、CASCADE/PROTECT 修正、匿名化边界 | 用户硬删除不再破坏业务或审计记录。 |
| 5. 兼容与发布 | 旧入口代理、迁移演练、指标、UAT 和 memory 更新 | 所有发布门禁有证据，旧入口有明确退役计划。 |

## 18. 完成定义

本 SPEC 只有在以下条件全部有证据时才算实现完成：

- 空间房主连续性不再依赖 created_by 或一个可被账号停用绕过的 membership 计数；
- 所有停用、撤权和删除入口都调用统一的不变量检查；
- 主动转让、强制交接和账号离职三条路径均有后端、前端和并发测试；
- 同类管理员、凭据、分享、任务和历史数据均按第 10 节处理；
- 迁移没有任意选择异常房主；
- 本地验证与筼筜现场验证边界被分别记录；
- memory.md、实施进度和交接文档更新为真实状态；
- 没有把“设计完成”错误标记为“生产已验收”。

## 19. Implementation status (2026-07-18)

The staged implementation is present on `codex/ownership-continuity`: canonical
space ownership, versioned transfer state, capability-gated voluntary/forced
handoff, impact preflight, and atomic offboarding are implemented. Offboarding
now supports successor mappings for final platform, organization, and business
administrator scopes before revoking the departing user's authority.

Local SQLite focused regressions, Django checks, migration-drift checks,
TypeScript, and i18n checks have passed. This is not a production acceptance:
PostgreSQL constraint/lock rehearsal, full-suite/build evidence, and authenticated
browser UAT remain required release gates.
