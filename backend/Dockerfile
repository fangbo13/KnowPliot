FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install only runtime dependencies (no build-essential to save memory)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
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

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
