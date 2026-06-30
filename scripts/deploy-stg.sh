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

# ===== Load app image =====
if [ -f "$IMAGE_TAR" ]; then
  echo "[deploy-stg] Loading image: $IMAGE_TAR"
  docker load -i "$IMAGE_TAR"
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
    echo "[reset] Loading DB image: $IMAGE_DB_TAR"
    docker load -i "$IMAGE_DB_TAR"
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
  echo "[deploy-stg][error] Health check failed" >&2
  echo "Check logs: docker compose -p $PROJECT logs -f"
  exit 1
fi

# ===== Cleanup old images =====
echo "[deploy-stg] Cleaning old unused Docker images"
docker image prune -f > /dev/null 2>&1 || true

echo -e "\033[32m[deploy-stg] STG Deploy complete (mode: $MODE)\033[0m"
