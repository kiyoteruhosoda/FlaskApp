#!/bin/bash
# STG デプロイスクリプト
# 使い方（モード引数は必須）:
#   ./scripts/deploy-stg.sh app      # 通常デプロイ（アプリのみ更新。DBスキーマ変更なし）
#   ./scripts/deploy-stg.sh migrate  # DDL更新時（新しい Alembic migration を追加した場合）
#   ./scripts/deploy-stg.sh reset    # 完全初期化（DB・メディアデータ消去。マスタデータ投入済みで起動）
#
# どれを使うか:
#   - アプリのみ更新（DDL変更なし）        → app
#   - DDL更新（migrations/versions/ 追加）  → migrate
#   - STG を完全に作り直したいとき          → reset

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
DOCKER_ROOT="$(dirname "$SCRIPT_DIR")"

PROJECT="photonest-stg"
APP_IMAGE="photonest:latest"
BASE_DIR="$DOCKER_ROOT/photonest-stg"
COMPOSE_FILE="$BASE_DIR/docker-compose.yml"
ENV_FILE="$BASE_DIR/.env"
IMAGE_TAR="$DOCKER_ROOT/photonest-latest.tar"
IMAGE_DB_TAR="$DOCKER_ROOT/photonest-db-latest.tar"
HEALTH_URL="http://127.0.0.1:8051/health/live"
DATA_PATH="$BASE_DIR/data"
DB_PATH="$BASE_DIR/db_data"
COMPOSE="docker compose -p $PROJECT -f $COMPOSE_FILE --env-file $ENV_FILE"

MODE="${1:-}"

case "$MODE" in
  app|migrate|reset) ;;
  *)
    echo "[deploy-stg][error] Mode required. Usage: $0 <app|migrate|reset>" >&2
    exit 1
    ;;
esac

echo -e "\033[36m[deploy-stg] Photonest STG deploy start (mode: $MODE)\033[0m"

# ===== Preflight: docker daemon must be reachable =====
if ! docker info >/dev/null 2>&1; then
  echo "[deploy-stg][error] Cannot reach the Docker daemon (permission denied or daemon down)." >&2
  echo "  Run this script with sudo, or add your user to the 'docker' group and re-login:" >&2
  echo "    sudo ./scripts/deploy-stg.sh $MODE" >&2
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
    # sleep 中に終了している場合があるので、表示直前にも生死を再確認する
    # （そうしないと失敗直後でも1周分「まだ読み込み中」と誤表示してしまう）
    if kill -0 "$pid" 2>/dev/null; then
      echo "[deploy-stg] ...still loading, ${waited}s elapsed (pid $pid) - this is normal for large images"
    fi
  done
  if ! wait "$pid"; then
    echo "[deploy-stg][error] docker load failed for $tar" >&2
    exit 1
  fi
}

# ===== Load app image =====
# 自己更新後の再実行時（PHOTONEST_DEPLOY_SELF_UPDATED=1）はロード済みなのでスキップする。
if [ "${PHOTONEST_DEPLOY_SELF_UPDATED:-}" = "1" ]; then
  echo "[deploy-stg] (self-update re-run) app image already loaded; skipping load"
elif [ -f "$IMAGE_TAR" ]; then
  load_image_with_progress "$IMAGE_TAR"
else
  echo "[deploy-stg][error] Image tar not found: $IMAGE_TAR" >&2
  exit 1
fi

# ===== Sync deploy assets from the loaded image =====
# 過去に「リポジトリでは修正済みなのに NAS 上の deploy スクリプト・docker-compose.yml が
# 古いままで、同じ起動失敗が再発し続ける」事故が繰り返された。
# tar（アプリイメージ）を唯一の配布物とし、イメージに焼き込まれた
# /app/docker-compose.yml と /app/scripts/deploy-stg.sh をロード直後に取り出して使う。
# スクリプト自身が更新された場合は置き換えて再実行する（tar の転送だけで修正が届く）。
COMPOSE_SYNCED_FROM_IMAGE=false
sync_assets_from_image() {
  local cid
  if ! cid=$(docker create "$APP_IMAGE" 2>/dev/null); then
    echo "[deploy-stg][warn] Could not inspect $APP_IMAGE; skipping asset sync" >&2
    return 0
  fi

  # --- docker-compose.yml（イメージ内のコピーを唯一の出所とする） ---
  mkdir -p "$BASE_DIR"
  if docker cp "$cid:/app/docker-compose.yml" "$COMPOSE_FILE.new" >/dev/null 2>&1; then
    mv -f "$COMPOSE_FILE.new" "$COMPOSE_FILE"
    COMPOSE_SYNCED_FROM_IMAGE=true
    echo "[deploy-stg] compose file synced from image: $APP_IMAGE -> $COMPOSE_FILE"
  else
    rm -f "$COMPOSE_FILE.new"
    echo "[deploy-stg][warn] $APP_IMAGE has no /app/docker-compose.yml (old image); falling back to file copy" >&2
  fi

  # --- nginx 設定（compose の ./docker/nginx/default.conf バインドマウント用） ---
  # compose の nginx サービスは設定ファイルを ./docker/nginx/default.conf という
  # 相対パスでバインドマウントする。相対パスは compose ファイルと同じディレクトリ
  # （$BASE_DIR）を基準に解決されるため、イメージ内の /app/docker/nginx/default.conf を
  # 同じ相対位置へ取り出しておかないと、起動時に
  #   Bind mount failed: '.../docker/nginx/default.conf' does not exist
  # で nginx コンテナが起動しない。compose と同様にイメージを唯一の出所とする。
  local nginx_conf_dst nginx_conf_dir
  nginx_conf_dst="$BASE_DIR/docker/nginx/default.conf"
  nginx_conf_dir="$(dirname "$nginx_conf_dst")"
  mkdir -p "$nginx_conf_dir"
  if docker cp "$cid:/app/docker/nginx/default.conf" "$nginx_conf_dst.new" >/dev/null 2>&1; then
    mv -f "$nginx_conf_dst.new" "$nginx_conf_dst"
    echo "[deploy-stg] nginx config synced from image: $APP_IMAGE -> $nginx_conf_dst"
  else
    rm -f "$nginx_conf_dst.new"
    echo "[deploy-stg][warn] $APP_IMAGE has no /app/docker/nginx/default.conf (old image); keeping existing file if any" >&2
  fi

  # --- deploy スクリプト自身（差分があれば置き換えて再実行） ---
  local script_name self_new
  script_name="$(basename "$SCRIPT_PATH")"
  self_new="$SCRIPT_DIR/.$script_name.new"
  if docker cp "$cid:/app/scripts/$script_name" "$self_new" >/dev/null 2>&1; then
    if cmp -s "$self_new" "$SCRIPT_PATH"; then
      rm -f "$self_new"
    elif [ "${PHOTONEST_DEPLOY_SELF_UPDATED:-}" = "1" ]; then
      # 再実行後も差分が残るのは異常（置き換え失敗等）。無限ループを避けて続行する。
      echo "[deploy-stg][warn] Script still differs from image copy after self-update; continuing as-is" >&2
      rm -f "$self_new"
    else
      chmod +x "$self_new"
      mv -f "$self_new" "$SCRIPT_PATH"
      docker rm -f "$cid" >/dev/null 2>&1 || true
      echo -e "\033[36m[deploy-stg] Deploy script updated from image; re-executing\033[0m"
      PHOTONEST_DEPLOY_SELF_UPDATED=1 exec "$SCRIPT_PATH" "$MODE"
    fi
  else
    rm -f "$self_new"
    echo "[deploy-stg][warn] $APP_IMAGE has no /app/scripts/$script_name (old image); keeping current script" >&2
  fi

  docker rm -f "$cid" >/dev/null 2>&1 || true
}
sync_assets_from_image

# ===== Fallback: update docker-compose.yml from a file supplied alongside the tar =====
# 新しいイメージなら上の sync で compose は取得済み。ここは古いイメージ
# （/app/docker-compose.yml を含まない）向けの従来動作。
COMPOSE_SRC="$DOCKER_ROOT/docker-compose.yml"
if [ "$COMPOSE_SYNCED_FROM_IMAGE" = true ]; then
  if [ -f "$COMPOSE_SRC" ]; then
    echo "[deploy-stg] note: $COMPOSE_SRC is ignored (image copy is authoritative)"
  fi
elif [ -f "$COMPOSE_SRC" ]; then
  echo "[deploy-stg] Updating compose file from $COMPOSE_SRC"
  mkdir -p "$BASE_DIR"
  cp "$COMPOSE_SRC" "$COMPOSE_FILE"
elif [ ! -f "$COMPOSE_FILE" ]; then
  echo "[deploy-stg][error] No docker-compose.yml found at $COMPOSE_FILE or $COMPOSE_SRC" >&2
  exit 1
fi

# ===== Stop running containers =====
echo "[deploy-stg] docker compose down"
$COMPOSE down || true

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
$COMPOSE up -d --remove-orphans

# ===== Wait for DB to actually accept TCP connections =====
# docker compose の depends_on/healthcheck は「healthy」と報告された時点で次に進むが、
# MariaDB 公式イメージは初回初期化時に一時ブートストラップサーバー（ソケットのみ）を
# 経由するため、healthcheck 実装によっては本来のネットワーク公開サーバーが起動する
# 前に healthy 判定されることがある。ここで web コンテナから実際に db:3306 へ接続
# できることを確認してから、以降の alembic upgrade を実行する。
echo "[deploy-stg] Waiting for DB to accept connections from web container"
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
  echo "[deploy-stg] ...db not reachable yet ($i/30)"
  sleep 2
done
if [ "$DB_WAIT_OK" != true ]; then
  echo "[deploy-stg][error] db:3306 not reachable from web container after waiting" >&2
  exit 1
fi

# ===== Schema sync =====
# DB 待機直後でも MariaDB 側の受け入れ準備が一瞬遅れることがあるため、
# 失敗しても少し待って再試行する（接続確立とサーバー完全起動の間の隙間対策）。
run_migrations_with_retry() {
  local attempt
  for attempt in 1 2 3; do
    if $COMPOSE exec -T web python scripts/run_db_migrations.py; then
      return 0
    fi
    echo "[deploy-stg][warn] DB migration failed (attempt $attempt/3); retrying in 5s" >&2
    sleep 5
  done
  echo "[deploy-stg][error] DB migration failed after 3 attempts" >&2
  return 1
}

case "$MODE" in
  migrate)
    # DDL更新時：既存データを保持したまま新しい migration だけを適用する。
    echo "[deploy-stg] Applying pending DB migrations"
    run_migrations_with_retry
    ;;
  reset)
    # db_data を削除した直後で DB は空。スキーマ・マスタデータは
    # `alembic upgrade head`（init_master + seed_master_data）で構築する。
    # web コンテナの entrypoint も起動時にマイグレーションを実行するが、
    # ここでも冪等に流して確実に head まで揃える。
    echo "[deploy-stg] Building schema + master data on fresh DB"
    run_migrations_with_retry
    ;;
esac

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
  $COMPOSE ps >&2 || true
  echo "" >&2
  echo "[deploy-stg] recent web logs (docker logs = 標準出力のみ。ヘルスチェック失敗の詳細は下の Health.Log を見る):" >&2
  $COMPOSE logs --tail 50 web >&2 || true
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

# ===== Show deployed version =====
echo "[deploy-stg] Deployed version:"
$COMPOSE exec -T web cat /app/shared/kernel/version.json 2>/dev/null || echo "[deploy-stg][warn] Could not read version.json from web container"

echo -e "\033[32m[deploy-stg] STG Deploy complete (mode: $MODE)\033[0m"
