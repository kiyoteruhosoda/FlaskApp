# CHANGELOG

完了した重要な変更を記録する（運用ルール: 完了項目は Progress.md から本ファイルへ移す）。
新しいものを上に追記する。書式は概ね Keep a Changelog 準拠。

## [Unreleased]

### Added
- `scripts/deploy.sh` / `scripts/deploy-stg.sh` に `migrate` モードを追加。
  引数だけで「アプリのみ更新（`deploy`）」「DDL更新（`migrate`＝`flask db upgrade`を
  自動実行、既存データ保持）」「完全初期化（`reset`）」を切り替えられるようにした。
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
