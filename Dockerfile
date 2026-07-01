# ===== frontend build stage =====
# Node / npm / node_modules（@playwright/test 等の devDependencies を含む）はビルドにしか
# 使わないため、最終イメージには含めない。以前は単一ステージで焼き込んでいたため、
# 実行時に不要な Node ツールチェーン一式（Playwright のブラウザバイナリ含む）が
# そのままイメージサイズに乗っていた。
FROM node:20-slim AS frontend-builder

# @playwright/test の postinstall によるブラウザダウンロードを止める
# （esbuild 等の他パッケージの postinstall はビルドに必要なため --ignore-scripts は使わない）
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ===== application image =====
FROM python:3.11-slim

EXPOSE 5000

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    curl \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install -r requirements.txt

WORKDIR /app

COPY . /app
COPY --from=frontend-builder /app/frontend/build /app/frontend/build

# Makefile から渡されるビルド情報で version.json を生成
ARG COMMIT_HASH=dev
ARG COMMIT_HASH_FULL=dev
ARG BRANCH=unknown
ARG COMMIT_DATE=unknown
ARG BUILD_DATE=unknown

RUN if [ "$BRANCH" = "main" ]; then VERSION="v${COMMIT_HASH}"; else VERSION="v${COMMIT_HASH}-${BRANCH}"; fi && \
    printf '{\n  "version": "%s",\n  "commit_hash": "%s",\n  "commit_hash_full": "%s",\n  "branch": "%s",\n  "commit_date": "%s",\n  "build_date": "%s"\n}\n' \
      "$VERSION" "$COMMIT_HASH" "$COMMIT_HASH_FULL" "$BRANCH" "$COMMIT_DATE" "$BUILD_DATE" \
    > shared/kernel/version.json

RUN chmod +x /app/scripts/entrypoint.sh
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# エントリポイントはイメージに焼き込む。compose 側で entrypoint を絶対パス指定すると
# パスのずれで `exec ... No such file or directory` を起こすため、起動方法はイメージを
# 唯一の出所とし、compose は command（web / worker / beat）でモードのみ指定する。
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["web"]
