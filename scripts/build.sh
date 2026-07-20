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
    app   アプリイメージのみ  → dist/image.tar
    db    DB イメージのみ     → dist/image-db.tar

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

# 作業ツリーの検証は Makefile の build / build-db ターゲットの前提
# （check-worktree → scripts/check_worktree_clean.sh）として実行される。
# どのビルド入口（make 直接実行を含む）でも同じチェックを通る。

GIT_COMMIT="$(git rev-parse --short HEAD)"
GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

echo ""
echo "=== Photonest ローカルビルド (target: $TARGET) ==="
echo ""

BUILD_START=$(date +%s)

case "$TARGET" in
  all) make all;     ARTIFACTS="dist/image.tar dist/image-db.tar dist/scripts/deploy.sh" ;;
  app) make build;   ARTIFACTS="dist/image.tar dist/scripts/deploy.sh" ;;
  db)  make build-db; ARTIFACTS="dist/image-db.tar dist/scripts/deploy.sh" ;;
esac

BUILD_END=$(date +%s)
BUILD_ELAPSED=$((BUILD_END - BUILD_START))

echo ""
echo "=== ビルド完了 ==="
echo "Git バージョン: $GIT_COMMIT ($GIT_BRANCH)"
for f in $ARTIFACTS; do
  if [ -f "$PROJECT_ROOT/$f" ]; then
    size=$(du -sh "$PROJECT_ROOT/$f" | cut -f1)
    echo "  $f  ($size)"
  fi
done
echo ""
echo "所要時間: $((BUILD_ELAPSED / 60))分$((BUILD_ELAPSED % 60))秒"
echo "次のステップ:"
echo "  dist/ の中身を NAS の photonest/<stg|prod>/ へ配置する（NAS 側の pick.sh 等）:"
echo "    dist/image.tar          -> photonest/<env>/image.tar"
echo "    dist/image-db.tar       -> photonest/<env>/image-db.tar   (あれば)"
echo "    dist/scripts/deploy.sh  -> photonest/<env>/scripts/deploy.sh"
echo "  # docker-compose.yml はアプリイメージに焼き込まれており、デプロイ時に"
echo "  # イメージから自動で取り出される（手動コピー不要）。"
echo "  # NAS 上で: cd photonest/<env> && ./scripts/deploy.sh app  (migrate/reset は状況に応じて)"
echo ""

