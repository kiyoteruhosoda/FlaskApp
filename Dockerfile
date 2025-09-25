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

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# version.json を生成するために最低限必要なファイルだけ
COPY scripts/ ./scripts/
COPY core/ ./core/

ARG COMMIT_HASH=unknown
ARG COMMIT_HASH_FULL=unknown
ARG BRANCH=unknown
ARG COMMIT_DATE=unknown
ARG BUILD_DATE=unknown

RUN echo "{" \
        "\"version\": \"v${COMMIT_HASH}-${BRANCH}\"," \
        "\"commit_hash\": \"${COMMIT_HASH}\"," \
        "\"commit_hash_full\": \"${COMMIT_HASH_FULL}\"," \
        "\"branch\": \"${BRANCH}\"," \
        "\"commit_date\": \"${COMMIT_DATE}\"," \
        "\"build_date\": \"${BUILD_DATE}\"" \
    "}"> core/version.json



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

# --- アプリ本体のみに限定してコピー ---
COPY --chown=appuser:appuser wsgi.py ./wsgi.py
COPY --chown=appuser:appuser core/ ./core/
COPY --chown=appuser:appuser webapp/ ./webapp/
COPY --chown=appuser:appuser application/ ./application/
COPY --chown=appuser:appuser domain/ ./domain/
COPY --chown=appuser:appuser infrastructure/ ./infrastructure/
COPY --chown=appuser:appuser cli/ ./cli/

# version.json はビルダーで生成したものを上書きコピーする
COPY --from=builder --chown=appuser:appuser /app/core/version.json /app/core/version.json

RUN python -m compileall webapp/translations/ || true

RUN mkdir -p data/media data/thumbs data/playback data/local_import \
 && chown -R appuser:appuser data/

USER appuser

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:5000/health/live || exit 1

EXPOSE 5000
CMD ["gunicorn","--bind","0.0.0.0:5000","--workers","4","--timeout","120","--keep-alive","5","wsgi:app"]
