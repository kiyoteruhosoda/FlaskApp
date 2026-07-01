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
| `regenerate_db_baseline.sh` | `db/init/01_initialize.sql` を現在の migration head から再生成。DDL変更時、`make build-db` の前に実行する |
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
./scripts/deploy.sh app
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

> **compose ファイルはデプロイ時に自動同期される。** `DOCKER_ROOT` 直下（TAR と同じ場所）に
> リポジトリの `docker-compose.yml` を置いて転送すると、デプロイスクリプトが対応するデプロイ
> ディレクトリ（`photonest/` / `photonest-stg/`）の `docker-compose.yml` へ自動でコピーする。
> `DOCKER_ROOT` 直下・デプロイ先のどちらにも compose が無い場合はエラーで停止する。
> なお起動方法（entrypoint）はイメージに焼き込み済みで、compose は `command`（web / worker /
> beat）でモードのみ指定する。絶対パスの `entrypoint:` 上書きは撤去済みのため、compose の
> 同期漏れによる `exec ... No such file or directory` は原理的に発生しない。

モード引数は必須（省略不可）。

```bash
# 本番：通常デプロイ（アプリのみ更新。DBスキーマ変更なし）
./scripts/deploy.sh app

# 本番：DDL更新（新しい Alembic migration を追加した場合。既存データは保持）
./scripts/deploy.sh migrate

# 本番：完全初期化（DB・メディアデータをすべて削除してから起動）
./scripts/deploy.sh reset

# STG：通常デプロイ
./scripts/deploy-stg.sh app

# STG：DDL更新
./scripts/deploy-stg.sh migrate

# STG：完全初期化
./scripts/deploy-stg.sh reset
```

どのモードを使うかは引数だけで判断できる:

| ケース | モード |
|---|---|
| アプリのみ更新（DDL変更なし） | `app` |
| DDL更新（`migrations/versions/` にファイル追加） | `migrate` |
| DB・メディアを完全に作り直したい（破壊的） | `reset` |

- `migrate` は起動後にコンテナ内で `flask db upgrade` を実行し、既存データを保持したまま
  新しい migration だけを適用する。
- `reset` モードでは DB イメージ（`photonest-db-latest.tar`）も再ロードし、起動後に
  `flask db stamp head` を自動実行する。詳細は次項 `regenerate_db_baseline.sh` 参照。

### regenerate_db_baseline.sh

`db/init/01_initialize.sql` は DBイメージ（`photonest-db-latest.tar`）に焼き込む
フルダンプで、スキーマ + マスタデータ（ロール・権限・初期管理者）を含む。これがあるため
`deploy.sh reset` / `deploy-stg.sh reset` は単独で初期マスタデータ投入済みの状態まで
起動する（`flask seed-master` を別途実行する必要はない）。

`./scripts/regenerate_db_baseline.sh` は、使い捨ての MariaDB コンテナに対して
`flask db upgrade` を実行し（現在の migration head までスキーマ + マスタデータを適用）、
それを `mysqldump` して `01_initialize.sql` を書き出す。既存の開発/STG/本番DBの中身は
一切参照・変更しない。含まれるのはスキーマとマスタデータのみで、業務データ
（メディア・アルバム・`system_settings` の値など）は含まれない。

**DDLを変更したら、`make build-db` の前に必ず実行すること。** ここを忘れると
`01_initialize.sql` のスキーマが古いまま `alembic_version` だけ head 扱いになり、
`deploy.sh reset` で作った DB に対して次回 `migrate` を実行した際、Alembic が
「未適用」と誤認して `init_master` から再実行し `CREATE TABLE` の重複エラーになる
（`deploy.sh`/`deploy-stg.sh` の `reset` が `flask db stamp head` を実行するのはこの
ズレに対する保険）。

再生成忘れの事故は `tests/integration/test_db_baseline_consistency.py` が CI で検出する
（`01_initialize.sql` に焼き込まれた `alembic_version` と現在の migration head を
ファイル同士で突き合わせるだけで、DB接続は不要）。

---

## Docker設定の注意点（healthcheck / イメージサイズ）

### Container Manager（Synology）に出る赤い「Traceback」

**アプリのクラッシュログではなく `healthcheck` の実行結果**（失敗時の標準エラー出力）。
healthcheck はコンテナ内で別プロセスとして定期実行されるため、`docker logs` には出ない。
`docker inspect --format '{{json .State.Health}}' <container>` を `python3 -m json.tool` に通す
で同じ内容を確認できる。

### `web` の healthcheck が `socket.gaierror` で失敗する

`API_BASE_URL`（外部公開ドメイン。CORS 等で使う自己参照 URL）に対して healthcheck が
名前解決しようとして失敗するケース。`API_BASE_URL` は環境ごとに公開ドメインを指すため、
コンテナ内蔵の DNS で解決できるとは限らない。`docker-compose.yml` の `web` healthcheck は
常にコンテナ内部の `http://127.0.0.1:5000/health/live` を叩くようにしてある。

### `[ERROR] Control server error: Permission denied: '/.gunicorn'`

gunicorn 25 以降がデフォルトで作る制御ソケット（`$HOME/.gunicorn/gunicorn.ctl`）を、
非 root ユーザー実行かつ `HOME` 未設定のこのコンテナでは書き込めないために出るエラー。
機能自体を使っていないため、`scripts/entrypoint.sh` の gunicorn 起動オプションに
`--no-control-socket` を付けて無効化している。

### `docker events` にパスワードが平文で出る

`docker-compose.yml` の `healthcheck.test` に `${VAR}` 形式で環境変数を書くと、
docker compose がコンテナ作成時にパスワードそのものへ展開してしまい、
`docker events` の `exec_create`/`exec_start` にコマンド全体が平文で記録される
（`mysqladmin ping ... -p"実際のパスワード"` のように出る）。

対策として `$$VAR`（ドル記号を2つ）でエスケープし、docker compose 側では展開させず
コンテナ内シェルの環境変数参照のまま渡すようにしてある（`db`/`redis` サービスの
healthcheck 参照）。`$$` エスケープなら `docker events` にはリテラルの
`$MARIADB_ROOT_PASSWORD` 等が残るだけで、実際の値は healthcheck 実行時にコンテナ内の
シェルが解決する。

> `redis` サービスの起動コマンド（ACL 設定用の `>${REDIS_PASSWORD}` 部分）はコンテナ
> 作成時の引数としてイメージの起動コマンドに直接埋め込まれる仕様上、`docker inspect` の
> `Config.Cmd` に一度だけ残る。healthcheck のように毎回 `docker events` に出続けるもの
> ではないが、NAS 上で他ユーザーが `docker inspect` できる環境では注意が必要。

新しく healthcheck やコマンドを追加する際は、シークレットを含む値を `${VAR}` で
直接埋め込まない（`$$VAR` にする、または `MYSQL_PWD` のような環境変数経由の認証方式に
寄せる）こと。

### `photonest-latest.tar` が異常に大きい（数GB〜数十GB）

以前の `Dockerfile` は単一ステージで、`frontend/` の実行時には不要な Node.js 本体・npm・
`node_modules`（devDependencies の `@playwright/test` の postinstall がダウンロードする
E2E テスト用ブラウザ Chromium/Firefox/WebKit、各数百MB含む）がそのまま最終イメージに
焼き込まれていた。実行時に必要なのは Flask が配信する `frontend/build/`（Vite の
ビルド成果物）だけなので、`Dockerfile` をマルチステージ化し、`frontend-builder`
（`node:20-slim`）ステージでビルドして `frontend/build` の成果物だけを最終イメージ
（`python:3.11-slim`）へコピーするようにした。`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` で
ビルド時のブラウザダウンロードも止めている。

ビルドキャッシュをリセットしたい場合:
```bash
make clean   # photonest-latest.tar / photonest-db-latest.tar 削除 + builder cache prune
make build
```

イメージサイズの確認:
```bash
docker images photonest:latest
docker history photonest:latest --no-trunc   # どのレイヤーが大きいか確認
```

### `docker build` の "transferring context" が数十GBある

これはイメージサイズとは別の問題で、ビルドコンテキスト（`docker build .` の `.` 配下）
自体が大きいことが原因。`photonest-latest.tar`/`photonest-db-latest.tar` の出力先が
リポジトリ直下（ビルドコンテキストの中）のため、`.dockerignore` で除外していないと
前回ビルドで作った tar 自体が次のビルドのコンテキストに含まれ、ビルドごとに肥大化が
積み重なる。`.gitignore` は `*.tar` を除外していたが `.dockerignore` には無かったため
起きていた。`.dockerignore` に `*.tar` を追加して解消済み。

```bash
# 古い tar がビルドディレクトリに残っていないか確認
du -sh photonest-latest.tar photonest-db-latest.tar 2>/dev/null
```

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
