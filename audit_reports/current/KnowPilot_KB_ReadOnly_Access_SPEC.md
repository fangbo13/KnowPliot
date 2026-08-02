# KnowPilot 知识库访问权限 SPEC（修订版：Member 管理 / Guest 只读 / 默认 Guest）

> 版本：2026-07-29（在原"成员只读"SPEC 基础上按最终需求修订）
> 关联：`KnowPilot_V7_Identity_RBAC_Spec.md` §4.2

## 1. 背景与根因

原问题：普通空间成员看不到知识库 Local Graph。根因不在图谱 API（`/documents/graph/` 只验证空间成员身份，任何角色可调用），而在前端知识库页面路由被 `knowledge.read` 能力门控，而该能力此前只发给 owner/knowledge_admin。

## 2. 目标权限矩阵（最终态）

| 能力 \ 角色 | Owner | Knowledge Admin | Reviewer | Member | Guest |
|---|:--:|:--:|:--:|:--:|:--:|
| knowledge.read（进知识库页/图谱/时间线/文档浏览） | ✅ | ✅ | ✅ 新增 | ✅ 新增 | ✅ 新增 |
| knowledge.manage（上传/编辑/删除/归档/标签/批量） | ✅ | ✅ | ❌ | ✅ **新增** | ❌ |
| knowledge.index（重建索引按钮） | ✅ | ✅ | ❌ | ❌ | ❌ |
| knowledge.download（下载原文件） | ✅ | ✅ | ❌ | ❌ | ❌ |
| Dashboard/Review 标签页（quality.read/review） | ✅ | ✅ | ✅ | ❌ | ❌ |

**默认角色**：所有"首次进入空间"路径（模型默认值、加入码、发现直加、发现申请、邀请码默认、按邮箱添加默认、默认空间兜底、注册落位）一律默认 **Guest**；管理员/Owner 仍可显式指定更高角色。

## 3. 改动清单

### 后端
| 文件 | 改动 |
|---|---|
| `apps/rbac/capabilities.py` | guest += knowledge.read；member += knowledge.read + knowledge.manage；reviewer += knowledge.read |
| `apps/spaces/permissions.py` | ROLE_PERMISSIONS member += DOCUMENT_UPLOAD/UPDATE/DELETE（与 knowledge.manage 对齐，服务端真实放行） |
| `apps/spaces/models.py` | SpaceMembership.role 默认值 member → guest（迁移 0022_alter_spacemembership_role） |
| `apps/spaces/join_services.py` | 加入码/发现直加/发现申请三处默认角色 → guest |
| `apps/spaces/serializers.py` | InviteCodeCreate / AddMemberByEmail 默认角色 → guest |
| `apps/spaces/views.py` `ensure_default_membership` | 默认空间兜底 → guest |
| `apps/spaces/services.py` 注册落位 | → guest |

### 前端
| 文件 | 改动 |
|---|---|
| `auth/NavigationRouting.tsx` | `/console` 门控 knowledge.read → knowledge.manage（防 Guest 只读者进控制台） |
| `pages/console/ConsoleHubPage.tsx` | 知识库入口卡片同上 |
| `pages/admin/KnowledgeBasePage.tsx` | 标签页按能力过滤（review→quality.review、dashboard→quality.read、taxonomy→canManage）；无 manage 显示只读提示横幅 |
| i18n zh/en common.json | 新增 `kb_readonly_notice` |

## 4. 写接口服务端防线核查表（对 Guest/Reviewer 只读生效）

| 端点 | 防线 | Guest 结果 |
|---|---|---|
| POST/PUT/PATCH/DELETE /documents/ | SpaceDocumentPermission → upload/update/delete 码 | 403 |
| /documents/{id}/reindex/ | SpaceDocumentPermission（POST→upload） | 403 |
| /documents/{id}/text|preview-diff|versions|rollback | `_get_editable_document` → DOCUMENT_UPDATE | 403 |
| /documents/batch/upload/ | SpaceDocumentPermission | 403 |
| /documents/{id}/tags/ PUT | has_space_permission(DOCUMENT_UPDATE) | 403 |
| /documents/{id}/confirm-fresh/ | has_space_permission(DOCUMENT_UPDATE) | 403 |
| taxonomy dimensions/terms/seed POST/PATCH | `_require_taxonomy_admin` | 403 |
| reviews approve/reject | REVIEWER_ROLES 白名单 | 403 |
| library-references POST/PATCH/DELETE | `_require_space_library_admin` | 403 |
| /documents/graph/、/timeline/、chunks GET | 空间成员即可 | 200 ✅ |
| /documents/dashboard/ | DASHBOARD_ROLES（owner/ka/reviewer） | 403 |

注：Member 现持有 upload/update/delete 服务端权限，上表 403 项对 Member 变为 200/放行（reindex 经 POST→upload 映射亦放行，但 UI 仅对 knowledge.index 角色显示按钮）。

## 5. 测试与验收

- `apps/rbac/test_capabilities.py`：guest={chat.ask, knowledge.read}；member 含 knowledge.read+manage；reviewer 含 knowledge.read（已更新，通过）
- `apps/spaces/tests.py`：member 可上传、guest 上传 403（已更新，通过）
- 存量无关失败（记录在案）：`_search_sqlite space_id` 参数漂移、`WORKSPACE_PERMANENT_DELETE` 环境开关导致的 owner 断言差异 — 均先于本次改动存在
- 浏览器 E2E：Guest 视角进入知识库页看 Local Graph、无管理按钮；Member 视角可见上传/编辑
