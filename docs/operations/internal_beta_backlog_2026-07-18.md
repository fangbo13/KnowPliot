# KnowPilot 内测阶段：问题清单

> 整理：ZCode（本地 Docker 验收 + 代码核查）｜日期：2026-07-18
> 用途：问题陈述，交 Claude 思考后重写 SPEC 与实现
> 当前分支：`fix/v1.74.1-acceptance-bugs`（已含验收 bug 修复 `027b069` + 爬虫清理 `82231f5`，未推送）
> 阶段：**内测**（用户仅能注册加入，单体；未来才接微软邮箱 SSO + 公司账号）

> 本文只列问题，不含建议。SPEC 重写与实现方案由 Claude 思考后产出。

---

## 一、用户提出的 7 条

### 1. [PRODUCT] 申请新建 workspace 的审批流程（内测阶段）
**现状**：`can_create_space` 直接放权给 `platform.organizations.manage`/`governance.spaces.manage`（`backend/apps/spaces/views.py:129`），无"申请→审批"流；当前每个用户是单体（无 org/业务线归属），未来才接微软邮箱 SSO + 公司账号。
**问题**：内测期用户只能注册加入，没有"对应经理"概念——建空间该由谁审批？
**优先级**：P1

### 2. [FEATURE/UX] 邀请/访问码加入 workspace 的通知与权限
**现状**：创建者=空间 owner，能力矩阵已含 `workspace.members.manage`/`knowledge.manage`/`workspace.settings.manage`/`workspace.invites.manage`/`workspace.access_requests.manage`（`apps/rbac/capabilities.py`，已验证精确匹配 SPEC §6）；`InviteCode`/`SpaceAccessRequest`/`apps.notifications` 模型与端点已存在（`/spaces/{id}/invites/`、`/spaces/{id}/access-requests/`、`/admin/spaces/{id}/access-requests/.../approve|reject/`）。
**问题**：① 通知→直达"发现工作空间"→accept/reject 的 UX 链路是否打通未核查；② 访问码加入是否走房主审批（而非直接加入）未确认；③ owner 成员增删改查（含角色 owner/knowledge_admin/reviewer/member/guest）前端是否齐全未核查。
**优先级**：P2

### 3. [FEATURE/UX] 超管 Knowledge Base 页显示空间归属
**现状**：`/platform-admin` 有 Models 页（`ModelProfileListCreateView`），Knowledge 页是否按空间归属展示未确认；`Document.space` FK 已存在（`apps/knowledge/models.py`）。
**问题**：超管看不到某知识文档属于哪个空间（缺 space 列/筛选）。
**优先级**：P3

### 4. [DOC/UX] Scenario Templates 是干嘛用的？
**现状**：`apps.scenario_templates`（`/api/v1/templates/`）+ 前端 templates 控制台。
**问题**：用户不理解该功能用途；UI 未说明"模板=克隆起点"。
**优先级**：P3

### 5. [FEATURE] 发现工作空间：搜索 + 常用卡片 + 分类维度
**现状**：`GET /spaces/discoverable/`（`backend/apps/spaces/views.py:333`）无搜索/卡片化；空间模型只有 org + business_line，无"审计组别/团队"维度。
**问题**：① 发现页无搜索、无常用/热门卡片；② 缺"办公地点/业务线/审计组别（如 Assurance Group 12345）"分类维度；③ 新建空间时无对应组别/业务线选择器。
**优先级**：P2

### 6. [BUG] 访问码加入弹窗 close/cancel 关不掉 + 频繁切页加载失败
**现状**：访问码加入弹窗，点关闭/cancel 不消失；频繁切换功能页面时加载失败。
**问题**：弹窗关闭逻辑失效（state 未复位 / 关闭绑定缺失 / Popconfirm 嵌套）；切页加载失败（疑似 API 限流 login 5/min·send 10/min / React state race / SSE 未清理，待定位）。
**优先级**：P1
**复现待补**：需具体路径（哪个弹窗、切哪些页、报什么错）。

### 7. [DECISION] 模型策略：不暴露模型选择 + 独立思考开关
**决策（2026-07-18）**：
- 不暴露用户模型选择；
- 服务端内定两档模型：fast=qwen3.7-Flash、deep=qwen3.7-plus；
- 独立思考开关，默认**关闭**（fast/deep 两档均默认思考关）；
- 用户可见控制：fast/deep 模式切换 + 思考开关（on/off，默认 off）；模型由服务端按模式解析。

**现状代码**：
- fast/deep 选择器在 `frontend/src/components/chat/ChatComposer.tsx:91-114`（Deep 按 `canUseDeep` 显隐）；
- 模型服务端解析 `backend/apps/spaces/generation_policy.py`（fast 用 `RAG_LLM_MODEL`/ModelProfile，deep=qwen3.7-plus+thinking）；
- `seed_models` 现 seed fast=qwen-plus、deep=qwen3.7-plus（与决策不符，fast 应为 qwen3.7-Flash）。

**问题（待 SPEC 重写）**：
- SPEC §7 现"deep=思考开启、fast=思考关闭"与决策冲突——思考需与 deep 解耦（deep 仅=更强模型，思考=独立开关、默认 off、适用任一模式）；
- `DEEP_ANSWER_MODE`/`VITE_DEEP_ANSWER_MODE` 旧开关语义待重定义（原=deep 总开关）；
- 思考开关是否需独立 capability/flag 门禁未定。
**优先级**：P2

---

## 二、ZCode 额外发现的问题（来自本地验收）

### A. [CONFIG] `.env` `QWEN_CHAT_MODEL=qwen3.6-flash` 与 SPEC `qwen-plus` 不一致
**现状**：`.env:18` qwen3.6-flash；`generation_policy.py:50` fast 回退用 `settings.RAG_LLM_MODEL`（=qwen3.6-flash）；SPEC §7 fast=qwen-plus。未 seed ModelProfile 时 fast 解析为 qwen3.6-flash（非 SPEC）；`test_generation_policy` 在容器内因此失败（已证：`QWEN_CHAT_MODEL=qwen-plus` 覆盖后 6/6 过）。
**优先级**：P3

### B. [CONFIG] `CAPABILITY_NAV` 后端开关"已定义未接线"
**现状**：`config/settings/base.py:254` 定义，但 `apps/` 业务代码无任何读取点（仅 settings/tests）。服务端能力强制本就独立于此开关。
**优先级**：P3

### C. [UX] 登录后重定向总到 `/chat`，未用 `default_console`
**现状**：owner/超管登录均落 `/chat`，非 `default_console`（`/platform-admin`/`/workspace/:id/manage`）；capability 控制台需直接 URL 访问。
**优先级**：P3

### D. [PRODUCT] 超管无 `chat.*` 能力（非任何空间成员）
**现状**：超管 capabilities 仅 7 个 `platform.*`，无 `chat.ask`/`chat.history`——超管在 UI 不能直接对话（除非加入某空间 membership）。SPEC 未明确超管对话路径。
**优先级**：P3

### E. [CLEANUP] DB 残留 12 个历史 QA 超管
**现状**：`qa_admin_*@example.test`、`qa_ui_*` 等共 12 个 `is_superuser=True`（历史 QA 遗留）。
**优先级**：P3

### F. [PERF] 前端大 chunk
**现状**：`antd 1.18MB`（gzip 369KB）、`index 839KB`。
**优先级**：P3

### G. [TEST] 容器内 SQLite 子集 8 个环境性失败
**现状**：repo 根 `SPEC.MD`/前端 smoke 脚本不在 backend 容器；`.env` `QWEN_CHAT_MODEL` 覆盖 qwen-plus 默认。非回归，但易误导下一位开发。
**优先级**：P3

### H. [DOC] 仓库名不一致
**现状**：remote `Onborading-AI.git`，交接文档写 `KnowPliot.git`；原开发机路径 `D:\KnowPliot`，本机 `D:\Github\Onborading-AI`。
**优先级**：P3

### I. [SPEC-GAP] ownership-continuity 未实现
**现状**：`docs/superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md` 状态"设计已确认；尚未实现"。本清单第 1/2 条及"硬删除 workspace"与之共享基础设施。
**优先级**：P1

### J. [PRODUCT/UX] 前端未展示"已解析 model/mode/budget"
**现状**：SPEC §14.2 要求"UI 显示有效 model/mode/budget"；当前聊天页只显示 fast/deep 选择器，未见解析后的 `model_id`/budget 展示。
**优先级**：P3

---

## 三、开放问题（待决策）
1. 内测审批：方案 A（超管审批） vs 方案 B（信任制）选哪个？
2. **[已决 2026-07-18]** 不暴露用户模型选择；服务端内定 fast=qwen3.7-Flash / deep=qwen3.7-plus；独立思考开关默认关闭（fast/deep 均可开）。SPEC §7 需解耦 thinking 与 deep（原 deep=思考开启 → 新 deep=更强模型、思考=独立开关默认 off）。
3. 新 taxonomy（审计组别/团队）：加字段 vs tag？命名与 org/business_line 关系？
4. 第 6 BUG：需具体复现路径（哪个弹窗、切哪些页、报错）。
5. 超管对话路径（D）：platform authority 隐式 `chat.ask` 还是要求加入空间？
6. 访问码 vs 邀请码语义边界：访问码=需审批、邀请码=直接生效——是否确认？
