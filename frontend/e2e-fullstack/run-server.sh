#!/usr/bin/env bash
# フルスタックE2E用の実サーバー起動スクリプト。
#
# 実 FastAPI サーバー ＋ 実DB（ファイルベース SQLite）＋ ビルド済み SPA
# （FastAPI が frontend/build を静的配信）を起動する。DB は毎回まっさらに作り直し、
# scripts/run_db_migrations.py でスキーマ・マスタデータ（初期管理者
# admin@example.com / admin@example.com）を投入する。
#
# Python は `${E2E_PYTHON:-python}` を使う（CI では venv の python を指す想定。
# ローカル検証では `E2E_PYTHON="uv run python"` などを渡す）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT}"

DB_FILE="${SCRIPT_DIR}/.e2e-fullstack.db"
PORT="${E2E_PORT:-8100}"
PY="${E2E_PYTHON:-python}"

export TESTING="true"
export DATABASE_URI="sqlite:///${DB_FILE}"
export SECRET_KEY="${SECRET_KEY:-e2e-fullstack-secret}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-e2e-fullstack-jwt}"
export ACCESS_TOKEN_ISSUER="${ACCESS_TOKEN_ISSUER:-photonest-e2e}"
export ACCESS_TOKEN_AUDIENCE="${ACCESS_TOKEN_AUDIENCE:-photonest-e2e}"
export GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}"
export GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-}"

# 毎回まっさらな DB から作り直す（決定論的なフィクスチャのため）
rm -f "${DB_FILE}"

echo "[e2e-fullstack] applying migrations to ${DB_FILE}"
${PY} scripts/run_db_migrations.py

echo "[e2e-fullstack] starting uvicorn on 127.0.0.1:${PORT}"
exec ${PY} -m uvicorn asgi:app --host 127.0.0.1 --port "${PORT}"
