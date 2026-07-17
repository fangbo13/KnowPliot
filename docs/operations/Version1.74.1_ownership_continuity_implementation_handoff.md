# Version1.74.1 所有权连续性实现交接 Prompt

把下面完整 Prompt 交给下一次 Codex 对话。该 Prompt 的目标是实现已经批准的 SPEC，不是重新缩小需求或只修补一个按钮。

~~~text
你接手 KnowPilot Version1.74.1 的“所有权连续性与账号离职编排”实现。

仓库与工作区：
- 仓库：D:\KnowPliot
- 设计所在工作树：D:\KnowPliot\.worktrees\knowpilot-optimization
- 当前设计分支：codex/knowpilot-optimization
- GitHub 验收基线分支：Version1.74.1
- 产品代码基线提交：135372e；设计文档提交以当前 git log 为准

开始前先检查 git status、当前分支、worktree 和最新提交。不要覆盖或回退用户已有修改；如果工作树已变化，以实际状态为准并记录差异。为实现工作使用独立的 codex/ 前缀分支或隔离 worktree，避免直接污染验收基线。

必须先完整阅读：
1. docs/superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md
2. docs/specs/2026-07-16-knowpilot-optimization-spec.md
3. SPEC.MD
4. memory.md
5. audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md
6. docs/operations/Version1.74.1_ownership_continuity_implementation_handoff.md

任务目标：
实现“显式唯一房主 + 主动转让需目标接收 + 治理管理员可强制原子交接 + 账号停用前统一影响预检和离职编排”。同时修复平台、组织、业务线最后管理员失联，以及会话、分享、邀请码、开放任务、合规记录在账号停用/删除时的不一致处理。

锁定的产品结论：
- KnowledgeSpace.owner 是唯一权威房主；created_by 只保留创建来源。
- 每个 active 或 archived 空间必须且只能有一个有效房主。
- 主动转让在目标接收前不改变权限；默认 72 小时过期。
- 管理员因离职或紧急处置可在自身 scope 内强制交接，必须提供受控原因并完整审计。
- 空间房主和 scoped admin 不能停用全局账号；只有 platform.users.offboard 可以全局离职。
- 账号停用前必须重新计算 impact；任一唯一房主或最后 scope admin 未解决时返回 409，且数据库不得部分变化。
- 停用必须撤销全部 AuthSession、ConversationShare，以及离职者签发但未使用的高权限邀请码/注册码/待接受邀请。
- 开放 Feedback review 和 KnowledgeGap ticket 解除分配并回到 scope 队列。
- 私人对话不转交给继任者；业务和审计记录不得随用户硬删除级联消失。
- activate 不自动恢复旧 owner、scoped memberships、UserRole、会话、分享或凭据。
- Phase 1 默认禁止 User 硬删除，包括 Django Admin 绕过。

严禁的捷径：
- 不要只给 deactivate 增加一条 owner count 检查。
- 不要继续把 SpaceMembership.role=owner 作为唯一事实来源。
- 不要把 KnowledgeSpace.created_by 当当前房主。
- 不要只依赖 Django signal 保证不变量。
- 不要在数据迁移中自动挑选最早用户、created_by 或任意一名 owner 解决 0/多 owner 异常。
- 不要在前端保留手填用户 UUID。
- 不要让客户端决定自己是否有 force 模式；服务端按 capability 和 scope 判断。
- 不要把 scoped admin 的范围移除实现成全局 User.is_active=false。
- 不要把私人聊天转给新房主。
- 不要把 token、邀请码正文、密钥、人事原因或 provider 信息写进日志、测试快照或提交。
- 不要宣称筼筜/生产通过，除非实际完成了授权的现场验证。

执行方法：
1. 使用 test-driven-development：先新增能够复现唯一房主停用、最后管理员撤权、并发转让和旧接口绕过的失败测试。
2. 写详细实施计划，把工作拆成数据迁移、domain services、权限/API、前端、数据保留、兼容发布六组。
3. 实现统一 predicate：
   - effective user
   - effective space membership
   - canonical/effective owner
   - effective platform/org/business admin
4. 分阶段迁移：
   - 先添加 nullable owner、ownership_version、OwnershipTransfer 和用户离职元数据；
   - 实现 audit_ownership_continuity；
   - 只为恰好一个有效 owner 的空间自动回填；
   - 对 0/多 owner 输出安全的 JSON/CSV 修复报告；
   - 服务双写并完成异常修复后，才收紧 non-null、PROTECT 和条件唯一约束。
5. 建立 OwnershipTransferService：
   - transaction.atomic；
   - select_for_update；
   - expected_ownership_version；
   - 固定锁顺序；
   - Idempotency-Key；
   - pending/accepted/declined/cancelled/expired/invalidated/completed 状态；
   - transaction.on_commit 后通知。
6. 建立 OffboardingImpactService 和 OffboardingService：
   - GET impact 返回 blocker、action、protected_history 和 impact_version；
   - POST offboard 在同一事务中完成管理员继任、房主交接、权限/会话/分享/凭据撤销、任务处理和 User 停用；
   - 重新计算 impact，过期则 409；
   - 中间任何失败全回滚。
7. 将所有绕过入口接入同一服务：
   - 旧 rbac deactivate；
   - SpaceMembership owner 删除/降级；
   - scoped assignment 删除；
   - UserRole revoke；
   - Django Admin delete；
   - 旧 transfer-owner。
8. 新增并只由服务端签发 capability：
   - workspace.ownership.read
   - workspace.ownership.transfer.request
   - workspace.ownership.transfer.accept
   - workspace.ownership.transfer.force
   - governance.admin_succession.manage
   - governance.users.suspend
   - platform.users.offboard
9. 前端实现：
   - 所有权卡片；
   - 可搜索、分页的候选人选择；
   - 主动转让接收/拒绝；
   - 强制交接原因和二次确认；
   - 用户离职 impact 抽屉和 successor 映射；
   - scoped admin 只显示范围暂停；
   - 409 刷新差异并保留仍有效选择；
   - 防重复点击、i18n、键盘、移动端和 reduced motion。
10. 按 SPEC 第 10 节处理同类资源：
   - scope ownership/custody；
   - 分享和凭据撤销；
   - 开放任务重新排队；
   - 合规/审计记录保留；
   - 私人内容不转移。

最低后端测试：
- 创建空间建立 canonical owner 和唯一 owner membership。
- 主动转让接收前无权限变化，接收后原子切换。
- 拒绝、取消、过期、invalidated 不改变房主。
- inactive/revoked/expired/guest/跨组织/本人目标拒绝。
- business/org/platform 强制交接严格按 scope。
- 两个并发转让只有一个成功。
- 幂等重放不重复写入或通知。
- 唯一房主未映射时 offboard 409 且无任何变化。
- 完整映射时交接、撤权、会话/分享/凭据撤销和停用一次提交。
- 故障注入证明全部回滚。
- 最后 platform/org/business admin 无法通过任何入口被撤掉。
- archived 空间仍有有效房主。
- 停用后会话失效；reactivate 不恢复权限。
- 用户硬删除不能级联破坏聊天、合规或审计证据。

最低前端测试：
- 不显示 UUID 输入。
- 候选人资格与 scope 正确。
- impact blocker 未解决时按钮禁用。
- 主动、强制、离职三种确认文案不同。
- scoped admin 看不到全局停用。
- 409 impact changed 正确恢复。
- 重复点击只产生一个请求。
- 中英文 key、键盘、移动布局和 reduced motion 通过。

验证要求：
- 运行与改动范围匹配的后端测试，再运行完整后端套件。
- 运行前端测试、TypeScript、i18n 和生产 build。
- 运行 Ruff/Django check/makemigrations --check/git diff --check。
- 检查本地 Markdown 链接和未决占位标记。
- PostgreSQL 条件约束、select_for_update 和迁移必须在授权的 PostgreSQL 环境验证；SQLite 结果不能替代。
- 未经明确授权不要启动或修改筼筜环境，不要使用生产凭据。

完成后必须更新：
- docs/superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md 的实现状态；
- docs/specs/2026-07-16-knowpilot-optimization-spec.md 的关联状态；
- audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md；
- memory.md；
- 如有迁移演练，新增不含秘密的审计报告。

最终交付格式：
1. 实际实现的行为摘要。
2. 变更文件和迁移列表。
3. 每条锁定不变量的验证证据。
4. 完整测试结果和真实数量。
5. 未完成的现场门禁，明确标为 pending。
6. commit SHA、分支名和工作树状态。
7. 下一位验收人员可复制执行的命令，但不得包含 token 或环境秘密。

不要因为现有 transfer-owner 接口存在就判定需求已经完成。验收标准是：账号停用、角色撤销、成员删除和硬删除路径都无法制造失联空间或零管理员 scope，并且整个离职过程可预检、可审计、可回滚。
~~~
