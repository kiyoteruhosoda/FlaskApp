# マルチステージビルドで本番環境用Dockerfile
# ビルドステージ
FROM python:3.11-slim as builder

WORKDIR /app

# システムの依存関係をインストール（ビルド用）
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Python依存関係をインストール
COPY requirements-prod.txt .
RUN pip install --no-cache-dir --user -r requirements-prod.txt

# 本番ステージ
FROM python:3.11-slim

WORKDIR /app

# 非rootユーザーを作成
RUN groupadd -r appuser && useradd -r -g appuser appuser

# システムの依存関係をインストール（実行用のみ）
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# ビルドステージからPythonパッケージをコピー
COPY --from=builder /root/.local /home/appuser/.local

# アプリケーションファイルをコピー
COPY --chown=appuser:appuser . .

# 翻訳ファイルをコンパイル
RUN python -m compileall webapp/translations/ || true

# 環境変数を設定
ENV FLASK_APP=wsgi.py
ENV FLASK_ENV=production
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app

# データディレクトリを作成
RUN mkdir -p data/media data/thumbs data/playback && \
    chown -R appuser:appuser data/

# 非rootユーザーに切り替え
USER appuser

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# ポートを公開
EXPOSE 5000

# アプリケーションを起動
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--keep-alive", "5", "wsgi:app"]
