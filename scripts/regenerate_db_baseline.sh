#!/bin/bash
# db/init/01_initialize.sql（DBイメージに焼き込むベースラインSQL）を、現在の
# Alembic migration head から再生成する。
#
# 使い方（リポジトリルートで、.venv を有効化した状態で実行）:
#   ./scripts/regenerate_db_baseline.sh
#
# 何をするか:
#   1. 使い捨ての MariaDB コンテナを起動する（既存の開発/STG/本番DBとは無関係）
#   2. 空のそのDBに対して `flask db upgrade` を実行し、現在の migration head まで
#      スキーマとマスタデータ（ロール・権限・初期管理者。versions/*_seed_master_data.py 経由）
#      を適用する
#   3. mysqldump で db/init/01_initialize.sql を書き出す（alembic_version も含む）
#   4. 使い捨てコンテナを削除する
#
# 生成される 01_initialize.sql に含まれるのはスキーマ + マスタデータのみ。
# 業務データ（メディア・アルバム・system_settings の値など）は一切含まれない
# （常に空のDBから作るため）。既存の開発/STG/本番DBの中身は一切参照・変更しない。
#
# 再生成後は `make build-db` でDBイメージをリビルドすること。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
OUT_FILE="$ROOT_DIR/db/init/01_initialize.sql"

if ! command -v flask >/dev/null 2>&1; then
  echo "[baseline][error] 'flask' コマンドが見つかりません。.venv を有効化してから実行してください:" >&2
  echo "  source .venv/bin/activate" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[baseline][error] docker コマンドが見つかりません。" >&2
  exit 1
fi

CONTAINER_NAME="photonest-db-baseline-$$"
DB_ROOT_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
DB_PORT="${DB_BASELINE_PORT:-33061}"
DB_NAME="appdb"

cleanup() {
  echo "[baseline] Removing ephemeral container"
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[baseline] Starting ephemeral MariaDB container ($CONTAINER_NAME)"
docker run -d --name "$CONTAINER_NAME" \
  -e MARIADB_ROOT_PASSWORD="$DB_ROOT_PASSWORD" \
  -e MARIADB_DATABASE="$DB_NAME" \
  -p "127.0.0.1:${DB_PORT}:3306" \
  mariadb:10.11 --default-time-zone=+00:00 >/dev/null

echo "[baseline] Waiting for MariaDB to accept connections"
ready=0
for i in $(seq 1 60); do
  if docker exec "$CONTAINER_NAME" mysqladmin ping -h localhost -u root -p"$DB_ROOT_PASSWORD" --silent >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" != "1" ]; then
  echo "[baseline][error] MariaDB did not become ready in time" >&2
  exit 1
fi

echo "[baseline] Applying migrations to head (flask db upgrade)"
DATABASE_URI="mysql+pymysql://root:${DB_ROOT_PASSWORD}@127.0.0.1:${DB_PORT}/${DB_NAME}?charset=utf8mb4" \
  flask db upgrade

echo "[baseline] Dumping schema + master data to $OUT_FILE"
docker exec "$CONTAINER_NAME" \
  mysqldump -u root -p"$DB_ROOT_PASSWORD" \
    --single-transaction --routines --triggers --no-tablespaces \
    "$DB_NAME" > "$OUT_FILE"

echo "[baseline] Done: $OUT_FILE"
echo "[baseline] Next: make build-db"
