FROM python:3.11-slim

EXPOSE 5000

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install -r requirements.txt

WORKDIR /app

COPY frontend/package*.json ./frontend/
RUN cd frontend && npm ci

COPY . /app

RUN cd frontend && npm run build

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
