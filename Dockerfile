# ===== ベースを可変に =====
ARG BUILDER_BASE=public.ecr.aws/docker/library/python:3.11-slim
ARG RUNTIME_BASE=public.ecr.aws/docker/library/python:3.11-slim

# ========= ビルドステージ =========
FROM ${BUILDER_BASE} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    git \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN if [ -d .git ]; then \
      ./scripts/generate_version.sh; \
    else \
      echo '{"version":"docker-build","commit_hash":"unknown","branch":"unknown","commit_date":"unknown","build_date":"'$(date -Iseconds)'"}' > core/version.json; \
    fi

# ========= 実行ステージ =========
FROM ${RUNTIME_BASE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=wsgi.py \
    FLASK_ENV=production \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    curl \
    procps \
  && rm -rf /var/lib/apt/lists/*

ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} -r appuser \
 && useradd  -u ${APP_UID} -r -g appuser appuser

COPY --from=builder /usr/local /usr/local

COPY --chown=appuser:appuser . .
COPY --from=builder --chown=appuser:appuser /app/core/version.json /app/core/version.json

RUN python -m compileall webapp/translations/ || true

RUN mkdir -p data/media data/thumbs data/playback data/local_import \
 && chown -R appuser:appuser data/

USER appuser

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:5000/health/live || exit 1

EXPOSE 5000
CMD ["gunicorn","--bind","0.0.0.0:5000","--workers","4","--timeout","120","--keep-alive","5","wsgi:app"]
