#!/bin/bash
# 本番デプロイスクリプト
# 使い方:
#   ./scripts/deploy.sh          # 通常デプロイ
#   ./scripts/deploy.sh reset    # 完全初期化（DB・メディアデータ消去）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_ROOT="$(dirname "$SCRIPT_DIR")"

PROJECT="photonest"
BASE_DIR="$DOCKER_ROOT/photonest"
COMPOSE_FILE="$BASE_DIR/docker-compose.yml"
ENV_FILE="$BASE_DIR/.env"
IMAGE_TAR="$DOCKER_ROOT/photonest-latest.tar"
IMAGE_DB_TAR="$DOCKER_ROOT/photonest-db-latest.tar"
HEALTH_URL="http://127.0.0.1:8050/health/live"
DATA_PATH="$BASE_DIR/data"
DB_PATH="$BASE_DIR/db_data"

MODE="${1:-deploy}"

echo -e "\033[36m[deploy] Photonest deploy start (mode: $MODE)\033[0m"

# ===== Update docker-compose.yml if supplied alongside the tar =====
COMPOSE_SRC="$DOCKER_ROOT/docker-compose.yml"
if [ -f "$COMPOSE_SRC" ]; then
  echo "[deploy] Updating compose file from $COMPOSE_SRC"
  mkdir -p "$BASE_DIR"
  cp "$COMPOSE_SRC" "$COMPOSE_FILE"
elif [ ! -f "$COMPOSE_FILE" ]; then
  echo "[deploy][error] No docker-compose.yml found at $COMPOSE_FILE or $COMPOSE_SRC" >&2
  exit 1
fi

# ===== Load app image =====
if [ -f "$IMAGE_TAR" ]; then
  echo "[deploy] Loading image: $IMAGE_TAR"
  docker load -i "$IMAGE_TAR"
else
  echo "[deploy][error] Image tar not found: $IMAGE_TAR" >&2
  exit 1
fi

# ===== Stop running containers =====
echo "[deploy] docker compose down"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down || true

# ===== Reset mode: clear data =====
if [ "$MODE" = "reset" ]; then
  echo -e "\033[33m[reset] WARNING: This will delete all DB & media data.\033[0m"

  if [ -f "$IMAGE_DB_TAR" ]; then
    echo "[reset] Loading DB image: $IMAGE_DB_TAR"
    docker load -i "$IMAGE_DB_TAR"
  else
    echo "[reset][warn] DB image tar not found: $IMAGE_DB_TAR"
  fi

  echo "[reset] Deleting $DB_PATH and $DATA_PATH"
  rm -rf "$DB_PATH" "$DATA_PATH"
fi

# ===== Start containers =====
echo "[deploy] docker compose up -d"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans

# ===== Wait for health check =====
echo "[deploy] Waiting for service health"

for i in $(seq 1 60); do
  if curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[deploy] Service healthy"
    break
  fi
  echo "[deploy] ...waiting ($i/60)"
  sleep 2
done

if ! curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
  echo "[deploy][error] Health check failed" >&2
  echo "Check logs: docker compose -p $PROJECT logs -f"
  exit 1
fi

# ===== Cleanup old images =====
echo "[deploy] Cleaning old unused Docker images"
docker image prune -f > /dev/null 2>&1 || true

echo -e "\033[32m[deploy] Deploy complete (mode: $MODE)\033[0m"
