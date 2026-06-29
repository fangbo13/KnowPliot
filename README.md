# KnowPilot — 知识库应用 Agent

> RAG 驱动的知识库应用 Agent，面向专业服务团队沉淀、检索和复用组织知识。

**当前版本：V6.1**

> **V6.1 更新**：在 V6.0 多空间基础上补全 —— 组织/业务线管理员角色（Org Admin / Business Admin）、文档管理改为空间级权限（空间 owner / knowledge_admin 管理本空间文档）、空间管理页（成员 + 访问码生成/吊销 + 设置），并移除 Web 爬虫入口。相关文档见 [SPEC.MD](SPEC.MD)、[V6 优化设计文档](audit_reports/KnowPilot_V6_Optimization_Design.md) 与 [V6.1 测试报告](audit_reports/v6.1_smoke/KnowPilot_V6_1_Test_Report.md)。

KnowPilot 原名 **EY Onboarding AI / onboardingai**。项目定位已从“新员工入职 Chatbot”升级为“组织级知识库应用 Agent”：用户可以上传文档、维护知识库、通过对话获取带来源引用的答案，并在同一平台覆盖入职培训、审计方法论、准则问答、项目经验沉淀、风险识别、底稿编制与合规检查等场景。

KnowPilot 主要解决三类问题：一是专业知识分散在手册、PDF、内网和个人经验中，查找成本高；二是同一问题依赖口口相传，答案口径容易不一致；三是项目经验跟着人员流动而流失，难以沉淀为组织资产。通过 RAG 检索、来源引用、知识库管理和权限审计，KnowPilot 把分散知识转化为可对话、可追溯、可持续更新的团队知识资产。

从推广角度看，KnowPilot 具备较强可复制性：同一套知识库 Agent 引擎可以按团队、业务线或项目空间复用，只需替换和维护知识库内容，即可从入职问答扩展到审计准则、方法论查询、项目经验库、风险识别等场景。验证一个团队后，可以低成本推广到更多团队，边际部署成本低，ROI 易于说明。

核心能力：

- **知识问答 Agent**：基于 RAG 检索增强生成，回答时附带来源引用，降低幻觉与口径不一致。
- **知识库管理**：支持文档上传、重新索引、删除和状态追踪；**当前版本不支持 Web 爬虫采集**，历史 crawler 表/代码仅作为兼容保留，不暴露 API 或前端入口。
- **多空间隔离（V6.1）**：同一站点内承载多个业务空间（组织 / 业务线 / 知识空间）。用户登录后进入默认空间，可通过空间切换器或访问码（access code）进入不同空间；文档、会话、检索、引用、审计均按 `space_id` 隔离，互不可见。
- **空间级治理**：支持 Space Owner、Knowledge Admin、Reviewer、Member、Guest，以及 Organization Admin / Business Admin 上级管理角色。
- **多场景复用**：同一套知识引擎可服务不同团队、业务线和知识空间。
- **管理与合规**：提供认证、权限控制、审计日志、系统监控与可追溯操作记录。
- **可持续扩展**：Django + React + pgvector + Celery 架构，支持后续扩展多知识库、多角色和更细粒度权限。

## Tech Stack

- **Backend**: Django 5.0 + DRF + Celery + Redis
- **Frontend**: React 18 + TypeScript + Vite + Ant Design 5 + Zustand
- **LLM**: Qwen via DashScope API (OpenAI 兼容协议)
- **Embeddings**: Qwen text-embedding-v4 (1024-dim)
- **Vector DB**: pgvector (PostgreSQL 16)
- **RAG**: LangChain + Docling

## Quick Start

```bash
# 1. 复制环境变量
cp .env.example .env
# 编辑 .env 填入 DASHSCOPE_API_KEY

# 2. 启动全栈
docker compose up --build

# 3. 数据库迁移
docker compose exec backend python manage.py migrate

# 4. 创建超级用户
docker compose exec backend python manage.py createsuperuser

# 5. 访问
# 前端: http://127.0.0.1:3003
# 后端 API: http://127.0.0.1:8000/api/v1/
# Django Admin: http://127.0.0.1:8000/admin/
```

> Windows / Docker Desktop 环境下，如 `localhost:8000` 偶发连接不稳定，优先使用 `127.0.0.1:8000`。

### Frontend Rebuild Note

当前 `frontend/Dockerfile` 默认使用本机已生成的 `frontend/dist`。如果修改了前端代码，需要先在宿主机重新构建，再重建前端镜像：

```bash
cd frontend
npm run build
cd ..
docker compose build frontend
docker compose up -d frontend
```

## Verification

V6.1 多空间与爬虫移除功能已完成一轮 smoke test，详细结果见：

- [KnowPilot V6.1 多空间与爬虫移除功能测试报告](audit_reports/v6.1_smoke/KnowPilot_V6_1_Test_Report.md)

已验证通过：

- 后端多空间隔离测试：`18/18` 通过。
- 前端 Vitest：`36/36` 通过。
- 前端 TypeScript typecheck：通过。
- 前端 production build：通过。
- API smoke test：登录、创建空间、生成访问码、加入空间、空间内会话、成员上传文档被拒、crawler endpoint `404`。
- 浏览器 smoke test：登录进入 `/chat`，空间管理页可打开，无 crawler/crawl 菜单文案，console/page error 为 `0`。

当前已知注意事项：

- `npm run check:i18n` 仍会失败，主要因为检查脚本把 API 路径、CSS selector、测试描述误判为翻译 key；建议后续修正 `frontend/scripts/check-i18n.cjs`。
- Django `manage.py check` 有 3 个 `django-allauth` deprecated warnings，不阻塞当前功能。
- 首次登录会弹出 onboarding modal，可能遮挡空间管理页；关闭后可正常操作。

## Project Structure

```
├── backend/              # Django 后端
│   ├── config/           # 项目配置 (settings, urls, celery)
│   └── apps/             # Django apps (core, users, spaces, chat, knowledge, rag, audit, rbac)
├── frontend/             # React 前端
│   └── src/              # 源码 (components, pages, store, api, hooks, i18n)
├── KnowPilot.md          # 产品定位与应用场景说明
├── SPEC.MD               # V6.1 多空间架构与功能规格
├── audit_reports/        # 功能模块、审计、修复与验收文档
├── docker-compose.yml    # 开发环境
└── .env.example          # 环境变量模板
```

## License

Internal use only — EY Confidential
