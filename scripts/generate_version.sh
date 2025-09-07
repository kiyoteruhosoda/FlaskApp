#!/bin/bash
# バージョンファイル生成スクリプト
# ビルド時やデプロイ時に実行して、バージョン情報をJSONファイルに保存

set -e

# スクリプトのディレクトリに移動
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$PROJECT_ROOT/core/version.json"

echo "バージョンファイルを生成しています..."

# Gitから情報を取得（Gitが利用可能な場合）
if command -v git >/dev/null 2>&1 && [ -d "$PROJECT_ROOT/.git" ]; then
    COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    COMMIT_HASH_FULL=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    COMMIT_DATE=$(git log -1 --format=%ci 2>/dev/null || echo "unknown")
    
    # バージョン文字列を生成
    if [ "$BRANCH" = "main" ]; then
        VERSION="v$COMMIT_HASH"
    else
        VERSION="v$COMMIT_HASH-$BRANCH"
    fi
else
    echo "Warning: Git not available, using default values"
    COMMIT_HASH="unknown"
    COMMIT_HASH_FULL="unknown"
    BRANCH="unknown"
    COMMIT_DATE="unknown"
    VERSION="dev"
fi

# ビルド日時
BUILD_DATE=$(date -Iseconds)

# バージョンJSONファイルを生成
cat > "$VERSION_FILE" << EOF
{
    "version": "$VERSION",
    "commit_hash": "$COMMIT_HASH",
    "commit_hash_full": "$COMMIT_HASH_FULL",
    "branch": "$BRANCH",
    "commit_date": "$COMMIT_DATE",
    "build_date": "$BUILD_DATE"
}
EOF

echo "バージョンファイルが生成されました: $VERSION_FILE"
echo "バージョン: $VERSION"
echo "コミット: $COMMIT_HASH ($BRANCH)"
echo "ビルド日時: $BUILD_DATE"
