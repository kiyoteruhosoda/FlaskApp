#!/bin/bash
# STG デプロイスクリプト
# 使い方:
#   ./scripts/deploy-stg.sh          # 通常デプロイ
#   ./scripts/deploy-stg.sh reset    # 完全初期化（DB・メディアデータ消去）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_ROOT="$(dirname "$SCRIPT_DIR")"

PROJECT="photonest-stg"
BASE_DIR="$DOCKER_ROOT/photonest-stg"
COMPOSE_FILE="$BASE_DIR/docker-compose.yml"
ENV_FILE="$BASE_DIR/.env"
IMAGE_TAR="$DOCKER_ROOT/photonest-latest.tar"
IMAGE_DB_TAR="$DOCKER_ROOT/photonest-db-latest.tar"
HEALTH_URL="http://127.0.0.1:8051/health/live"
DATA_PATH="$BASE_DIR/data"
DB_PATH="$BASE_DIR/db_data"

MODE="${1:-deploy}"

echo -e "\033[36m[deploy-stg] Photonest STG deploy start (mode: $MODE)\033[0m"

# ===== Load a docker image tar with visible progress =====
# `docker load` は標準では進捗を表示せず、大きいイメージだと数分間無反応に見える。
# `pv` があれば転送量・速度・経過時間を表示し、なければ一定間隔でハートビートを出して
# 「止まっているように見えるが実行中」であることが分かるようにする。
load_image_with_progress() {
  local tar="$1"
  local size_human
  size_human="$(du -h "$tar" 2>/dev/null | cut -f1)"
  echo "[deploy-stg] Loading image: $tar (${size_human:-unknown size})"

  if command -v pv >/dev/null 2>&1; then
    pv "$tar" | docker load
    return
  fi

  echo "[deploy-stg] (tip: 'sudo apt-get install -y pv' or synocommunity ipkg で pv を入れると進捗バーが出ます)"
  docker load -i "$tar" &
  local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 5
    waited=$((waited + 5))
    echo "[deploy-stg] ...still loading, ${waited}s elapsed (pid $pid) - this is normal for large images"
  done
  wait "$pid"
}

# ===== Update docker-compose.yml if supplied alongside the tar =====
COMPOSE_SRC="$DOCKER_ROOT/docker-compose.yml"
if [ -f "$COMPOSE_SRC" ]; then
  echo "[deploy-stg] Updating compose file from $COMPOSE_SRC"
  mkdir -p "$BASE_DIR"
  cp "$COMPOSE_SRC" "$COMPOSE_FILE"
elif [ ! -f "$COMPOSE_FILE" ]; then
  echo "[deploy-stg][error] No docker-compose.yml found at $COMPOSE_FILE or $COMPOSE_SRC" >&2
  exit 1
fi

# ===== Load app image =====
if [ -f "$IMAGE_TAR" ]; then
  load_image_with_progress "$IMAGE_TAR"
else
  echo "[deploy-stg][error] Image tar not found: $IMAGE_TAR" >&2
  exit 1
fi

# ===== Stop running containers =====
echo "[deploy-stg] docker compose down"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down || true

# ===== Reset mode: clear data =====
if [ "$MODE" = "reset" ]; then
  echo -e "\033[33m[reset] WARNING: This will delete all STG DB & media data.\033[0m"

  if [ -f "$IMAGE_DB_TAR" ]; then
    load_image_with_progress "$IMAGE_DB_TAR"
  else
    echo "[reset][warn] DB image tar not found: $IMAGE_DB_TAR"
  fi

  echo "[reset] Deleting $DB_PATH and $DATA_PATH"
  rm -rf "$DB_PATH" "$DATA_PATH"
fi

# ===== Start containers =====
echo "[deploy-stg] docker compose up -d"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans

# ===== Wait for health check =====
echo "[deploy-stg] Waiting for service health"

for i in $(seq 1 60); do
  if curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[deploy-stg] Service healthy"
    break
  fi
  echo "[deploy-stg] ...waiting ($i/60)"
  sleep 2
done

if ! curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
  echo "[deploy-stg][error] Health check failed: $HEALTH_URL" >&2
  echo "" >&2
  echo "----- diagnostics -----" >&2
  echo "[deploy-stg] container status:" >&2
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps >&2 || true
  echo "" >&2
  echo "[deploy-stg] recent web logs (docker logs = 標準出力のみ。ヘルスチェック失敗の詳細は下の Health.Log を見る):" >&2
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --tail 50 web >&2 || true
  echo "" >&2
  echo "[deploy-stg] web healthcheck history (Container Manager の詳細ログに出るのはこれと同じ内容):" >&2
  docker inspect --format '{{json .State.Health}}' "${PROJECT}-web-1" 2>/dev/null | python3 -m json.tool >&2 || true
  echo "------------------------" >&2
  echo "" >&2
  echo "[deploy-stg] 次に見るコマンド:" >&2
  echo "  docker compose -p $PROJECT logs -f web" >&2
  echo "  docker inspect --format '{{json .State.Health}}' ${PROJECT}-web-1 | python3 -m json.tool" >&2
  exit 1
fi

# ===== Cleanup old images =====
echo "[deploy-stg] Cleaning old unused Docker images"
docker image prune -f > /dev/null 2>&1 || true

echo -e "\033[32m[deploy-stg] STG Deploy complete (mode: $MODE)\033[0m"
