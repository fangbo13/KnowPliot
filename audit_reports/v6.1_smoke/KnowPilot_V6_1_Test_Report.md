# KnowPilot V6.1 多空间与爬虫移除功能测试报告

> 测试日期：2026-06-29  
> 测试范围：Claude 实现后的“统一平台 + 多业务线 / 多知识空间”能力、访问码加入、空间级隔离、爬虫功能移除、前端构建与浏览器烟测。  
> 测试环境：Windows + Docker Compose，本地服务 `backend:8000`、`frontend:3003`、PostgreSQL/pgvector、Redis。  

## 1. 总结

本轮测试结论：**核心功能通过，可以继续进入下一轮更完整 UAT。**

已验证通过：

- 后端多空间隔离单元测试：18/18 通过。
- 前端 Vitest：36/36 通过。
- 前端 TypeScript 类型检查：通过。
- 前端 production build：通过。
- 真实 API 烟测：登录、创建空间、生成访问码、加入空间、创建空间内会话、成员上传文档被拒、爬虫接口 404 均符合预期。
- 浏览器烟测：登录成功进入 `/chat`，空间管理页可打开，无 crawler/crawl 菜单文案，无 console/page error。

需要关注：

- `npm run check:i18n` 失败，报告 152 个 missing keys。但其中大量是 API 路径、CSS selector、测试描述被误判为翻译 key，疑似检查脚本规则过宽；仍建议单独治理。
- Django `manage.py check` 有 3 个 `django-allauth` 废弃配置 warning，不阻塞功能。
- 本机通过 `localhost:8000` 访问曾出现连接不稳定，改用 `127.0.0.1:8000` 后稳定。建议本地文档统一使用 `127.0.0.1` 或排查 Windows/IPv6 localhost 解析。
- 前端 Dockerfile 依赖本地 `frontend/dist`，测试最新 UI 前必须先 `npm run build` 再 `docker compose build frontend`。

## 2. 测试命令与结果

| 类别 | 命令 | 结果 |
| --- | --- | --- |
| 后端多空间定向测试 | `docker compose exec -T backend python manage.py test apps.spaces --settings=config.settings.test -v 2` | 通过，18 tests OK |
| Django system check | `docker compose exec -T backend python manage.py check` | 通过，有 3 个 allauth deprecated warnings |
| 前端类型检查 | `npm run typecheck` | 通过 |
| 前端单元测试 | `npm test -- --run` | 通过，2 files / 36 tests |
| 前端构建 | `npm run build` | 通过，有 chunk size warning |
| i18n 检查 | `npm run check:i18n` | 失败，152 missing keys |
| 前端镜像构建 | `docker compose build frontend` | 通过 |
| 前端页面探测 | `curl http://127.0.0.1:3003/` | 200 |
| 后端 crawler endpoint | `GET /api/v1/crawl/` | 404，符合“爬虫移除”预期 |

## 3. 后端功能验证

### 3.1 自动化测试覆盖

`apps.spaces.tests` 覆盖以下关键点，全部通过：

- `DocumentIsolationTest`
  - 文档列表按 active space 隔离。
  - 跨空间文档详情返回 404。
- `SessionIsolationTest`
  - 会话列表按 active space 隔离。
  - 普通用户只能看到加入的空间。
- `AccessCodeTest`
  - 访问码可加入空间。
  - 访问码只授予 membership role，不绕过 RBAC。
  - 无效/吊销访问码被拒。
- `PermissionMatrixTest`
  - owner/member/guest 权限矩阵符合预期。
  - 无 membership 无访问权限。
  - platform admin 可访问全局。
- `RetrievalIsolationTest`
  - RAG retriever 只返回当前 `space_id` 下的 chunks。
- `CrawlerRemovedTest`
  - `/api/v1/crawl/` 返回 404。
- `DocumentPermissionTest`
  - member 不能上传文档。
  - knowledge_admin 只在自己空间具备上传权限。
- `OrgBusinessAdminTest`
  - org admin 覆盖组织下空间。
  - business admin 只覆盖所属业务线。
  - org admin 可创建空间。

### 3.2 API 烟测

真实服务 API 验证结果：

```json
{
  "admin_login": true,
  "member_login": true,
  "space_created": true,
  "invite_joined": true,
  "joined_space_visible_to_member": true,
  "session_created": true,
  "session_listed_in_space": true,
  "member_document_create_status": 403,
  "crawler_endpoint_status": 404
}
```

结论：

- Admin 可以创建 space。
- Admin 可以生成 access code。
- Member 可以通过 access code 加入 space。
- Member 加入后能看到该 space。
- Member 可以在该 space 创建 chat session。
- Member 不具备文档上传权限时，文档创建返回 403。
- 爬虫入口 `/api/v1/crawl/` 返回 404，符合需求。

## 4. 前端验证

### 4.1 构建与测试

前端 `typecheck`、Vitest、production build 均通过。

build warning：

- `antd` chunk 大于 500 kB。
- `src/i18n/index.ts` 同时被动态和静态导入，无法单独切 chunk。

这些属于性能/打包优化提示，不阻塞当前功能。

### 4.2 浏览器烟测

使用 Puppeteer 验证：

- `/login` 可正常打开。
- 使用 QA 超级用户登录成功。
- 登录后跳转到 `/chat`。
- 页面能加载空间切换入口。
- `/spaces/manage` 可直接打开。
- 空间设置、成员列表可见。
- 页面正文未出现 `crawler` / `crawl` / `web collection` 文案。
- console error：0。
- page error：0。

截图证据：

- `audit_reports/v6.1_smoke/screenshots/01-login.png`
- `audit_reports/v6.1_smoke/screenshots/02-after-login.png`
- `audit_reports/v6.1_smoke/screenshots/03-space-management.png`
- `audit_reports/v6.1_smoke/screenshots/04-space-management-unblocked.png`

说明：首次登录会弹出 onboarding modal，会遮挡页面。关闭后空间管理页可正常操作。

## 5. 爬虫移除验证

已确认：

- `backend/config/urls.py` 不再 include `apps.crawler.urls`。
- `GET /api/v1/crawl/` 返回 404。
- 前端 `App.tsx` 中 crawler admin route 已移除。
- `AppLayout.tsx` 中 crawler menu item 已移除。
- 浏览器页面中未发现 crawler/crawl 入口文案。
- `README.md` 与 `KnowPilot.md` 已明确“当前版本不支持 Web 爬虫采集”。
- `SPEC.MD` 已将爬虫章节改为 removed 状态。

保留项：

- `backend/apps/crawler/` 代码与 migration 仍存在。
- `audit` action choices 仍保留 crawler 历史枚举。

判断：这与需求中的“可保留历史表但不暴露 API”一致。当前测试未发现可访问的爬虫功能入口。

## 6. 发现的问题与建议

### P2 - i18n 检查脚本误报严重

现象：

- `npm run check:i18n` 失败，报告 152 个 missing keys。
- 误报包括：
  - API 路径：`/chat/sessions/`、`/spaces/`、`/documents/`
  - CSS selector：`.ant-input-affix-wrapper`
  - import 路径：`../i18n`
  - 测试描述文本

影响：

- CI 若启用该检查会失败。
- 真正缺失的翻译 key 会被大量噪声淹没。

建议：

- 修改 `frontend/scripts/check-i18n.cjs`，只识别 `t('...')` / `t("...")` 等明确翻译调用。
- 排除 `__tests__`、API client URL、CSS selector、import path。
- 再补齐真实缺失的 key。

### P3 - 本地 `localhost:8000` 访问不稳定

现象：

- `localhost:8000` 曾出现 `curl` 超时或 HTTP code `000`。
- `127.0.0.1:8000` 稳定返回：
  - `/api/v1/spaces/` 未登录为 401。
  - `/api/v1/crawl/` 为 404。

影响：

- Windows 本地测试时可能误判服务不可用。

建议：

- README 的本地测试 URL 可补充 `127.0.0.1` fallback。
- 如需彻底解决，排查 Windows hosts、IPv6 `::1`、Docker Desktop 端口映射。

### P3 - Django allauth deprecated warnings

现象：

`manage.py check` 提示：

- `ACCOUNT_AUTHENTICATION_METHOD` deprecated。
- `ACCOUNT_EMAIL_REQUIRED` deprecated。
- `ACCOUNT_USERNAME_REQUIRED` deprecated。

影响：

- 当前不阻塞运行。
- 后续 allauth 升级可能需要迁移配置。

建议：

- 按 warning 改为：
  - `ACCOUNT_LOGIN_METHODS = {'email'}`
  - `ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']`

### P3 - 前端首登 onboarding modal 会遮挡空间管理页

现象：

- 第一次登录进入 `/chat` 或 `/spaces/manage` 时会弹出 Welcome modal。
- modal 关闭后页面可正常使用。

影响：

- 不算功能 bug，但空间管理页首次进入时会被遮挡，管理操作需要先关闭引导。

建议：

- 管理页可考虑不触发 onboarding modal，或仅在 Chat 首页触发。

## 7. 风险评估

| 风险项 | 结论 |
| --- | --- |
| 多空间基础模型 | 通过 |
| 访问码加入空间 | 通过 |
| 访问码绕过权限 | 未发现，测试覆盖通过 |
| 文档跨空间泄漏 | 未发现，测试覆盖通过 |
| 会话跨空间泄漏 | 未发现，测试覆盖通过 |
| RAG 跨空间检索 | 未发现，测试覆盖通过 |
| 爬虫 API 暴露 | 未发现，`/api/v1/crawl/` 为 404 |
| 前端构建 | 通过 |
| 前端运行时错误 | 浏览器烟测 0 error |
| i18n 检查 | 不通过，需要治理脚本/翻译 key |

## 8. 结论

Claude 本次实现的核心目标基本达成：

- KnowPilot 已从单一知识库形态扩展为多空间平台。
- 文档、会话、RAG 检索、访问码与权限隔离已有测试覆盖。
- 爬虫功能已从主路由和前端入口移除。
- 前端可以构建并完成登录与空间管理页烟测。

建议下一步：

1. 修复 i18n 检查脚本误报。
2. 做一次更完整的 UI UAT：空间切换、访问码弹窗、成员管理、普通用户与管理员视角差异。
3. 针对真实文档上传和 RAG 问答做端到端测试，包括引用是否严格限定在当前 space。
4. 清理或归档历史 crawler 代码，避免后续开发者误以为功能仍可启用。
