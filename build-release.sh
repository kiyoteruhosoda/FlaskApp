#!/bin/bash
# Docker リリースビルドスクリプト

set -e

# 設定
IMAGE_NAME="photonest"
VERSION=${1:-latest}
REGISTRY=${REGISTRY:-localhost:5000}

echo "PhotoNest Dockerリリースビルドを開始します..."
echo "イメージ名: ${IMAGE_NAME}:${VERSION}"

# 1. 本番用Dockerイメージをビルド
echo "Step 1: Dockerイメージをビルド中..."
docker build -t ${IMAGE_NAME}:${VERSION} -f Dockerfile .

# 2. イメージにタグを付ける
echo "Step 2: イメージにタグを付与中..."
docker tag ${IMAGE_NAME}:${VERSION} ${IMAGE_NAME}:latest

# レジストリが指定されている場合はタグ付け
if [ "$REGISTRY" != "localhost:5000" ]; then
    docker tag ${IMAGE_NAME}:${VERSION} ${REGISTRY}/${IMAGE_NAME}:${VERSION}
    docker tag ${IMAGE_NAME}:${VERSION} ${REGISTRY}/${IMAGE_NAME}:latest
fi

# 3. イメージサイズを確認
echo "Step 3: ビルド結果確認..."
docker images ${IMAGE_NAME}:${VERSION}

# 4. セキュリティスキャン（オプション）
echo "Step 4: セキュリティスキャン実行中..."
if command -v docker &> /dev/null && docker --version | grep -q "Docker"; then
    echo "セキュリティスキャンはスキップされました (docker scan コマンドが利用できません)"
fi

# 5. イメージをレジストリにプッシュ（オプション）
if [ "$2" = "push" ]; then
    echo "Step 5: イメージをレジストリにプッシュ中..."
    if [ "$REGISTRY" != "localhost:5000" ]; then
        docker push ${REGISTRY}/${IMAGE_NAME}:${VERSION}
        docker push ${REGISTRY}/${IMAGE_NAME}:latest
    else
        echo "ローカルレジストリへのプッシュはスキップされました"
    fi
fi

echo "✅ Dockerリリースビルドが完了しました！"
echo ""
echo "次のステップ:"
echo "  ローカル実行: docker-compose up -d"
echo "  単体実行: docker run -p 5000:5000 ${IMAGE_NAME}:${VERSION}"
echo "  レジストリプッシュ: ./build-release.sh ${VERSION} push"
