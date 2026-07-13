#!/bin/bash
# デプロイスクリプト（stg / prod 共通・配置ディレクトリから環境を自動判定）
#
# 配置想定（環境ごとに自己完結したディレクトリ。photonest/ 配下に stg/ と prod/ を置く）:
#   photonest/
#     stg/
#       image.tar          # ビルド済みアプリイメージ（dist/image.tar を配置）
#       image-db.tar       # (任意) DB イメージ（reset 時のみ使用。dist/image-db.tar を配置）
#       scripts/deploy.sh  # このスクリプト（git 管理。dist/scripts/deploy.sh を配置）
#       .env               # stg 用設定（無ければ初回デプロイ時にテンプレートを自動生成）
#       docker-compose.yml # stg 用（デプロイ時にイメージ内のコピーで自動更新される）
#       mnt/               # コンテナマウント用データ（data/ と db_data/ が作られる）
#       pick.sh            # イメージ取得用（git 管理外・任意。dist/ からここへ配置する）
#     prod/                # 上記と同じ構成
#
# 使い方（モード引数は必須。photonest/<stg|prod>/ で実行する）:
#   ./scripts/deploy.sh app      # 通常デプロイ（アプリのみ更新。DBスキーマ変更なし）
#   ./scripts/deploy.sh migrate  # DDL更新時（新しい Alembic migration を追加した場合）
#   ./scripts/deploy.sh reset    # 完全初期化（DB・メディアデータ消去。破壊的）
#
# デプロイ中にエラーが発生した場合は、失敗したモジュール（コンテナ）のログを
# 出力して終了する。

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
ENV_NAME="$(basename "$BASE_DIR")"

# ===== 環境判定（配置ディレクトリ名で stg / prod を切り替える） =====
case "$ENV_NAME" in
  stg)
    PROJECT="photonest-stg"
    DEFAULT_WEB_HOST_PORT=8051
    ;;
  prod)
    # 既存の本番デプロイ（compose project 名 "photonest"）を引き継ぐ
    PROJECT="photonest"
    DEFAULT_WEB_HOST_PORT=8050
    ;;
  *)
    echo "[deploy][error] このスクリプトは photonest/stg/scripts/ または photonest/prod/scripts/ に配置して実行してください。" >&2
    echo "  現在の配置: $SCRIPT_DIR（親ディレクトリ名 '$ENV_NAME' が stg / prod ではありません）" >&2
    exit 1
    ;;
esac

TAG="[deploy:$ENV_NAME]"
log()  { echo -e "\033[36m${TAG}\033[0m $*"; }
warn() { echo -e "\033[33m${TAG}[warn]\033[0m $*" >&2; }
err()  { echo -e "\033[31m${TAG}[error]\033[0m $*" >&2; }

APP_IMAGE="photonest:$ENV_NAME"
DB_IMAGE="photonest-db:$ENV_NAME"
IMAGE_TAR="$BASE_DIR/image.tar"
IMAGE_DB_TAR="$BASE_DIR/image-db.tar"
COMPOSE_FILE="$BASE_DIR/docker-compose.yml"
ENV_FILE="$BASE_DIR/.env"

# ===== .env の値を読む（compose interpolation と同じく「最後の定義」を採用） =====
# CR（Windows 改行の混入）と前後の空白は必ず除去する。docker compose 自身の
# .env パーサーは CRLF を許容するが、ここで読んだ値は export されて compose の
# 値より優先されるため、CR が残ると実在するパスでも
#   Bind mount failed: '<path>\r' does not exist
# という一見矛盾したエラーになる（エラー表示も CR で行頭上書きされ判読不能になる）。
env_file_value() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 0
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d'=' -f2- \
    | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' || true
}

# マウントルート。既定は環境ディレクトリ配下の mnt/（.env の HOST_DATA_ROOT で上書き可）。
HOST_DATA_ROOT="$(env_file_value HOST_DATA_ROOT)"
HOST_DATA_ROOT="${HOST_DATA_ROOT:-$BASE_DIR/mnt}"
DATA_PATH="$HOST_DATA_ROOT/data"
DB_PATH="$HOST_DATA_ROOT/db_data"

WEB_HOST_PORT="$(env_file_value WEB_HOST_PORT)"
WEB_HOST_PORT="${WEB_HOST_PORT:-$DEFAULT_WEB_HOST_PORT}"
HEALTH_URL="http://127.0.0.1:${WEB_HOST_PORT}/health/live"

# compose interpolation はシェル環境変数 > --env-file の優先順位のため、
# ここで export した値が .env の記載や compose 既定値より優先される。
# イメージタグと HOST_DATA_ROOT は必ずこのスクリプトの判定値で統一する
# （stg と prod が同一ホストで photonest:latest を取り合わないようにするため）。
export HOST_DATA_ROOT
export WEB_IMAGE="$APP_IMAGE"
export DB_IMAGE

COMPOSE="docker compose -p $PROJECT -f $COMPOSE_FILE --env-file $ENV_FILE"

MODE="${1:-}"

case "$MODE" in
  app|migrate|reset) ;;
  *)
    err "Mode required. Usage: $0 <app|migrate|reset>"
    exit 1
    ;;
esac

# ===== エラー時診断: 失敗したモジュールのログを出して終了する =====
# init-paths を含める（マウントルート作成の run-once コンテナ。ここで失敗すると
# db 等がそもそも起動しないため、真っ先にログを確認したい）。
ALL_SERVICES=(init-paths db redis web worker beat nginx)

dump_module_logs() { # 引数: サービス名...
  echo "" >&2
  echo "----- diagnostics ($TAG) -----" >&2
  echo "$TAG container status:" >&2
  # -a: 起動に失敗して即終了したコンテナ（init-paths 等）も一覧に出す。
  $COMPOSE ps -a >&2 || true
  local svc
  for svc in "$@"; do
    echo "" >&2
    echo "$TAG ---- module logs: $svc (last 100 lines) ----" >&2
    $COMPOSE logs --tail 100 --timestamps "$svc" >&2 || true
  done
  echo "------------------------------" >&2
}

fail() { # 引数: メッセージ [ログを出すサービス名...]
  local msg="$1"
  shift || true
  err "$msg"
  if [ $# -gt 0 ]; then
    dump_module_logs "$@"
  fi
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
}

# set -e で中断される想定外のエラーでも、必ず全モジュールのログを出して終了する。
on_unexpected_error() {
  local line="$1"
  err "Unexpected error at line $line (mode: $MODE)"
  dump_module_logs "${ALL_SERVICES[@]}"
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
}
trap 'on_unexpected_error $LINENO' ERR

log "Photonest deploy start (env: $ENV_NAME, mode: $MODE, base: $BASE_DIR)"

# ===== Preflight: docker daemon must be reachable =====
if ! docker info >/dev/null 2>&1; then
  err "Cannot reach the Docker daemon (permission denied or daemon down)."
  echo "  Run this script with sudo, or add your user to the 'docker' group and re-login:" >&2
  echo "    sudo $0 $MODE" >&2
  exit 1
fi

# ===== Preflight: 旧配置（<環境dir>/db_data 直下）のデータ引き継ぎガード =====
# 旧 deploy-stg.sh 時代のマウントルートは <環境dir> 直下（db_data/・data/）だった。
# 現行の既定は <環境dir>/mnt 配下のため、旧データが残ったまま app/migrate を実行すると
# 空の mnt/db_data で MariaDB が新規初期化され、既存データが使われない事故になる。
# 旧 db_data があり新側に無い場合は、何も変更しないうちに停止して対処を促す。
log "Mount root: $HOST_DATA_ROOT"
if [ "$MODE" != "reset" ] && [ -d "$BASE_DIR/db_data" ] && [ ! -d "$DB_PATH" ]; then
  err "旧配置の DB データが見つかりました: $BASE_DIR/db_data（現在のマウントルート $HOST_DATA_ROOT には db_data がありません）"
  echo "  このまま続行すると空の DB が新規初期化され、既存データが使われません。以下のどちらかで対処してください:" >&2
  echo "" >&2
  echo "  A) 既存データを新配置へ移動する（推奨）:" >&2
  echo "       mkdir -p \"$HOST_DATA_ROOT\"" >&2
  echo "       mv \"$BASE_DIR/db_data\" \"$HOST_DATA_ROOT/\"" >&2
  echo "       [ -d \"$BASE_DIR/data\" ] && mv \"$BASE_DIR/data\" \"$HOST_DATA_ROOT/\"" >&2
  echo "" >&2
  echo "  B) 旧配置のまま使う: $ENV_FILE に HOST_DATA_ROOT=$BASE_DIR を設定する" >&2
  echo "" >&2
  echo "  ※ 旧データを破棄して新規初期化してよい場合のみ、$BASE_DIR/db_data をリネーム／削除して再実行してください。" >&2
  err "Deploy aborted before any changes (mode: $MODE, env: $ENV_NAME)"
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
  log "Loading image: $tar (${size_human:-unknown size})"

  if command -v pv >/dev/null 2>&1; then
    pv "$tar" | docker load
    return
  fi

  log "(tip: 'sudo apt-get install -y pv' or synocommunity ipkg で pv を入れると進捗バーが出ます)"
  docker load -i "$tar" &
  local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 5
    waited=$((waited + 5))
    # sleep 中に終了している場合があるので、表示直前にも生死を再確認する
    # （そうしないと失敗直後でも1周分「まだ読み込み中」と誤表示してしまう）
    if kill -0 "$pid" 2>/dev/null; then
      log "...still loading, ${waited}s elapsed (pid $pid) - this is normal for large images"
    fi
  done
  if ! wait "$pid"; then
    fail "docker load failed for $tar"
  fi
}

# tar には photonest:latest / photonest-db:latest として保存されているため、
# ロード後に環境別タグ（photonest:stg 等）を付け直す。stg と prod を同一ホストで
# 運用しても、片方のロードがもう片方の実行イメージを差し替えないようにするため。
retag_for_env() { # 引数: <ロード時タグ> <環境別タグ>
  local loaded="$1" target="$2"
  if ! docker tag "$loaded" "$target"; then
    fail "Failed to tag $loaded as $target"
  fi
  log "Tagged $loaded -> $target"
}

# ===== Load app image =====
if [ -f "$IMAGE_TAR" ]; then
  load_image_with_progress "$IMAGE_TAR"
  retag_for_env "photonest:latest" "$APP_IMAGE"
elif docker image inspect "$APP_IMAGE" >/dev/null 2>&1; then
  warn "Image tar not found: $IMAGE_TAR — reusing already-loaded $APP_IMAGE"
else
  err "Image tar not found: $IMAGE_TAR"
  echo "  ビルドマシンで 'make build' を実行し、dist/image.tar を $IMAGE_TAR へ配置してください（pick.sh 等）。" >&2
  exit 1
fi

# ===== Sync deploy assets from the loaded image =====
# 過去に「リポジトリでは修正済みなのに NAS 上の docker-compose.yml が古いままで、
# 同じ起動失敗が再発し続ける」事故が繰り返された。アプリイメージに焼き込まれた
# /app/docker-compose.yml をロード直後に取り出し、常にイメージと同じ版を使う。
# 環境ごとの違い（ポート・資格情報等）はすべて .env 側で表現する。
sync_assets_from_image() {
  local cid
  if ! cid=$(docker create "$APP_IMAGE" 2>/dev/null); then
    warn "Could not inspect $APP_IMAGE; skipping asset sync"
    return 0
  fi

  # --- docker-compose.yml（イメージ内のコピーを唯一の出所とする） ---
  mkdir -p "$BASE_DIR"
  if docker cp "$cid:/app/docker-compose.yml" "$COMPOSE_FILE.new" >/dev/null 2>&1; then
    mv -f "$COMPOSE_FILE.new" "$COMPOSE_FILE"
    log "compose file synced from image: $APP_IMAGE -> $COMPOSE_FILE"
  else
    rm -f "$COMPOSE_FILE.new"
    warn "$APP_IMAGE has no /app/docker-compose.yml (old image); keeping existing file if any"
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
    log "nginx config synced from image: $APP_IMAGE -> $nginx_conf_dst"
  else
    rm -f "$nginx_conf_dst.new"
    warn "$APP_IMAGE has no /app/docker/nginx/default.conf (old image); keeping existing file if any"
  fi

  docker rm -f "$cid" >/dev/null 2>&1 || true
}
sync_assets_from_image

if [ ! -f "$COMPOSE_FILE" ]; then
  fail "No docker-compose.yml found at $COMPOSE_FILE (image sync also failed)"
fi

# ===== Ensure .env exists (zero-config deploy) =====
# .env が無くてもデプロイできるようにする（docker compose は --env-file と
# 各サービスの env_file: .env の両方で実ファイルを要求するため、無いと即失敗する）。
# 値はすべて docker-compose.yml 側の ${VAR:-default} が供給するので、生成する
# .env は上書き用のコメント付きテンプレートで足りる。既存の .env には触れない。
if [ ! -f "$ENV_FILE" ]; then
  warn "$ENV_FILE not found; generating a default template."
  echo "  All settings fall back to built-in defaults (development-grade credentials)."
  echo "  For any externally reachable environment, edit $ENV_FILE and redeploy."
  mkdir -p "$BASE_DIR"
  if [ "$ENV_NAME" = "stg" ]; then
    DEFAULT_DB_HOST_PORT=3308
    DEFAULT_DB_CONTAINER=mariadb-stg
    DEFAULT_NETWORK=photonest-stg
    DEFAULT_SUBNET=172.23.0.0/16
  else
    DEFAULT_DB_HOST_PORT=3307
    DEFAULT_DB_CONTAINER=mariadb
    DEFAULT_NETWORK=photonest-prod
    DEFAULT_SUBNET=172.22.0.0/16
  fi
  cat > "$ENV_FILE" <<ENVEOF
# 自動生成された .env（deploy スクリプトが作成。環境: $ENV_NAME）。
# 資格情報などは docker-compose.yml の既定値で起動する（初期設定のみで動作）。
# 既定の資格情報は開発向け。外部公開する場合は必ず上書きして再デプロイする。
# すべての項目は .env.example（stg は .env.staging.example）を参照。

# --- 環境固有の実値（この環境ディレクトリに閉じた値に固定する）---
# HOST_DATA_ROOT はこのスクリプトの DATA_PATH/DB_PATH（reset 時の削除対象）と
# compose のバインドマウント先を一致させるため、必ず <環境dir>/mnt にする。
HOST_DATA_ROOT=$BASE_DIR/mnt
WEB_HOST_PORT=$WEB_HOST_PORT
DB_HOST_PORT=$DEFAULT_DB_HOST_PORT
DB_CONTAINER_NAME=$DEFAULT_DB_CONTAINER
DOCKER_NETWORK_NAME=$DEFAULT_NETWORK
DOCKER_NETWORK_SUBNET=$DEFAULT_SUBNET

# --- 上書き推奨（未設定なら開発向け既定値で動作する）---
# MARIADB_ROOT_PASSWORD=strong-mariadb-root-password-here
# MARIADB_USER=web_user
# MARIADB_PASSWORD=strong-mariadb-web_user-password-here
# MARIADB_DATABASE=appdb
# REDIS_PASSWORD=strong-redis-password-here
# API_BASE_URL=https://photonest.example.com
# CORS_ALLOWED_ORIGINS=https://photonest.example.com
# ADMIN_INITIAL_PASSWORD=change-me-strong
ENVEOF
fi

# ===== Ensure DB image is available under the env-specific tag =====
# reset 時は tar からロードするが、通常デプロイでは既存タグを使い回す。
# 環境別タグがまだ無い場合は、従来運用の photonest-db:latest から引き継ぐ。
ensure_db_image() {
  if docker image inspect "$DB_IMAGE" >/dev/null 2>&1; then
    return 0
  fi
  if [ -f "$IMAGE_DB_TAR" ]; then
    load_image_with_progress "$IMAGE_DB_TAR"
    retag_for_env "photonest-db:latest" "$DB_IMAGE"
    return 0
  fi
  if docker image inspect "photonest-db:latest" >/dev/null 2>&1; then
    retag_for_env "photonest-db:latest" "$DB_IMAGE"
    return 0
  fi
  fail "DB image not found: $DB_IMAGE（$IMAGE_DB_TAR も photonest-db:latest も存在しません。'make build-db' で dist/image-db.tar を作成し配置してください）"
}

# ===== Stop running containers =====
log "docker compose down"
$COMPOSE down || true

# ===== Reset mode: clear data =====
if [ "$MODE" = "reset" ]; then
  echo -e "\033[33m[reset] WARNING: This will delete all $ENV_NAME DB & media data.\033[0m"

  if [ -f "$IMAGE_DB_TAR" ]; then
    load_image_with_progress "$IMAGE_DB_TAR"
    retag_for_env "photonest-db:latest" "$DB_IMAGE"
  else
    warn "[reset] DB image tar not found: $IMAGE_DB_TAR"
  fi

  echo "[reset] Deleting $DB_PATH and $DATA_PATH"
  rm -rf "$DB_PATH" "$DATA_PATH"
fi

ensure_db_image

# ===== Ensure the host mount root exists =====
# init-paths コンテナが data/・db_data/ 等のサブディレクトリ作成と所有権設定を
# 担うが、その init-paths 自身が HOST_DATA_ROOT（既定 <環境dir>/mnt）を
# バインドマウントする。Docker はバインドマウント元が存在しなくても自動作成
# しないため、mnt/ が無い新規デプロイでは最初のコンテナ起動時点で
#   Error response from daemon: Bind mount failed: '<HOST_DATA_ROOT>' does not exist
# となり、以降のコンテナが一切起動しない（ログも残らない）。マウントルートだけは
# ここで確実に作り、サブディレクトリ作成・所有権付与は従来どおり init-paths に任せる。
log "Ensuring host mount root exists: $HOST_DATA_ROOT"
if ! mkdir -p "$HOST_DATA_ROOT"; then
  fail "Could not create host mount root: $HOST_DATA_ROOT（親ディレクトリの権限を確認してください）"
fi

# ===== Start containers =====
log "docker compose up -d"
# 出力を tee で捕捉する。バインドマウント失敗などの起動前エラーはコンテナが
# 生成されないため `docker compose logs` には一切残らず、失敗時の診断で唯一の
# 手がかりになる。またパイプ経由だと compose は非TTYと判断してプレーンな
# 行単位出力に切り替わるため、進捗バーの \r による表示崩れも避けられる。
UP_OUTPUT="$(mktemp)"
if ! $COMPOSE up -d --remove-orphans 2>&1 | tee "$UP_OUTPUT"; then
  err "docker compose up failed"
  echo "" >&2
  echo "$TAG ---- 'docker compose up' の出力（バインドマウント失敗等はコンテナログに残らないため再掲）----" >&2
  cat "$UP_OUTPUT" >&2
  rm -f "$UP_OUTPUT"
  dump_module_logs "${ALL_SERVICES[@]}"
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
fi
rm -f "$UP_OUTPUT"

# ===== Wait for DB to actually accept TCP connections =====
# docker compose の depends_on/healthcheck は「healthy」と報告された時点で次に進むが、
# MariaDB 公式イメージは初回初期化時に一時ブートストラップサーバー（ソケットのみ）を
# 経由するため、healthcheck 実装によっては本来のネットワーク公開サーバーが起動する
# 前に healthy 判定されることがある。ここで web コンテナから実際に db:3306 へ接続
# できることを確認してから、以降の alembic upgrade を実行する。
log "Waiting for DB to accept connections from web container"
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
  log "...db not reachable yet ($i/30)"
  sleep 2
done
if [ "$DB_WAIT_OK" != true ]; then
  fail "db:3306 not reachable from web container after waiting" db web
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
    warn "DB migration failed (attempt $attempt/3); retrying in 5s"
    sleep 5
  done
  fail "DB migration failed after 3 attempts" web db
}

case "$MODE" in
  migrate)
    # DDL更新時：既存データを保持したまま新しい migration だけを適用する。
    log "Applying pending DB migrations"
    run_migrations_with_retry
    ;;
  reset)
    # db_data を削除した直後で DB は空。スキーマ・マスタデータは
    # `alembic upgrade head`（init_master + seed_master_data）で構築する。
    # web コンテナの entrypoint も起動時にマイグレーションを実行するが、
    # ここでも冪等に流して確実に head まで揃える。
    log "Building schema + master data on fresh DB"
    run_migrations_with_retry
    ;;
esac

# ===== Wait for health check =====
log "Waiting for service health: $HEALTH_URL"

for i in $(seq 1 60); do
  if curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
    log "Service healthy"
    break
  fi
  log "...waiting ($i/60)"
  sleep 2
done

if ! curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
  err "Health check failed: $HEALTH_URL"
  dump_module_logs web nginx
  echo "" >&2
  echo "$TAG web healthcheck history (Container Manager の詳細ログに出るのはこれと同じ内容):" >&2
  docker inspect --format '{{json .State.Health}}' "${PROJECT}-web-1" 2>/dev/null | python3 -m json.tool >&2 || true
  echo "" >&2
  echo "$TAG 次に見るコマンド:" >&2
  echo "  docker compose -p $PROJECT logs -f web" >&2
  echo "  docker inspect --format '{{json .State.Health}}' ${PROJECT}-web-1 | python3 -m json.tool" >&2
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
fi

# ===== Cleanup old images =====
log "Cleaning old unused Docker images"
docker image prune -f > /dev/null 2>&1 || true

# ===== Show deployed version =====
log "Deployed version:"
$COMPOSE exec -T web cat /app/shared/kernel/version.json 2>/dev/null || warn "Could not read version.json from web container"

echo -e "\033[32m${TAG} Deploy complete (mode: $MODE)\033[0m"
