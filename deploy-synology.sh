#!/bin/bash
# Synology用PhotoNestデプロイスクリプト

set -e

echo "PhotoNest Synology デプロイを開始します..."

# 設定
SYNOLOGY_DOCKER_DIR="/volume1/docker/photonest"
SYNOLOGY_IP=${1:-"192.168.1.100"}
SYNOLOGY_USER=${2:-"admin"}

# 必要なディレクトリを作成
echo "Step 1: ディレクトリ構造を作成中..."
mkdir -p synology-deploy/{config,data/{media,thumbs,playback},db,redis}

# Synology用ファイルをコピー
echo "Step 2: Synology用ファイルを準備中..."
cp docker-compose.synology.yml synology-deploy/docker-compose.yml
cp .env.synology synology-deploy/config/.env
cp Dockerfile synology-deploy/
cp -r application/ cli/ core/ domain/ infrastructure/ migrations/ webapp/ synology-deploy/
cp main.py wsgi.py requirements-prod.txt babel.cfg init.sql synology-deploy/
cp SynologyUsage.md synology-deploy/

# デプロイパッケージを作成
echo "Step 3: デプロイパッケージを作成中..."
tar -czf photonest-synology-deploy.tar.gz synology-deploy/

echo "Step 4: Synologyでの手動デプロイ手順を表示..."
cat << 'EOF'

=== Synology手動デプロイ手順 ===

1. File Stationを開いて /docker/ フォルダに移動
2. photonest-synology-deploy.tar.gz をアップロード
3. 以下のコマンドを実行（SSHまたはタスクスケジューラー）：

   cd /volume1/docker/
   tar -xzf photonest-synology-deploy.tar.gz
   mv synology-deploy photonest
   cd photonest

4. Container Managerを開く
5. 「プロジェクト」タブで「作成」をクリック
6. 以下を設定：
   - プロジェクト名: photonest
   - パス: /volume1/docker/photonest
   - docker-compose.ymlをアップロード

7. 環境変数を編集：
   nano config/.env
   
   重要: 以下を必ず変更
   - SECRET_KEY
   - AES_KEY
   - DB_ROOT_PASSWORD
   - DB_PASSWORD

8. プロジェクトを起動

=== アクセス設定 ===

1. コントロールパネル > アプリケーションポータル > リバースプロキシ
2. 設定：
   - ソース: HTTPS, your-nas.synology.me, 443
   - デスティネーション: HTTP, localhost, 5000

3. コントロールパネル > 外部アクセス > DDNS でドメイン設定

EOF

echo ""
echo "✅ Synologyデプロイパッケージが作成されました！"
echo "📦 ファイル: photonest-synology-deploy.tar.gz"
echo "📋 詳細手順: SynologyUsage.md を参照"

# 自動転送オプション（SSH接続可能な場合）
if [ "$3" = "auto" ]; then
    echo ""
    echo "自動転送を実行中..."
    scp photonest-synology-deploy.tar.gz ${SYNOLOGY_USER}@${SYNOLOGY_IP}:/volume1/docker/
    echo "✅ ファイルを ${SYNOLOGY_IP} に転送しました"
    echo "Synologyでtar -xzf /volume1/docker/photonest-synology-deploy.tar.gz を実行してください"
fi

# クリーンアップ
read -p "一時ディレクトリ synology-deploy を削除しますか? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf synology-deploy
    echo "一時ディレクトリを削除しました"
fi
