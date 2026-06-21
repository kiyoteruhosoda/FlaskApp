#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$PROJECT_ROOT/core/version.json"

echo "バージョンファイルを生成しています..."

if command -v git >/dev/null 2>&1 && [ -d "$PROJECT_ROOT/.git" ]; then
    # 明示的に .git とプロジェクトルートを指定
    GIT="git --git-dir=$PROJECT_ROOT/.git --work-tree=$PROJECT_ROOT"

    COMMIT_HASH=$($GIT rev-parse --short HEAD 2>/dev/null || echo "unknown")
    COMMIT_HASH_FULL=$($GIT rev-parse HEAD 2>/dev/null || echo "unknown")
    BRANCH=$($GIT rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    COMMIT_DATE=$($GIT log -1 --format=%ci 2>/dev/null || echo "unknown")

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

BUILD_DATE=$(date -Iseconds)

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
