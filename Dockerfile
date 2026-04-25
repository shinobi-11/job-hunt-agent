FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

RUN playwright install chromium && \
    playwright install-deps chromium


FROM base AS development

RUN pip install -e ".[dev]"

COPY . .

RUN mkdir -p /app/data && chmod 755 /app/data

CMD ["python", "agent.py"]


FROM base AS production

COPY models.py database.py matcher.py searcher.py cli.py \
     resume_parser.py agent.py ./
COPY .env.example ./.env.example

RUN mkdir -p /app/data && chmod 755 /app/data

RUN groupadd -r jobagent && useradd -r -g jobagent -m jobagent && \
    chown -R jobagent:jobagent /app
USER jobagent

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('/app/data/jobs.db').execute('SELECT 1')" || exit 1

CMD ["python", "agent.py"]
