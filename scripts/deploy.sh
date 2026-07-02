#!/bin/bash
# 本番デプロイスクリプト
# 使い方（モード引数は必須）:
#   ./scripts/deploy.sh app      # 通常デプロイ（アプリのみ更新。DBスキーマ変更なし）
#   ./scripts/deploy.sh migrate  # DDL更新時（新しい Alembic migration を追加した場合）
#   ./scripts/deploy.sh reset    # 完全初期化（DB・メディアデータ消去。マスタデータ投入済みで起動）
#
# どれを使うか:
#   - アプリのみ更新（DDL変更なし）        → app
#   - DDL更新（migrations/versions/ 追加）  → migrate
#   - 完全に作り直したいとき（破壊的）      → reset

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
COMPOSE="docker compose -p $PROJECT -f $COMPOSE_FILE --env-file $ENV_FILE"

MODE="${1:-}"

case "$MODE" in
  app|migrate|reset) ;;
  *)
    echo "[deploy][error] Mode required. Usage: $0 <app|migrate|reset>" >&2
    exit 1
    ;;
esac

echo -e "\033[36m[deploy] Photonest deploy start (mode: $MODE)\033[0m"

# ===== Preflight: docker daemon must be reachable =====
if ! docker info >/dev/null 2>&1; then
  echo "[deploy][error] Cannot reach the Docker daemon (permission denied or daemon down)." >&2
  echo "  Run this script with sudo, or add your user to the 'docker' group and re-login:" >&2
  echo "    sudo ./scripts/deploy.sh $MODE" >&2
  exit 1
fi

# ===== Load a docker image tar with visible progress =====
# `docker load` は標準では進捗を表示せず、大きいイメージだと数分間無反応に見える。
# `pv` があれば転送量・速度・経過時間を表示し、なければ一定間隔でハートビートを出して
# 「止まっているように見えるが実行中」であることが分かるようにする。
load_image_with_progress() {
  local tar="$1"
  local size_human
  size_human="$(du -h "$tar" 2>/dev/null | cut -f1)"
  echo "[deploy] Loading image: $tar (${size_human:-unknown size})"

  if command -v pv >/dev/null 2>&1; then
    pv "$tar" | docker load
    return
  fi

  echo "[deploy] (tip: 'sudo apt-get install -y pv' or synocommunity ipkg で pv を入れると進捗バーが出ます)"
  docker load -i "$tar" &
  local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 5
    waited=$((waited + 5))
    # sleep 中に終了している場合があるので、表示直前にも生死を再確認する
    # （そうしないと失敗直後でも1周分「まだ読み込み中」と誤表示してしまう）
    if kill -0 "$pid" 2>/dev/null; then
      echo "[deploy] ...still loading, ${waited}s elapsed (pid $pid) - this is normal for large images"
    fi
  done
  if ! wait "$pid"; then
    echo "[deploy][error] docker load failed for $tar" >&2
    exit 1
  fi
}

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
  load_image_with_progress "$IMAGE_TAR"
else
  echo "[deploy][error] Image tar not found: $IMAGE_TAR" >&2
  exit 1
fi

# ===== Stop running containers =====
echo "[deploy] docker compose down"
$COMPOSE down || true

# ===== Reset mode: clear data =====
if [ "$MODE" = "reset" ]; then
  echo -e "\033[33m[reset] WARNING: This will delete all DB & media data.\033[0m"

  if [ -f "$IMAGE_DB_TAR" ]; then
    load_image_with_progress "$IMAGE_DB_TAR"
  else
    echo "[reset][warn] DB image tar not found: $IMAGE_DB_TAR"
  fi

  echo "[reset] Deleting $DB_PATH and $DATA_PATH"
  rm -rf "$DB_PATH" "$DATA_PATH"
fi

# ===== Start containers =====
echo "[deploy] docker compose up -d"
$COMPOSE up -d --remove-orphans

# ===== Wait for DB to actually accept TCP connections =====
# docker compose の depends_on/healthcheck は「healthy」と報告された時点で次に進むが、
# MariaDB 公式イメージは初回初期化時に一時ブートストラップサーバー（ソケットのみ）を
# 経由するため、healthcheck 実装によっては本来のネットワーク公開サーバーが起動する
# 前に healthy 判定されることがある。ここで web コンテナから実際に db:3306 へ接続
# できることを確認してから、以降の flask db stamp/upgrade を実行する。
echo "[deploy] Waiting for DB to accept connections from web container"
DB_WAIT_OK=false
for i in $(seq 1 30); do
  if $COMPOSE exec -T web python -c "
import socket
s = socket.create_connection(('db', 3306), timeout=2)
s.close()
" >/dev/null 2>&1; then
    DB_WAIT_OK=true
    break
  fi
  echo "[deploy] ...db not reachable yet ($i/30)"
  sleep 2
done
if [ "$DB_WAIT_OK" != true ]; then
  echo "[deploy][error] db:3306 not reachable from web container after waiting" >&2
  exit 1
fi

# ===== Schema sync =====
case "$MODE" in
  migrate)
    # DDL更新時：既存データを保持したまま新しい migration だけを適用する。
    echo "[deploy] Applying pending DB migrations (flask db upgrade)"
    $COMPOSE exec -T web flask db upgrade
    ;;
  reset)
    # db/init/01_initialize.sql はスキーマ・マスタデータ込みで焼き込み済み。
    # scripts/regenerate_db_baseline.sh で再生成したものは alembic_version も
    # head に揃った状態で含まれるはずだが、念のためここでも stamp head しておき、
    # 万一 alembic_version がずれた状態で焼き込まれていても次回 `migrate` が
    # init_master から再実行され CREATE TABLE の重複エラーになるのを防ぐ。
    # 前提: db/init/01_initialize.sql は DBイメージ再ビルド（make build-db）前に
    #       ./scripts/regenerate_db_baseline.sh で現在の migration head から
    #       再生成しておくこと。DDL変更時は忘れずに再生成すること。
    echo "[deploy] Stamping alembic_version to head (fresh DB from baked snapshot)"
    $COMPOSE exec -T web flask db stamp head
    ;;
esac

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
  echo "[deploy][error] Health check failed: $HEALTH_URL" >&2
  echo "" >&2
  echo "----- diagnostics -----" >&2
  echo "[deploy] container status:" >&2
  $COMPOSE ps >&2 || true
  echo "" >&2
  echo "[deploy] recent web logs (docker logs = 標準出力のみ。ヘルスチェック失敗の詳細は下の Health.Log を見る):" >&2
  $COMPOSE logs --tail 50 web >&2 || true
  echo "" >&2
  echo "[deploy] web healthcheck history (Container Manager の詳細ログに出るのはこれと同じ内容):" >&2
  docker inspect --format '{{json .State.Health}}' "${PROJECT}-web-1" 2>/dev/null | python3 -m json.tool >&2 || true
  echo "------------------------" >&2
  echo "" >&2
  echo "[deploy] 次に見るコマンド:" >&2
  echo "  docker compose -p $PROJECT logs -f web" >&2
  echo "  docker inspect --format '{{json .State.Health}}' ${PROJECT}-web-1 | python3 -m json.tool" >&2
  exit 1
fi

# ===== Cleanup old images =====
echo "[deploy] Cleaning old unused Docker images"
docker image prune -f > /dev/null 2>&1 || true

echo -e "\033[32m[deploy] Deploy complete (mode: $MODE)\033[0m"
