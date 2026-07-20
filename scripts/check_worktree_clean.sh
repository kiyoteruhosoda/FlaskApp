#!/bin/bash
# ビルド前の作業ツリー検証。
#
# イメージには作業ツリーの内容がそのまま焼き込まれる（Dockerfile の COPY . /app）。
# コミットされていない内容（追跡ファイルの変更・未追跡ファイル）が残ったまま
# ビルドすると、version.json 上は最新コミットを名乗るのに中身がリポジトリと
# 一致しない成果物ができる。デプロイ先ではイメージ内の docker-compose.yml を
# 唯一の出所として使うため、この不一致は「修正したはずの障害が再発し続ける」
# という原因の特定しにくい形で現れる。
#
# すべてのビルド入口をカバーするため、Makefile の build / build-db ターゲットの
# 前提（check-worktree）として実行される（scripts/.build.sh は make 経由で通る）。
# 意図的にローカル変更込みでビルドする場合のみ ALLOW_DIRTY=1 で回避できる。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [ "${ALLOW_DIRTY:-0}" = "1" ]; then
  echo "[warn] ALLOW_DIRTY=1: 作業ツリーの変更チェックをスキップします（成果物はリポジトリと一致しない可能性があります）" >&2
  exit 0
fi

# 追跡ファイルの変更に加え、未追跡ファイル（.gitignore 対象外）も検出する。
# 未追跡ファイルも COPY . /app でイメージへ焼き込まれるため、コミットに現れない
# 内容が成果物へ混入し得る。判定を単純に保つため .dockerignore は考慮しない
# （イメージに入れないファイルを常置したい場合は .gitignore へ追加する）。
dirty="$(git status --porcelain --untracked-files=all)"
if [ -n "$dirty" ]; then
  echo "[error] コミットされていない変更（追跡ファイルの変更・未追跡ファイル）があります:" >&2
  echo "$dirty" | sed 's/^/    /' >&2
  echo "[error] この状態でビルドすると上記の内容がイメージに焼き込まれ、" >&2
  echo "        version.json のコミットとリポジトリの内容が一致しない成果物ができます。" >&2
  echo "        commit / stash / 削除 / .gitignore への追加で解消してから再実行してください。" >&2
  echo "        （意図的にローカル変更込みでビルドする場合: ALLOW_DIRTY=1 を付けて実行）" >&2
  exit 1
fi
