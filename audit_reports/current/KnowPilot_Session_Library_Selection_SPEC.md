# KnowPilot 会话级引用库选择与加载动画优化 SPEC

状态：Draft → 实施中
适用范围：聊天问答（Fast / Deep 模式）、工作区创建、参考库调用
关联记忆：会话长短期记忆系统、记忆系统前端体验优化需求

## 1. 背景与目标

当前参考库（Reference Library）调用完全由后端自动决定：空间级 opt-in（`SpaceLibraryReference`）+ 查询关键词路由（`route_reference_libraries`）。前端仅有只读 chips 展示，用户无法在对话入口自行决定"本次会话引用哪些公开库"。

目标：
1. 让用户在**每个 session** 自主勾选引用哪些已发布公开库。
2. 按回答模式限制同时引用的库数量：**Fast 最多 1 个、Deep 最多 3 个**（本空间自身知识库始终检索，不计入上限）。
3. 超上限时禁止勾选并弹出友好提示，支持"不再提示"（localStorage 持久化）。
4. 工作区创建流程支持 opt-in 参考库，形成该空间的可选库池。
5. 优化加载动画：三点顺序跳动 + 客户端循环阶段文案，与后端真实 phase 解耦。

## 2. 核心决策

| 项 | 决策 |
| --- | --- |
| Fast 上限 | 1 个引用库 |
| Deep 上限 | 3 个引用库 |
| 新会话默认 | 空集合（仅检索本空间） |
| 选择权威性 | 会话有显式选择时按该集合检索（跳过关键词路由）；无记录（null）时回退自动路由 |
| 持久化 | 规范集合存 `ChatSession.reference_library_ids`；每轮快照存 `ChatTurn.reference_library_ids` |
| 总开关 | `CHAT_SESSION_LIBRARY_SELECTION_ENABLED`（默认 True） |

## 3. 数据模型

### ChatSession（新增）
- `reference_library_ids: JSONField(null=True, blank=True, default=None)`
  - `None`：会话从未经过选择器（老会话/未传字段）→ 回退关键词自动路由。
  - `[]`：用户显式选择"不引用任何公开库"→ 只搜本空间。
  - `[uuid, ...]`：用户显式选择的库 id 列表（去重、已按写入时校验）。

### ChatTurn（新增）
- `reference_library_ids: JSONField(default=list)`：本轮实际使用的参考库 id 快照（已按当前模式上限截断），供 Celery v3 路径与审计使用。

## 4. API 契约

### POST /api/v1/chat/sessions/{id}/send/（及 regenerate）
请求体新增可选字段：
- `selected_library_ids: list[UUID]`（可选）。不传该字段 → session 选择状态保持不变（保留 null 回退语义）。

服务端处理：
1. 仅接受"本 space 已 opt-in 且 `library.status=published`"的库 id；非法/未 opt-in/未发布项静默剔除。
2. 按 `requested_answer_mode` 取上限（fast=`CHAT_LIBRARY_MAX_FAST`，deep=`CHAT_LIBRARY_MAX_DEEP`）；超限保留前 N，不硬失败。
3. 传入字段时：写入 `session.reference_library_ids`（规范集合）并快照到 `turn.reference_library_ids`；未传时不改动 session，turn 快照沿用 session 现值（null→自动路由）。

错误码：本特性不新增硬失败错误码；非法项走"静默剔除 + 截断"策略以保证鲁棒性。

### 工作区创建 POST（creation_services / ownership）
- 请求体可选 `reference_library_ids: list[UUID]`：创建成功后为每个已发布库建立 `SpaceLibraryReference(enabled=True)`，形成空间可选库池。

## 5. 检索链路

`pipeline.retrieve_and_generate(..., selected_library_ids)`：
- `selected_library_ids is not None`（含空表）→ 调 `resolve_selected_libraries(active_space, selected_library_ids, max_count)`：
  - 仅解析本 space 已 opt-in 且已发布的库，按 `max_count` 截断，返回 (space_ids, name_by_space)。
  - **跳过** `route_reference_libraries` 关键词过滤。
  - 空表 → 无参考库，仅检索本空间。
- `is None` → 现有 `route_reference_libraries` 自动路由（向后兼容）。

`max_count` 由 turn.answer_mode 决定（fast/deep）。

## 6. 前端交互

### 引用库选择器（ChatComposer 模式工具条）
- 入口按钮"引用库"，点击弹出多选层；选项来自 `libraryApi.getReferences()`（本空间已 opt-in 已发布库）。
- 上限随 `answerMode` 动态变化（fast=1 / deep=3）；达上限后其余选项禁用。
- 首次达上限或切换模式导致超限时弹 `Modal` 友好提示，含"不再提示"复选框，写 `localStorage: kp.libpicker.hideCapNotice`。
- 新会话默认空选；切换会话重置为空。
- 切换 Fast/Deep 若当前选择数超新上限 → 自动截断到上限并提示。

### 加载动画
- 三点顺序跳动（CSS `@keyframes`，`animation-delay` 0 / 0.16 / 0.32s）。
- 阶段文案客户端定时循环（约 1.6s），文案：理解问题中 → 调用知识库检索 → 结合上下文分析 → 正在组织答案；与后端 phase 解耦。
- 保留 sr-only 无障碍播报。

## 7. 配置项（settings/base.py）
- `CHAT_LIBRARY_MAX_FAST`（默认 1）
- `CHAT_LIBRARY_MAX_DEEP`（默认 3）
- `CHAT_SESSION_LIBRARY_SELECTION_ENABLED`（默认 True）；关闭后 send_message 忽略 `selected_library_ids`，管线回退自动路由。

## 8. 向后兼容
- 未传 `selected_library_ids` 或总开关关闭 → 行为与现状一致（自动路由 + 静态动画）。
- 老会话 `reference_library_ids=None` → 自动路由。
- 分支会话：默认继承源会话选择快照（首版从简）。

## 9. 验收标准
- Fast 模式最多 1 个库、Deep 最多 3 个库；超限禁止勾选且弹提示、可"不再提示"。
- 新会话默认不引用公开库，只搜本空间。
- 显式选择后 citations 的 `source_library` 只出现在所选库范围内。
- 三点顺序跳动 + 阶段文案循环切换。
- 50-80 轮真人对话（Fast/Deep × 有效/无效回复）通过率报告。

## 10. 测试矩阵
| 层 | 用例 |
| --- | --- |
| 序列化器 | selected_library_ids 非法/未 opt-in/未发布被剔除 |
| send_message | fast 超 1 截断、deep 超 3 截断；未传字段 session 保持 null |
| pipeline | 显式空集合→无参考库；显式集合→跳过路由+截断；None→自动路由 |
| 创建 | 带 reference_library_ids 建立 SpaceLibraryReference |
| E2E | 从 0 建库 + 50-80 轮（逻辑/打岔/澄清）+ 动画 + 选择器 |
