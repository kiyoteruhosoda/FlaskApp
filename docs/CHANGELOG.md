# CHANGELOG

完了した重要な変更を記録する（運用ルール: 完了項目は Progress.md から本ファイルへ移す）。
新しいものを上に追記する。書式は概ね Keep a Changelog 準拠。

## [Unreleased]

### Added
- **Photo Imports 機能を新設**（Photo Settings から Local Import Status を分離）。
  新ページ `/photo-imports`（`PhotoImportsPage.tsx`、Sidebar に `fa-file-import`
  アイコンで追加、権限 `admin:photo-settings`）でインポート状態の確認・取り込み実行
  （`system:manage` 保有時のみ表示）に加え、**Import Directory へのファイル手動
  アップロード**ができるようになった。バックエンドに
  `POST /api/sync/local-import/upload`（multipart、`admin:photo-settings` 必須）を追加。
  拡張子は `SUPPORTED_EXTENSIONS`（domain/local_import/policies.py）で検証し、
  同名ファイルは上書きせず連番を付与する。Photo Settings はディレクトリ状態の
  確認のみに整理。
- 画面フッタにアプリバージョンを常時表示（`Footer.tsx`、`GET /api/version` を参照）。
- Role Management にデフォルトロール（master_data.py の admin/manager/member/guest）を
  `isDefault: true` 付きで表示。デフォルトロールは UI で編集・削除ボタンを出さず、
  API 側でも `PUT`/`DELETE /api/admin/roles/<id>` が `default_role_immutable`(403) を
  返すようガードした。

### Fixed
- **パスキー登録が常に「Failed to register passkey」で失敗する不具合を修正。**
  フロントは `GET /api/auth/passkey/options/register` / `POST /api/auth/passkey/verify/register`
  を呼んでいたが、バックエンドには auth ブループリント側の
  `POST /auth/passkey/options/register`（Flask-Login セッション必須）しか存在せず
  404 になっていた。JWT 認証（`login_or_jwt_required`）対応の登録エンドポイントを
  `/api` 側（`api/auth_passkeys.py`）に追加して解消。チャレンジは従来同様
  Flask セッションに保持する。
- ログインの二段階認証（TOTP）要求時に、内部エラーコード `totp_required` が
  赤い dismissible アラートでそのまま表示されていた問題を修正。エラーではなく
  通常の案内（info アラート「認証コードを入力してログインを完了してください」）に
  変更し、`invalid_totp` / `invalid_credentials` も利用者向け文言に変換して表示する
  ようにした。

### Changed
- ログイン/登録画面のデザイン調整: カードの枠・影を外して背景と一体化し、
  Navbar ブランドと重複する「PhotoNest」タイトルを削除。英日切替を
  カードヘッダ右上（視認性の悪い outline ボタン）から card-footer の
  リンク型ドロップダウンへ移動。
- Sidebar の Dashboard アイコンを `fa-gauge-high` から `fa-bars-progress` に変更。
- Celery worker 起動直後、最初に実行されたタスク（`picker_import.watchdog` の
  `list_importing()` クエリなど）が SQLAlchemy 内部の `NotImplementedError`
  で失敗することがある不具合を修正。原因は `cli/src/celery/celery_app.py` の
  `create_app()` が import 時点（＝Celery マスタープロセス内、`--pool=prefork`
  が子プロセスを fork する前）に `_apply_persisted_settings()` 経由で実際に
  DB へ接続してしまっていたこと。fork 後の子プロセスは親が開いた DB
  コネクション（ソケット）をそのまま引き継ぐため、複数プロセスが同じ
  コネクションを使うと MySQL プロトコルのやり取りが混線し、ORM 内部で
  説明のつかないエラーとして表面化していた。`worker_process_init` シグナルで
  `db.engine.dispose()` を呼ぶだけでは不十分だった（fork 直前に Python レベルでは
  同じ `Engine` オブジェクト・コネクションプールの内部ロック状態までコピーされて
  しまうため、fork 後に破棄しても "Command Out of Sync" / "Lost connection to
  MySQL server during query" という形で症状が残った）。根本対策として、fork が
  発生するより前、モジュール import 時点（Celery マスタープロセス内）で
  `create_app()` 実行直後に `db.engine.dispose()` を呼び、マスタープロセスが
  DB コネクションを保持したまま fork されること自体をなくした。
  `worker_process_init` 側の dispose は多重防御として残している。
- 新規作成ユーザーがログインできない不具合を修正。`admin_users.py` のユーザー作成/更新
  API がメールアドレスの形式を検証していなかったため、非メール形式の値が登録でき、
  ログイン時に `LoginRequestSchema`（`fields.Email`）で弾かれていた。加えて、その
  バリデーションエラーを処理する `error_handlers.py` の 422 ハンドラが webargs の
  `e.data` をそのまま返していたため、シリアライズ不可能な Schema インスタンスを含み
  `TypeError` で 500 になる二次バグもあった（`e.data["messages"]` のみを返すよう修正）。
- `/admin/groups`・`/admin/roles`・`/admin/config` に遷移できない不具合を修正。旧
  Jinja UI 時代の Flask ルートが React SPA と同じパスを持ったまま「自分自身へ
  redirect」する死んだコードとして残っており、無限リダイレクトになっていた
  （`admin/routes.py`）。SPA シェルを返すよう修正し、あわせて `Sidebar.tsx`/`Header.tsx`
  のリンクを `<a href>` から `react-router-dom` の `Link` に置き換えてクライアント
  サイド遷移にした。また `/admin/groups` の権限チェックが `group:manage`
  （どのロールにも付与され得ない存在しない権限コード）を要求していたため常に権限
  エラーになっていたバグも修正し、React SPA/JSON API と同じ `user:manage` に統一。
- `admin/users` ページで日本語表示時に検索ボックスと「検索」ボタンが縦に折り返される
  不具合を修正（`flex-nowrap` を付与）。
- 同期ジョブ履歴 (`JobSync`) に `session_recovery.cleanup_stale_sessions`・
  `picker_import.watchdog` の no-op 実行（対象0件）まで記録され、履歴が埋もれていた
  問題を修正。Celery タスクの共通実行基盤 (`cli/src/celery/celery_app.py` の
  `ContextTask`) に no-op 判定を追加し、実際に処理が発生した場合のみ履歴を残すように
  した。
- ログイン画面の「パスキーでログイン」ボタンが絵文字 (🔐) だったのを FontAwesome の
  鍵アイコンに変更。
- `worker`/`beat` コンテナの healthcheck（`docker-compose.yml`）が
  `ps aux | grep -q ...` を使っているが、ベースイメージ `python:3.11-slim` には
  `ps` コマンド（procps パッケージ）が含まれておらず、実行のたびに
  `/bin/sh: ps: not found` で healthcheck が失敗していた。このエラーは
  healthcheck プローブ自身の STDIO（`docker inspect` の `State.Health.Log`）に
  記録され `docker compose logs` には出ないため気づきにくく、タスク自体は正常に
  実行され続けていた。`Dockerfile` の apt-get install に `procps` を追加して修正。
- `docs/OPERATIONS.md`「3. デプロイ」「5. ログ監視」のログ確認コマンド例を修正。
  `docker compose logs <サービス名>` は `docker-compose.yml`/`.env` があるディレクトリ
  （`/volume1/docker/photonest` 等）で実行する必要があるが、その前提が書かれておらず
  `/volume1/docker` 直下で実行すると `Failed to load /volume1/docker/.env` で失敗して
  いた。また引数はサービス名（`web`/`worker`等）であってコンテナ名
  （`photonest-web-1`等）ではないため、「コンテナ構成」の表記もサービス名に修正した。

### Added
- フロントエンドのアイコンを Bootstrap Icons から FontAwesome
  （`@fortawesome/fontawesome-free`）に統一。`bootstrap-icons` 依存を削除。
- ログイン前でも `?lang=` クエリパラメータ / `lang` Cookie で日英を切り替え可能に
  した（既定は英語）。`select_locale()`（Flask-Babel）にクエリパラメータ対応を追加し、
  フロントエンドの `i18n/config.ts` もハードコードされていた `lng: 'ja'` を廃止して
  同じ `lang` Cookie/クエリを見るようにした。プロフィール画面にも言語切り替え UI を
  追加。
- Sidebar の Media メニューを表示系（メディアギャラリー・アルバム・タグ・重複）と
  管理系（セッション・同期ジョブ・写真設定）に並び替え。
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
