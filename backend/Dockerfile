FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install runtime dependencies (V4.1 SYS-V4.1-011: added ca-certificates for HTTPS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_TRUSTED_HOST=mirrors.tuna.tsinghua.edu.cn
ENV PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/

# Install Python dependencies
# psycopg[binary] and pgvector have pre-built wheels, no compilation needed
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY . .

RUN mkdir -p /app/media

EXPOSE 8000

# V4.6: gunicorn (threaded workers) instead of runserver — serves concurrent SSE
# chat streams without blocking. docker-compose overrides this with --reload for dev.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "8", "--worker-class", "gthread", "--timeout", "120"]
