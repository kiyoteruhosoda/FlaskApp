#!/bin/bash
# デプロイ先ホスト（NAS）から Photonest をビルド → 取り出し → デプロイする。
# deploybridge の Agent（scripts.json）から photonest/<stg|prod>/build-remote.sh
# として実行される想定（環境ディレクトリに 1 コピーずつ置く）。
#
# 流れ:
#   BUILD  : 開発コンテナ内で git pull + scripts/build.sh を実行し、
#            dist/image.tar（+ image-db.tar / dist/scripts/deploy.sh）を作る
#   PICK   : dist/ の成果物を docker cp でこの環境ディレクトリへ取り出す
#   DEPLOY : scripts/deploy.sh <MODE> を実行する（イメージ load・compose up・
#            ヘルスチェックは deploy.sh が担う）
#
# この script はホストに置いたコピーで動くため git pull では更新されない。
# git pull 後のリポジトリ HEAD とバージョン刻印を照合し、不一致なら自分を
# 更新する（自己更新）。script 本体に変更があった場合は RESTART REQUIRED
# （exit 2）で終了するので、もう一度実行すること。
# ※ 初回のみ、リポジトリのこのファイルをホストの
#    /volume1/docker/photonest/<stg|prod>/build-remote.sh へ手動配置する。
#
# 使い方:
#   ./build-remote.sh [run] [MODE]
#     MODE: app / migrate / reset（deploy.sh のモード。既定: app）
#   第 1 引数は Agent の args 登録用スロット（"run" など）で、値は使わない。
#
# 環境変数で上書き:
#   DEV_CONTAINER      ビルドを実行する開発コンテナ名（既定: ubuntu-dev）
#   DEV_CONTAINER_USER docker exec するユーザー（既定: sshuser）
#   PROJECT_DIR        コンテナ内のリポジトリパス（既定: /work/project/photonest）
#   BUILD_TARGET       scripts/build.sh へ渡すターゲット（既定: all）
set -euo pipefail

# ホストへ配布（自己更新）時にリポジトリの commit hash が刻印される。
# リポジトリ内のこのファイルでは常に unversioned のまま。
BUILD_REMOTE_VERSION="unversioned"

PROJECT=photonest

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
ENV_NAME="$(basename "$SCRIPT_DIR")"

MODE=${2:-app}

DEV_CONTAINER=${DEV_CONTAINER:-ubuntu-dev}
DEV_CONTAINER_USER=${DEV_CONTAINER_USER:-sshuser}
PROJECT_DIR=${PROJECT_DIR:-/work/project/$PROJECT}
BUILD_TARGET=${BUILD_TARGET:-all}

echo "===== START ====="
echo "PROJECT=$PROJECT"
echo "MODE=$MODE"
echo "PWD=$(pwd)"
echo "DATE=$(date)"

case "$ENV_NAME" in
  stg|prod) ;;
  *)
    echo "[build-remote][error] この script は photonest/stg/ または photonest/prod/ に配置して実行してください。" >&2
    echo "  現在の配置: $SCRIPT_DIR（ディレクトリ名 '$ENV_NAME' が stg / prod ではありません）" >&2
    exit 1
    ;;
esac

case "$MODE" in
  app|migrate|reset) ;;
  *)
    echo "[build-remote][error] MODE は app / migrate / reset のいずれかです: '$MODE'" >&2
    exit 1
    ;;
esac

echo "===== BUILD ====="

docker exec -u "$DEV_CONTAINER_USER" "$DEV_CONTAINER" bash -lc "
cd '$PROJECT_DIR' &&
git pull
"

# 自己更新: ビルド対象と script のバージョン（git commit）は一致しているべき。
# pull 後のリポジトリ HEAD と刻印バージョンが不一致なら script を更新する。
# 過去に「pick が最新の deploy.sh を配置したはずなのに古い版が実行され続ける」
# 事故が起きたため、ランチャーであるこの script 自身も必ず最新化してから
# ビルド・デプロイに進む。
REPO_SHA="$(docker exec -u "$DEV_CONTAINER_USER" "$DEV_CONTAINER" bash -lc "cd '$PROJECT_DIR' && git rev-parse --short HEAD")"
echo "repo version: $REPO_SHA / script version: $BUILD_REMOTE_VERSION"

if [ "$BUILD_REMOTE_VERSION" != "$REPO_SHA" ]; then
    SELF_PATH="$SCRIPT_DIR/$(basename "$0")"
    NEW_SELF="$SCRIPT_DIR/.build-remote.sh.new"
    docker cp "$DEV_CONTAINER:$PROJECT_DIR/scripts/build-remote.sh" "$NEW_SELF"
    sed -i "s|^BUILD_REMOTE_VERSION=.*|BUILD_REMOTE_VERSION=\"$REPO_SHA\"|" "$NEW_SELF"
    chmod +x "$NEW_SELF"
    if diff <(grep -v '^BUILD_REMOTE_VERSION=' "$NEW_SELF") \
            <(grep -v '^BUILD_REMOTE_VERSION=' "$SELF_PATH") >/dev/null; then
        # script 本体は同一（他ファイルのみの commit）。刻印だけ更新して続行する
        mv "$NEW_SELF" "$SELF_PATH"
        echo "script unchanged; version stamp updated to $REPO_SHA"
    else
        mv "$NEW_SELF" "$SELF_PATH"
        echo ""
        echo "===== RESTART REQUIRED ====="
        echo "build-remote.sh を $BUILD_REMOTE_VERSION -> $REPO_SHA に更新しました。"
        echo "もう一度実行してください: $SELF_PATH"
        exit 2
    fi
fi

docker exec -u "$DEV_CONTAINER_USER" "$DEV_CONTAINER" bash -lc "
cd '$PROJECT_DIR' &&
./scripts/build.sh '$BUILD_TARGET'
"

echo "===== PICK ====="

# dist/ の成果物をこの環境ディレクトリへ取り出す。deploy.sh は必ず今回ビルドの
# 版で上書きしてから実行する（古いコピーが残っていても実行されないようにする）。
docker cp "$DEV_CONTAINER:$PROJECT_DIR/dist/image.tar" "$SCRIPT_DIR/image.tar"
if docker cp "$DEV_CONTAINER:$PROJECT_DIR/dist/image-db.tar" "$SCRIPT_DIR/image-db.tar" 2>/dev/null; then
    echo "picked: image-db.tar"
else
    echo "image-db.tar は dist/ に無いためスキップ（reset 時のみ必要）"
fi
mkdir -p "$SCRIPT_DIR/scripts"
docker cp "$DEV_CONTAINER:$PROJECT_DIR/dist/scripts/deploy.sh" "$SCRIPT_DIR/scripts/deploy.sh"
chmod +x "$SCRIPT_DIR/scripts/deploy.sh"
echo "picked: image.tar, scripts/deploy.sh"

echo "===== DEPLOY ====="

# 直前の PICK で置いた deploy.sh を絶対パスで実行する（deploy.sh は自身も
# イメージ内の版と照合し、差異があれば自己更新して再実行する二重防御）。
exec bash "$SCRIPT_DIR/scripts/deploy.sh" "$MODE"
