# scripts/

運用・デプロイ・開発補助用のスクリプト集。

## 実行環境

プロジェクトルートで実行してください。Python スクリプトは `.venv` を有効化した状態で使用します。

```bash
source .venv/bin/activate
```

---

## デプロイ・インフラ

| スクリプト | 用途 |
|---|---|
| `.build.sh` | ローカルで Docker イメージをビルドし TAR を生成。前提チェック付き |
| `entrypoint.sh` | Docker コンテナ起動スクリプト。`docker-compose.yml` から使用（web / worker / beat モード切替） |
| `deploy.sh` | 本番（`/volume1/docker/photonest`）向けデプロイスクリプト |
| `deploy-stg.sh` | STG（`/volume1/docker/photonest-stg`）向けデプロイスクリプト |
| `generate_version.sh` | `shared/kernel/version.json` を生成。`Makefile` の `make build` から自動呼び出し |
| `fix_redis_aof.sh` | Redis の AOF ファイルが壊れたときの緊急修復スクリプト |

### .build.sh

ローカルビルドのエントリーポイント。Docker / buildx / make / git の前提チェックを行ったうえで `make` を呼び出し、完了後に成果物のパスとサイズを表示します。

```bash
# アプリ + DB を両方ビルド（推奨）
./scripts/.build.sh

# アプリイメージのみ → photonest-latest.tar
./scripts/.build.sh app

# DB イメージのみ → photonest-db-latest.tar
./scripts/.build.sh db

# ヘルプ
./scripts/.build.sh --help
```

ビルド後の流れ:

```bash
# 生成した TAR を Synology に転送
scp photonest-latest.tar photonest-db-latest.tar <user>@<synology-host>:/volume1/docker/

# Synology 上でデプロイ（SSH 接続後）
./scripts/deploy.sh
```

### deploy.sh / deploy-stg.sh

スクリプトの位置（`scripts/`）から `DOCKER_ROOT`（`/volume1/docker`）を自動導出します。
TAR ファイルは `DOCKER_ROOT` 直下、compose ディレクトリはその下に配置してください。

```
/volume1/docker/
├── photonest/           ← docker-compose.yml + .env（本番）
├── photonest-stg/       ← docker-compose.yml + .env（STG）
├── photonest-latest.tar
├── photonest-db-latest.tar
└── scripts/
    ├── deploy.sh
    └── deploy-stg.sh
```

> **compose ファイルはリポジトリと手動同期する。** `photonest/` と `photonest-stg/` の
> `docker-compose.yml` はリポジトリ直下の `docker-compose.yml` の**コピー**であり、デプロイ
> スクリプトは同期しない（イメージの TAR ロードと再起動のみ行う）。リポジトリ側の
> `docker-compose.yml` を更新したら、対応するデプロイディレクトリへ必ずコピーし直すこと。
> 同期漏れがあると古い設定のまま起動し、`exec ... No such file or directory` 等の起動失敗を招く。

```bash
# 本番：通常デプロイ（コンテナ停止 → イメージロード → 起動 → ヘルスチェック）
./scripts/deploy.sh

# 本番：完全初期化（DB・メディアデータをすべて削除してから起動）
./scripts/deploy.sh reset

# STG：通常デプロイ
./scripts/deploy-stg.sh

# STG：完全初期化
./scripts/deploy-stg.sh reset
```

reset モードでは DB イメージ（`photonest-db-latest.tar`）も再ロードします。

---

## 初期データ投入・セットアップ

| スクリプト | 用途 |
|---|---|
| `seed_master_data.py` | 初期ユーザー・ロール・パーミッションを DB に投入 |
| `bootstrap_system_settings.py` | システム設定テーブルを環境変数の値で初期化（upsert） |

```bash
# 初期ユーザー・ロール・パーミッション投入
python scripts/seed_master_data.py

# システム設定の初期化（環境変数から読み込み）
python scripts/bootstrap_system_settings.py
```

> `flask seed-master` コマンドは `seed_master_data.py` と同等の処理を行います。

---

## デバッグ・確認

| スクリプト | 用途 |
|---|---|
| `check_logs.py` | picker_import タスクのログを DB から検索・表示 |
| `demo_cdn_configuration.py` | CDN / Blob Storage の現在の設定値を確認 |
| `demo_cdn_integration.py` | CDN 統合機能（Azure / CloudFlare）の動作デモ |
| `demo_storage.py` | Storage 境界コンテキストの DDD 実装デモ |

### check_logs.py

```bash
# 直近20件（デフォルト）を表示
python scripts/check_logs.py

# セッション ID 123 のログを絞り込み
python scripts/check_logs.py --session-id 123

# イベント種別で絞り込み
python scripts/check_logs.py --event picker.session.complete --last 10

# レベルで絞り込み
python scripts/check_logs.py --level ERROR

# JSON 出力
python scripts/check_logs.py --json --last 50
```

### demo_cdn_configuration.py

```bash
# CDN 設定を確認
python scripts/demo_cdn_configuration.py --cdn

# Blob Storage 設定を確認
python scripts/demo_cdn_configuration.py --blob

# CDN 機能のデモ実行
python scripts/demo_cdn_configuration.py --demo
```
