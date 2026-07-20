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
| `.build.sh` | ローカルで Docker イメージをビルドし `dist/` に成果物を生成。前提チェック付き |
| `entrypoint.sh` | Docker コンテナ起動スクリプト。`docker-compose.yml` から使用（web / worker / beat モード切替） |
| `deploy.sh` | stg / prod 共通デプロイスクリプト（配置ディレクトリ名で環境を自動判定） |
| `generate_version.sh` | `shared/kernel/version.json` を生成。`Makefile` の `make build` から自動呼び出し |
| `fix_redis_aof.sh` | Redis の AOF ファイルが壊れたときの緊急修復スクリプト |

### .build.sh

ローカルビルドのエントリーポイント。Docker / buildx / make / git の前提チェックを行ったうえで `make` を呼び出し、完了後に成果物のパスとサイズを表示します。

```bash
# アプリ + DB を両方ビルド（推奨）
./scripts/.build.sh

# アプリイメージのみ → dist/image.tar
./scripts/.build.sh app

# DB イメージのみ → dist/image-db.tar
./scripts/.build.sh db

# ヘルプ
./scripts/.build.sh --help
```

ビルド前に作業ツリーを検証する: コミットされていない変更（追跡ファイルの変更・
未追跡ファイル）があるとエラー終了する（イメージには作業ツリーがそのまま
焼き込まれるため、リポジトリと一致しない成果物を作らない）。この検証は
`Makefile` の `build` / `build-db` ターゲットの前提（`check-worktree` →
`scripts/check_worktree_clean.sh`）として実行されるため、`make build` を直接
実行した場合も必ず通る。意図的にローカル変更込みでビルドする場合のみ
`ALLOW_DIRTY=1` を付けて回避できる。イメージに入れたくないファイルを常置する
場合は `.gitignore` へ追加する。

ビルド成果物はすべて `dist/`（git 管理外）に置かれる:

```
dist/
├── image.tar          # アプリイメージ（docker save）
├── image-db.tar       # DB イメージ（make build-db / all 実行時）
└── scripts/
    └── deploy.sh      # デプロイスクリプト（git 管理コピー）
```

### deploy.sh（stg / prod 共通）

NAS 側は環境ごとに自己完結したディレクトリ構成とし、`deploy.sh` は自分の
配置ディレクトリ（`photonest/stg/` か `photonest/prod/` か）から環境を自動判定する。

```
photonest/
├── stg/
│   ├── image.tar           ← dist/image.tar を配置（pick.sh で取得）
│   ├── image-db.tar        ← (任意) dist/image-db.tar。reset 時のみ使用
│   ├── scripts/deploy.sh   ← dist/scripts/deploy.sh を配置（git 管理）
│   ├── .env                ← stg 用設定（無ければ初回デプロイで自動生成）
│   ├── docker-compose.yml  ← stg 用（デプロイ時にイメージ内のコピーで自動更新）
│   ├── mnt/                ← コンテナマウント用データ（data/ と db_data/）
│   └── pick.sh             ← イメージ取得用（git 管理外・運用者が用意）
└── prod/                   ← 上記と同じ構成
```

- 環境判定: 親ディレクトリ名が `stg` → compose project `photonest-stg`・ポート既定 8051、
  `prod` → project `photonest`（既存本番を引き継ぐ）・ポート既定 8050。
  それ以外のディレクトリ名で実行するとエラー終了する。
- ロードしたイメージは `photonest:stg` / `photonest:prod` のように環境別タグを
  付け直して使う（同一ホストで stg と prod が `photonest:latest` を取り合わない）。
- マウントデータは `<環境dir>/mnt/` 配下（`.env` の `HOST_DATA_ROOT` で上書き可）。
  `reset` モードが削除するのはこの `mnt/data` と `mnt/db_data`。
- ヘルスチェック先ポートは `.env` の `WEB_HOST_PORT`（未設定時は環境別既定値）に追従する。
- **デプロイエラー時は失敗したモジュール（コンテナ）のログを出力して終了する**
  （DB 接続待ちタイムアウト → db、マイグレーション失敗 → web + db、
  ヘルスチェック失敗 → web + nginx。想定外のエラーは全サービスのログを出す）。
- ネットワークは Docker の自動割当（compose に subnet 指定なし）。同期した compose に
  固定 subnet 指定が残っている場合は警告を出す（古い作業ツリーからビルドされた
  イメージの検出）。`docker compose up` が "Pool overlaps" で失敗した場合は、
  ホスト上の全 Docker ネットワークの subnet・compose プロジェクトラベル一覧を
  診断出力したうえで **5秒後に1回だけ再試行する**（subnet 指定なしでもデーモンの
  IPAM に削除済みネットワークの残骸があると発生し得るため。再試行では別プールが
  選ばれ成功し得る）。再試行でも失敗し、かつ一覧に重複相手が見当たらない場合は
  IPAM 残骸が原因なので、Docker（Container Manager）を再起動して再デプロイする:
  `sudo synopkg restart ContainerManager`（DSM 7.x）。
  また `down` 後、`.env` の `DOCKER_NETWORK_NAME` と同名の残留
  ネットワークが存在すれば削除する（コンテナ接続中なら警告のみ）。

> **docker-compose.yml・nginx 設定・deploy.sh 自身はアプリイメージから自己同期される。**
> アプリイメージには `docker-compose.yml`（→ `/app/docker-compose.yml`）・nginx 設定
> （→ `/app/docker/nginx/default.conf`）・`deploy.sh`（→ `/app/scripts/deploy.sh`）が
> 焼き込まれており、`docker load` 直後に取り出して環境ディレクトリへ展開する
> （イメージ内が唯一の出所）。実行中の `deploy.sh` がイメージ内の版と異なる場合は
> 自己更新して同じモード引数で自動的に再実行する（一致時は「最新版で実行中」と
> ログに出る）。環境ごとの違い（ポート・資格情報等）はすべて `.env` 側で表現する。
> なお起動方法（entrypoint）もイメージに焼き込み済みで、compose は `command`（web / worker /
> beat）でモードのみ指定する。
> この自己同期の前提（`.dockerignore` が compose を除外しない等）は
> `tests/integration/test_deploy_asset_sync_consistency.py` が検証する。

> **`.env` は事前作成不要（初期設定のみで動作する）。** 不在の場合はデプロイスクリプトが
> コメント付きテンプレートを自動生成し、資格情報・JWT秘密鍵などは `docker-compose.yml` の
> `${VAR:-default}` と `system_settings_defaults.py` の既定値で起動する
> （生成 `.env` は環境別のポート・ネットワーク名等を固定する）。既定の資格情報は
> 開発向けのため、外部公開する環境では生成された `.env` を編集して再デプロイする。
> 既存の `.env` には一切触れない。この前提は
> `tests/unit/core/test_zero_config_deploy_defaults.py` が検証する。

モード引数は必須（省略不可）。環境ディレクトリ（`photonest/stg` または
`photonest/prod`）で実行する。

```bash
# 通常デプロイ（アプリのみ更新。DBスキーマ変更なし）
./scripts/deploy.sh app

# DDL更新（新しい Alembic migration を追加した場合。既存データは保持）
./scripts/deploy.sh migrate

# 完全初期化（DB・メディアデータをすべて削除してから起動）
./scripts/deploy.sh reset
```

どのモードを使うかは引数だけで判断できる:

| ケース | モード |
|---|---|
| アプリのみ更新（DDL変更なし） | `app` |
| DDL更新（`migrations/versions/` にファイル追加） | `migrate` |
| DB・メディアを完全に作り直したい（破壊的） | `reset` |

- `migrate` は起動後にコンテナ内で `scripts/run_db_migrations.py`（`alembic upgrade head`
  を安全に実行するラッパー、後述）を実行し、既存データを保持したまま新しい migration
  だけを適用する。
- `reset` モードでは DB イメージ（`image-db.tar`）も再ロードして `mnt/db_data` を
  削除し、空の DB に対して同スクリプト（`init_master` + `seed_master_data`）で
  スキーマとマスタデータを構築する。

DB イメージはスキーマを焼き込まない素の MariaDB（UTC 固定）で、スキーマ・マスタデータの
構築は常に web コンテナ起動時の `scripts/run_db_migrations.py`（`scripts/entrypoint.sh`
から呼ばれる）が担う。DDL を変更したら migration を追加するだけでよく、ベースライン SQL
の再生成手順は不要。

`scripts/run_db_migrations.py` は素の `alembic upgrade head` の薄いラッパーで、適用前に
実テーブルの有無と `alembic_version` に記録されたリビジョンを調べる。Alembic 管理外
（過去の焼き込みベースライン運用の名残等）で既にテーブルが存在する DB に対して素朴に
`upgrade head` すると `init_master` が全テーブルを `CREATE TABLE` しようとして
`Table '...' already exists` で失敗するため、その場合は自動で `stamp init_master` して
から `upgrade head` する。「Alembic 管理下かどうか」は `alembic_version` テーブルの
有無ではなく記録されたリビジョンの有無で判定する（テーブルが在っても空なら管理外扱いで
自己修復の対象）。一部だけテーブルが存在する中途半端な状態は自動判断せずエラー終了する
（詳細は `migrations/README.md`）。

---

## Docker設定の注意点（healthcheck / イメージサイズ）

- Container Manager に出る赤い traceback は `healthcheck` の実行結果（`docker logs` には
  出ない）。`docker inspect --format '{{json .State.Health}}' <container>` を
  `python3 -m json.tool` に通すと同じ内容を確認できる。
- `web` の healthcheck は常にコンテナ内部の `http://127.0.0.1:5000/health/live` を見る
  （`API_BASE_URL` は見ない）。
- `scripts/entrypoint.sh` の gunicorn 起動オプションに `--no-control-socket` を付けている。
- `db`/`redis` の healthcheck はシークレットを `$$VAR`（ドル記号2つ）でエスケープしている。
  新しく healthcheck やコマンドを追加する際は、シークレットを含む値を `${VAR}` で直接
  埋め込まない（`$$VAR` にする、または `MYSQL_PWD` のような環境変数経由の認証方式に寄せる）こと。
- `Dockerfile` は `frontend-builder`（`node:20-slim`）ステージでフロントエンドをビルドし、
  `frontend/build` の成果物だけを最終イメージへコピーするマルチステージ構成。
  ビルドキャッシュをリセットしたい場合は `make clean && make build`。
- `.dockerignore` は `*.tar` 等のビルド成果物を除外している。新しい出力ファイルを
  リポジトリ直下に置く場合は `.dockerignore` にも追記すること。

過去の不具合の経緯・原因は `docs/CHANGELOG.md` を参照。

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
