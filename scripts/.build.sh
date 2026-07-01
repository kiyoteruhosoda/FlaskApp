#!/bin/bash
# ローカルで Docker イメージをビルドし TAR を生成する。
# Makefile のラッパー。前提チェック・サマリー表示を追加。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
  cat <<EOF
Usage: $(basename "$0") [TARGET]

  TARGET:
    all   アプリ + DB イメージを両方ビルド（デフォルト）
    app   アプリイメージのみ  → photonest-latest.tar
    db    DB イメージのみ     → photonest-db-latest.tar

  -h, --help  このヘルプを表示

例:
  ./scripts/.build.sh          # 両方ビルド
  ./scripts/.build.sh app      # アプリのみ
  ./scripts/.build.sh db       # DB のみ
EOF
}

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
check_prereqs() {
  local ok=true

  if ! command -v docker &>/dev/null; then
    echo "[error] Docker が見つかりません" >&2
    ok=false
  fi

  if ! docker buildx version &>/dev/null 2>&1; then
    echo "[error] docker buildx が使えません（Docker Desktop 2.x 以上またはプラグインが必要）" >&2
    ok=false
  fi

  if ! command -v make &>/dev/null; then
    echo "[error] make が見つかりません" >&2
    ok=false
  fi

  if ! command -v git &>/dev/null; then
    echo "[error] git が見つかりません" >&2
    ok=false
  fi

  if [ "$ok" = false ]; then
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
TARGET="${1:-all}"

case "$TARGET" in
  -h|--help)
    usage
    exit 0
    ;;
  all|app|db)
    ;;
  *)
    echo "[error] 不明なターゲット: $TARGET" >&2
    usage >&2
    exit 1
    ;;
esac

cd "$PROJECT_ROOT"

check_prereqs

echo ""
echo "=== Photonest ローカルビルド (target: $TARGET) ==="
echo ""

case "$TARGET" in
  all) make all;     ARTIFACTS="photonest-latest.tar photonest-db-latest.tar" ;;
  app) make build;   ARTIFACTS="photonest-latest.tar" ;;
  db)  make build-db; ARTIFACTS="photonest-db-latest.tar" ;;
esac

echo ""
echo "=== ビルド完了 ==="
for f in $ARTIFACTS; do
  if [ -f "$PROJECT_ROOT/$f" ]; then
    size=$(du -sh "$PROJECT_ROOT/$f" | cut -f1)
    echo "  $f  ($size)"
  fi
done
echo ""
echo "次のステップ:"
echo "  scp $ARTIFACTS <user>@<synology-host>:/volume1/docker/"
echo "  # scripts/*.sh や docker-compose.yml を変更した場合は自動同期されないので、"
echo "  # 必要な分だけ手動でコピーする:"
echo "  scp docker-compose.yml <user>@<synology-host>:/volume1/docker/"
echo "  scp scripts/deploy.sh scripts/deploy-stg.sh <user>@<synology-host>:/volume1/docker/scripts/"
echo "  # Synology 上で: ./scripts/deploy.sh app   (migrate/reset は状況に応じて)"
echo ""
