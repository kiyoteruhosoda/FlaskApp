#!/bin/sh
set -eu

# ===== Colored echo =====
log()  { printf "\033[32m[entrypoint]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[entrypoint][warn]\033[0m %s\n" "$*"; }
err()  { printf "\033[31m[entrypoint][error]\033[0m %s\n" "$*"; }

# ===== Startup diagnostics =====
log "========== DIAGNOSTICS =========="

# イメージバージョン（ビルド時に埋め込まれる）
if [ -f /app/shared/kernel/version.json ]; then
  python -c "
import json, sys
try:
    d = json.load(open('/app/shared/kernel/version.json'))
    print('[entrypoint] image : version={} branch={} commit={} build={}'.format(
        d.get('version','?'), d.get('branch','?'),
        d.get('commit_hash','?'), d.get('build_date','?')))
except Exception as e:
    print('[entrypoint] image : version.json parse error -', e)
" 2>&1
else
  warn "image : version.json not found (old image or build error)"
fi

# Python・PyMySQL
log "python : $(python --version 2>&1)"
log "pymysql: $(python -c 'import pymysql; print(pymysql.__version__)' 2>&1 || echo 'NOT INSTALLED')"

# 起動モード
log "mode   : ${1:-web}"
log "================================="

# ===== Directory prepare =====
log "Ensuring /app/data directory structure"

mkdir -p /app/data \
         /app/data/backups \
         /app/data/celery \
         /app/data/media/local_import \
         /app/data/media/originals \
         /app/data/media/playback \
         /app/data/media/thumbs \
         /app/data/tmp \
         /app/data/uploads

# ===== Permissions =====
if [ -n "${PUID:-}" ] && [ -n "${PGID:-}" ]; then
  log "Applying PUID=${PUID}, PGID=${PGID}"
  chown -R "$PUID:$PGID" /app/data || warn "chmod not fully applied"
else
  warn "PUID/PGID not set, skipping chown"
fi

# ===== DB wait =====
if echo "${DATABASE_URI:-}" | grep -q "mysql"; then
  DB_HOST=$(echo "$DATABASE_URI" | sed -E 's#.*://[^@]+@([^:/]+).*#\1#')
  DB_PORT=$(echo "$DATABASE_URI" | sed -E 's#.*://[^@]+@[^:]+:([0-9]+).*#\1#')
  DB_NAME=$(echo "$DATABASE_URI" | sed -E 's#.*://[^@]+@[^/]+/([^?]+).*#\1#')
  DB_USER=$(echo "$DATABASE_URI" | sed -E 's#.*://([^:]+):.*#\1#')
  DB_PASS=$(echo "$DATABASE_URI" | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')

  log "DB target: ${DB_USER}@${DB_HOST}:${DB_PORT:-3306}/${DB_NAME}"
  log "Waiting for DB ..."

  export _DB_WAIT_HOST="$DB_HOST" _DB_WAIT_USER="$DB_USER" \
         _DB_WAIT_PASS="$DB_PASS" _DB_WAIT_PORT="${DB_PORT:-3306}"

  _db_first=1
  until python -c "
import os, pymysql, sys
try:
    c = pymysql.connect(
        host=os.environ['_DB_WAIT_HOST'],
        port=int(os.environ['_DB_WAIT_PORT']),
        user=os.environ['_DB_WAIT_USER'],
        password=os.environ['_DB_WAIT_PASS'],
        connect_timeout=3,
    )
    c.close()
except Exception:
    sys.exit(1)
" >/dev/null 2>&1; do
    if [ "$_db_first" = "1" ]; then
      _db_err=$(python -c "
import os, pymysql, sys
try:
    c = pymysql.connect(
        host=os.environ['_DB_WAIT_HOST'],
        port=int(os.environ['_DB_WAIT_PORT']),
        user=os.environ['_DB_WAIT_USER'],
        password=os.environ['_DB_WAIT_PASS'],
        connect_timeout=3,
    )
    c.close()
except Exception as e:
    print(type(e).__name__ + ': ' + str(e))
    sys.exit(1)
" 2>&1 || true)
      warn "DB not ready: ${_db_err}"
      _db_first=0
    fi
    printf "."
    sleep 2
  done
  unset _DB_WAIT_HOST _DB_WAIT_USER _DB_WAIT_PASS _DB_WAIT_PORT
  printf "\n"
  log "DB is ready"
fi

# ===== Schema readiness wait（worker / beat 用） =====
# worker / beat は db が healthy になった時点で起動するが、reset 直後は web が
# スキーマ構築（alembic upgrade head）を実行している最中である。構築完了前に
# Celery を動かすと、タスク実行・ログの DB 書き込みが構築途中の部分スキーマへ
# 行を挿入してしまい、構築が中断された際の自動復旧（run_db_migrations.py の
# 「対象テーブルがすべて空なら削除して再構築」）の条件を永遠に満たせなくして
# web をクラッシュループに閉じ込める（2026-07-20 の prod reset 障害）。
# alembic_version にリビジョンが記録される（＝スキーマ構築完了）までここで待つ。
# 上限超過時は警告して起動を続行する（Alembic 管理へ移行していない既存環境を
# 締め出さないため。その場合でも従来と同じ挙動になるだけで悪化はしない）。
wait_for_schema() {
  [ -n "${DATABASE_URI:-}" ] || return 0
  _schema_waited=0
  _schema_limit="${SCHEMA_WAIT_TIMEOUT_SECONDS:-900}"
  log "Waiting for DB schema (alembic_version revision) ..."
  export _DB_WAIT_HOST="$DB_HOST" _DB_WAIT_USER="$DB_USER" \
         _DB_WAIT_PASS="$DB_PASS" _DB_WAIT_PORT="${DB_PORT:-3306}" \
         _DB_WAIT_NAME="$DB_NAME"
  until python -c "
import os, pymysql, sys
try:
    c = pymysql.connect(
        host=os.environ['_DB_WAIT_HOST'],
        port=int(os.environ['_DB_WAIT_PORT']),
        user=os.environ['_DB_WAIT_USER'],
        password=os.environ['_DB_WAIT_PASS'],
        database=os.environ['_DB_WAIT_NAME'],
        connect_timeout=3,
    )
    try:
        with c.cursor() as cur:
            cur.execute('SELECT version_num FROM alembic_version LIMIT 1')
            row = cur.fetchone()
    finally:
        c.close()
except Exception:
    sys.exit(1)
sys.exit(0 if row else 1)
" >/dev/null 2>&1; do
    if [ "$_schema_waited" -ge "$_schema_limit" ]; then
      warn "DB schema not ready after ${_schema_limit}s; starting anyway (Alembic 管理外のDBか、web のスキーマ構築が失敗している可能性。web のログを確認してください)"
      break
    fi
    sleep 5
    _schema_waited=$((_schema_waited + 5))
  done
  unset _DB_WAIT_HOST _DB_WAIT_USER _DB_WAIT_PASS _DB_WAIT_PORT _DB_WAIT_NAME
  if [ "$_schema_waited" -lt "$_schema_limit" ]; then
    log "DB schema is ready"
  fi
}

# ===== Trap =====
term_handler() {
  warn "Signal received, stopping..."
  kill -TERM "$child" 2>/dev/null || true
  wait "$child" 2>/dev/null || true
  log "Shutdown complete"
  exit 0
}

trap term_handler TERM INT

# ===== First-run hook =====
FLAG=/app/data/.initialized
if [ ! -f "$FLAG" ]; then
  log "First-time init"
  touch "$FLAG"
fi

# ===== Mode selection =====
MODE="${1:-web}"
shift || true

case "$MODE" in
  web)
    log "Running DB migrations"
    python scripts/run_db_migrations.py
    log "Starting Gunicorn + UvicornWorker (ASGI web mode)"
    # gunicorn 25+ はデフォルトで制御ソケット（/run/gunicorn.ctl 等）を作成しようとするが、
    # 非rootユーザー実行のこのコンテナでは書き込み権限がなく
    # "[ERROR] Control server error: [Errno 13] Permission denied" が出続ける。未使用機能のため無効化する。
    # UvicornWorker を使うことで ASGI アプリ（asgi.py）を Gunicorn のマルチプロセスで実行する。
    # FastAPI が /api/* を処理し、Flask（WSGI）が UI ルートを処理する Strangler Fig 構成。
    exec gunicorn asgi:app \
      -k uvicorn.workers.UvicornWorker \
      --bind 0.0.0.0:5000 \
      --workers 2 \
      --timeout 120 \
      --graceful-timeout 90 \
      --keep-alive 5 \
      --max-requests 1000 \
      --max-requests-jitter 100 \
      --worker-tmp-dir /dev/shm \
      --no-control-socket
    ;;

  worker)
    wait_for_schema
    log "Starting Celery worker"
    exec celery -A cli.src.celery.tasks worker --loglevel=info --concurrency=2 -Q celery,picker_import
    ;;

  beat)
    wait_for_schema
    log "Starting Celery beat"
    exec celery -A cli.src.celery.tasks beat --loglevel=info --schedule=/app/data/celerybeat-schedule
    ;;

  *)
    log "Executing custom command: $MODE $*"
    exec "$MODE" "$@"
    ;;
esac &

child=$!
wait "$child"
