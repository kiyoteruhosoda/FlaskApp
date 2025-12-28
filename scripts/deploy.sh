#!/bin/bash

#通常デプロイ
#./deploy.sh

#完全初期化（データ消去に注意）
#./deploy.sh reset

set -euo pipefail

PROJECT="photonest"
BASE_DIR="/volume1/docker/photonest"
COMPOSE_FILE="$BASE_DIR/docker-compose.yml"
IMAGE_TAR="/volume1/docker/photonest-latest.tar"   # ✅ 修正
HEALTH_URL="http://127.0.0.1:8050/health/live"
DATA_PATH="$BASE_DIR/data"
DB_PATH="$BASE_DIR/db_data"

MODE="${1:-deploy}"   # deploy or reset

echo -e "\033[36m[deploy] Photonest deploy start (mode: $MODE)\033[0m"

# ===== Load image =====
if [ -f "$IMAGE_TAR" ]; then
  echo "[deploy] Loading image: $IMAGE_TAR"
  docker load -i "$IMAGE_TAR"
else
  echo "[deploy][error] Image tar not found: $IMAGE_TAR"
  exit 1
fi

# ===== Stop running containers =====
echo "[deploy] docker compose down"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down || true

# ===== Reset mode: clear data =====
if [ "$MODE" = "reset" ]; then
  echo -e "\033[33m[reset] WARNING: This will delete all DB & media data.\033[0m"

  echo "[reset] Removing old DB image cache"
  docker images | grep "photonest-db" && docker rmi -f $(docker images | grep "photonest-db" | awk '{print $3}') || true

  echo "[reset] Deleting $DB_PATH and $DATA_PATH"
  rm -rf "$DB_PATH" "$DATA_PATH"

  echo "[reset] Recreated empty data directories"
fi



# ===== Start containers =====
echo "[deploy] docker compose up -d"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d --remove-orphans

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
  echo "[deploy][error] Health check failed"
  echo "Check logs: docker compose -p $PROJECT logs -f"
  exit 1
fi

# ===== Cleanup old images =====
echo "[deploy] Cleaning old unused Docker images"
docker image prune -f > /dev/null 2>&1 || true

echo -e "\033[32m[deploy] Deploy complete (mode: $MODE)\033[0m"
