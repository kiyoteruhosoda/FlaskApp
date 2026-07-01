# CHANGELOG

完了した重要な変更を記録する（運用ルール: 完了項目は Progress.md から本ファイルへ移す）。
新しいものを上に追記する。書式は概ね Keep a Changelog 準拠。

## [Unreleased]

### Fixed
- `docs/OPERATIONS.md`「3. デプロイ」「5. ログ監視」のログ確認コマンド例を修正。
  `docker compose logs <サービス名>` は `docker-compose.yml`/`.env` があるディレクトリ
  （`/volume1/docker/photonest` 等）で実行する必要があるが、その前提が書かれておらず
  `/volume1/docker` 直下で実行すると `Failed to load /volume1/docker/.env` で失敗して
  いた。また引数はサービス名（`web`/`worker`等）であってコンテナ名
  （`photonest-web-1`等）ではないため、「コンテナ構成」の表記もサービス名に修正した。

### Added
- `deploy.sh`/`deploy-stg.sh` に Docker daemon 疎通の preflight チェックを追加。
  `sudo` なしで実行して `docker.sock` への `permission denied` が起きた場合、
  `docker load` の途中まで進んでから `set -e` で無言終了していた（コンテナは何も
  変更されない）。実行直後に分かりやすいエラーで案内するよう変更。あわせて
  `load_image_with_progress` のハートビートが `docker load` 失敗直後にも1回だけ
  「まだ読み込み中」と誤表示していた不具合を修正し、失敗時は明示的にエラー終了する
  ようにした。
- `tests/integration/test_db_baseline_consistency.py` を追加。`db/init/01_initialize.sql`
  に焼き込まれた `alembic_version` と現在の migration head を突き合わせる回帰テスト
  （DB接続不要、ファイル突き合わせのみ）。`scripts/regenerate_db_baseline.sh` の
  再生成忘れを CI で検出する。
- `scripts/regenerate_db_baseline.sh` を追加。`db/init/01_initialize.sql`
  （DBイメージに焼き込むベースラインSQL）の再生成を自動化。使い捨ての MariaDB
  コンテナに対して `flask db upgrade` を実行し、現在の migration head の
  スキーマ + マスタデータ（roles/permissions/初期管理者）をダンプする。
  既存の開発/STG/本番DBは一切参照・変更しない。手動 `mysqldump` の運用を廃止。
  `make regen-db-baseline` からも呼び出せる。詳細は `scripts/README.md` /
  `docs/OPERATIONS.md`「2. データベース操作」参照。
- `scripts/deploy.sh` / `scripts/deploy-stg.sh` のモード引数を必須化し、
  「アプリのみ更新（`app`）」「DDL更新（`migrate`＝`flask db upgrade`を自動実行、
  既存データ保持）」「完全初期化（`reset`）」を明示引数だけで切り替えられるようにした
  （引数省略時のデフォルト`deploy`は廃止）。
  `reset` は起動後に `flask db stamp head` を自動実行し、`db/init/01_initialize.sql`
  焼き込み時に空のまま投入される `alembic_version` を head に揃える（放置すると次回
  `migrate` が `init_master` から再実行され `CREATE TABLE` 重複エラーになっていた）。
  詳細は `scripts/README.md` / `docs/OPERATIONS.md`「2. データベース操作」参照。
- CLI `flask rebuild-originals`：`MEDIA_ORIGINALS_DIRECTORY` を直接走査して Media を
  再登録（冪等、`--dry-run`/`--refresh`/`--verbose`）。DB 初期化後の復旧用。
- 重複メディアのレビュー画面（`/media/duplicates`）と API `GET /api/media/duplicates`。
  exact(sha256)/similar(phash) でグループ化し人手で残す1枚を選択、他をソフト削除。詳細は ADR-0003。
- マイグレーション/モデル乖離の回帰テスト `tests/integration/test_migration_model_consistency.py`
  （単一ベース/ヘッド検証 + autogenerate 差分ゼロ検証）。
- CI ワークフロー `.github/workflows/test.yml`（push/PR でドリフトテスト実行）。
- 認可マスタデータの単一カタログ `shared/domain/auth/master_data.py` と、冪等な
  データマイグレーション `versions/*_seed_master_data.py`。
- `media.google_media_id` の一意制約と、Google Photos 取り込みの「復活方式」
  （`_upsert_google_media`：既存行をソフト削除含め復活・更新）。
- 設定フラグ `REQUIRE_PASSWORD_CHANGE_ON_FIRST_LOGIN`（既定 OFF、土台のみ）。
- マイグレーション運用 README（`migrations/README.md`）。

### Fixed
- `db/init/01_initialize.sql` が実際には migration head（`3b7c2e9a1f08`: media.google_media_id
  の一意制約）より古いまま放置されていた既存の乖離を修正（`media` テーブルへの
  `uq_media_google_media_id` 追加、`alembic_version` へ head を記録）。
  再発防止として上記の `test_db_baseline_consistency.py` を追加。
- `.dockerignore` に `*.tar` 等を追加。`photonest-latest.tar`/`photonest-db-latest.tar`
  が `.gitignore` では除外済みでも `.dockerignore` からは漏れていたため、ビルドの
  たびに前回出力した数十GB規模の tar がビルドコンテキストとしてスキャン・転送され
  （`docker build` の "transferring context" が数十GBに達する）原因になっていた。
  あわせて `.pytest_cache` / `test-results` / `playwright-report` 等のローカル
  開発・テスト成果物も除外。
- `Dockerfile` をマルチステージ化し、`photonest-latest.tar` の異常な肥大化を修正。
  Node.js 本体・npm・`node_modules`（devDependencies の `@playwright/test` が
  ダウンロードする E2E テスト用ブラウザ含む）は `frontend/build` のビルドにしか使わないが、
  従来は単一ステージで最終イメージにそのまま焼き込まれていた。`frontend-builder`
  （`node:20-slim`）ステージでビルドし、`frontend/build` の成果物だけを最終イメージへ
  コピーするよう変更。`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` でビルド時のブラウザ
  ダウンロードも停止。詳細は `docs/OPERATIONS.md`「6. トラブルシューティング」参照。
- STG デプロイの troubleshooting 性を改善。詳細は `docs/OPERATIONS.md`「6. トラブルシューティング」参照。
  - `web` の healthcheck が公開ドメイン用の `API_BASE_URL` に対して名前解決していたため、
    NAS 環境で DNS 解決できず `socket.gaierror` で失敗し続けていた問題を修正
    （常にコンテナ内部の `127.0.0.1:5000/health/live` を見るように変更）。
  - gunicorn 25+ のデフォルト制御ソケット作成で毎起動時に出ていた
    `[ERROR] Control server error: Permission denied: '/.gunicorn'` を
    `--no-control-socket` を付与して解消。
  - `docker-compose.yml` の `db`/`redis` healthcheck が `${VAR}` 展開により
    `docker events` へパスワード平文を記録していた問題を `$$VAR` エスケープで修正。
  - `scripts/deploy-stg.sh`: `docker load` が無応答に見える問題に対し、`pv` があれば
    進捗バー、なければ経過秒数のハートビートを表示するように変更。ヘルスチェック失敗時に
    `docker compose ps` / 直近ログ / healthcheck 履歴を自動出力するよう強化。
- コンテナ起動失敗 `exec /script/entrypoint.sh failed: No such file or directory` を修正。
  起動方法をイメージに焼き込み（Dockerfile に `ENTRYPOINT ["/app/scripts/entrypoint.sh"]` /
  `CMD ["web"]`）、compose の `entrypoint:` 絶対パス上書きを撤去。compose は `command`
  （web / worker / beat）でモードのみ指定する。デプロイ先の compose コピー同期漏れに対する
  耐性を高めた（`scripts/README.md` に同期手順を明記）。
- CI で `pytest`（`python -m` なし）実行時に `conftest.py` の `import shared` が
  `ModuleNotFoundError` になる問題を修正（pyproject に `pythonpath = [".", "cli/src"]` を追加）。

### Changed
- 重複判定を単一実装に統合し、旧実装へのサイレントフォールバックを廃止。想定外の例外は
  伝播させ、不正ハッシュ時のみ明示的に「重複なし」で継続する。詳細は ADR-0004。
- マイグレーション履歴を単一ベースライン `migrations/versions/init_master.py` に統合
  （旧リビジョン 33 本を削除）。詳細は ADR-0001。
- DB ネイティブ ENUM を廃止し全モデルの `Enum(...)` を `native_enum=False` 化。詳細は ADR-0002。
- `scripts/seed_master_data.py` をカタログ参照に統一（値の二重管理を排除）。
- 初期管理者パスワードを `ADMIN_INITIAL_PASSWORD` で上書き可能化。
