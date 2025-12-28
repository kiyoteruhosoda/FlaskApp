#!/bin/sh
set -eu

# ===== Colored echo =====
log()  { printf "\033[32m[entrypoint]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[entrypoint][warn]\033[0m %s\n" "$*"; }
err()  { printf "\033[31m[entrypoint][error]\033[0m %s\n" "$*"; }

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
  DB_USER=$(echo "$DATABASE_URI" | sed -E 's#.*://([^:]+):.*#\1#')
  DB_PASS=$(echo "$DATABASE_URI" | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')

  log "Waiting for DB at $DB_HOST ..."
  until mysql -h "$DB_HOST" -u "$DB_USER" "-p$DB_PASS" --skip-ssl -e "SELECT 1" >/dev/null 2>&1; do
    printf "."
    sleep 2
  done
  printf "\n"
  log "DB is ready"
fi

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
  # place migration/init actions here if needed
  touch "$FLAG"
fi

# ===== Mode selection =====
MODE="${1:-web}"
shift || true

case "$MODE" in
  web)
    log "Starting Gunicorn (web mode)"
    exec gunicorn wsgi:app \
      --bind 0.0.0.0:5000 \
      --workers 2 \
      --threads 4 \
      --timeout 120 \
      --graceful-timeout 90 \
      --keep-alive 5 \
      --max-requests 1000 \
      --max-requests-jitter 100 \
      --worker-tmp-dir /dev/shm
    ;;

  worker)
    log "Starting Celery worker"
    exec celery -A cli.src.celery.tasks worker --loglevel=info --concurrency=2 -Q celery,picker_import
    ;;

  beat)
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
