#!/bin/bash
# リリースパッケージ作成スクリプト

set -e

VERSION=${1:-$(date +"%Y%m%d-%H%M%S")}
RELEASE_DIR="release-${VERSION}"
PACKAGE_NAME="photonest-${VERSION}.tar.gz"

echo "PhotoNest リリースパッケージを作成します..."
echo "バージョン: ${VERSION}"

# 1. リリースディレクトリを作成
echo "Step 1: リリースディレクトリを作成中..."
rm -rf ${RELEASE_DIR}
mkdir -p ${RELEASE_DIR}

# 2. 必要なファイルをコピー
echo "Step 2: 必要なファイルをコピー中..."
cp -r \
    application/ \
    cli/ \
    core/ \
    domain/ \
    infrastructure/ \
    migrations/ \
    webapp/ \
    ${RELEASE_DIR}/

# 設定ファイル
cp \
    main.py \
    wsgi.py \
    requirements-prod.txt \
    Dockerfile \
    docker-compose.yml \
    .dockerignore \
    init.sql \
    deploy.sh \
    build-release.sh \
    .env.production \
    babel.cfg \
    ${RELEASE_DIR}/

# ドキュメント
cp \
    README.md \
    LICENSE \
    ${RELEASE_DIR}/

# 3. 不要なファイルを除去
echo "Step 3: 不要なファイルを除去中..."
find ${RELEASE_DIR} -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find ${RELEASE_DIR} -name "*.pyc" -delete 2>/dev/null || true
find ${RELEASE_DIR} -name "*.pyo" -delete 2>/dev/null || true
find ${RELEASE_DIR} -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true

# 4. バージョン情報ファイルを作成
echo "Step 4: バージョン情報ファイルを作成中..."
cat > ${RELEASE_DIR}/VERSION << EOF
PhotoNest Release Package
Version: ${VERSION}
Build Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Git Commit: $(git rev-parse HEAD 2>/dev/null || echo "N/A")
EOF

# 5. リリースノートを作成
echo "Step 5: リリースノートを作成中..."
cat > ${RELEASE_DIR}/RELEASE_NOTES.md << EOF
# PhotoNest Release ${VERSION}

## デプロイ手順

### 1. 環境変数の設定
\`\`\`bash
cp .env.production .env
# .envファイルを編集して適切な値を設定してください
\`\`\`

### 2. Dockerを使用したデプロイ
\`\`\`bash
# イメージをビルド
./build-release.sh ${VERSION}

# アプリケーションを起動
docker-compose up -d
\`\`\`

### 3. 手動デプロイ
\`\`\`bash
# 依存関係をインストール
pip install -r requirements-prod.txt

# データベースマイグレーション
./deploy.sh
\`\`\`

## 本番環境チェックリスト

- [ ] .envファイルの設定確認
- [ ] データベース接続設定
- [ ] Google OAuth設定
- [ ] セキュリティキーの変更
- [ ] SSL証明書の設定
- [ ] ファイアウォール設定
- [ ] バックアップ設定

## パッケージ内容

- アプリケーションコード
- 本番用Docker設定
- デプロイスクリプト
- データベース設定
- 環境変数テンプレート

EOF

# 6. パッケージを圧縮
echo "Step 6: パッケージを圧縮中..."
tar -czf ${PACKAGE_NAME} ${RELEASE_DIR}/

# 7. チェックサムを生成
echo "Step 7: チェックサムを生成中..."
sha256sum ${PACKAGE_NAME} > ${PACKAGE_NAME}.sha256

# 8. 結果表示
echo "✅ リリースパッケージが作成されました！"
echo ""
echo "ファイル:"
echo "  📦 ${PACKAGE_NAME} ($(du -h ${PACKAGE_NAME} | cut -f1))"
echo "  🔐 ${PACKAGE_NAME}.sha256"
echo "  📁 ${RELEASE_DIR}/"
echo ""
echo "デプロイ手順:"
echo "  1. パッケージを本番サーバーに転送"
echo "  2. tar -xzf ${PACKAGE_NAME}"
echo "  3. cd ${RELEASE_DIR}"
echo "  4. RELEASE_NOTES.mdを参照してデプロイ実行"

# 9. クリーンアップオプション
read -p "一時ディレクトリ ${RELEASE_DIR} を削除しますか? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf ${RELEASE_DIR}
    echo "一時ディレクトリを削除しました"
fi
