# ========= ビルドステージ =========
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ビルドに必要なツール/ヘッダ（wheel作成用）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    git \
  && rm -rf /var/lib/apt/lists/*

# 依存関係（グローバルにインストール）← 重要：--user を使わない
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリコードをコピーしてバージョンファイルを生成
COPY . .
RUN if [ -d .git ]; then \
      ./scripts/generate_version.sh; \
    else \
      echo '{"version":"docker-build","commit_hash":"unknown","branch":"unknown","commit_date":"unknown","build_date":"'$(date -Iseconds)'"}' > core/version.json; \
    fi


# ========= 実行ステージ =========
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=wsgi.py \
    FLASK_ENV=production \
    PYTHONPATH=/app

WORKDIR /app

# 実行時に必要なランタイムライブラリのみ
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    curl \
    procps \
  && rm -rf /var/lib/apt/lists/*

# 任意：ホストのUID/GIDに合わせたい場合に使える引数（デフォルト1000）
ARG APP_UID=1000
ARG APP_GID=1000

# 非rootユーザー作成
RUN groupadd -g ${APP_GID} -r appuser \
 && useradd  -u ${APP_UID} -r -g appuser appuser

# ビルド済みのPython環境を丸ごとコピー（/usr/local）
# これで gunicorn を含む全パッケージが全ユーザーで見える
COPY --from=builder /usr/local /usr/local

# アプリ本体とバージョンファイル
COPY --chown=appuser:appuser . .
COPY --from=builder --chown=appuser:appuser /app/core/version.json /app/core/version.json

# 翻訳ファイルをコンパイル（無ければスキップ）
RUN python -m compileall webapp/translations/ || true

# データディレクトリ（本番環境用）
RUN mkdir -p data/media data/thumbs data/playback data/local_import \
 && chown -R appuser:appuser data/

USER appuser

# ヘルスチェック（curl 利用）
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:5000/health/live || exit 1

EXPOSE 5000

# Gunicornで起動（requirements に gunicorn を入れておく）
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--keep-alive", "5", "wsgi:app"]
