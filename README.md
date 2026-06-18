# EY Onboarding AI — 新员工入职 Chatbot

> RAG 驱动的 AI Chatbot，帮助 EY 新员工快速获取入职相关信息。

## Tech Stack

- **Backend**: Django 5.0 + DRF + Celery + Redis
- **Frontend**: React 18 + TypeScript + Vite + Ant Design 5 + Zustand
- **LLM**: Qwen 3.6 via DashScope API (OpenAI 兼容协议)
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
# 前端: http://localhost:3000
# 后端 API: http://localhost:8000/api/v1/
# Django Admin: http://localhost:8000/admin/
```

## Project Structure

```
├── backend/              # Django 后端
│   ├── config/           # 项目配置 (settings, urls, celery)
│   └── apps/             # Django apps (core, users, chat, knowledge, rag, audit)
├── frontend/             # React 前端
│   └── src/              # 源码 (components, pages, store, api, hooks, i18n)
├── docker-compose.yml    # 开发环境
└── .env.example          # 环境变量模板
```

## License

Internal use only — EY Confidential
