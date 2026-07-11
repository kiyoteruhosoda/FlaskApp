# CHANGELOG

完了した重要な変更を記録する（運用ルール: 完了項目は Progress.md から本ファイルへ移す）。
新しいものを上に追記する。書式は概ね Keep a Changelog 準拠。

## [Unreleased]

### Added
- **T11: FastAPI 全面移行 Phase 3 後続作業完了（Flask 完全撤廃）**。
  `presentation/fastapi/` に全サービス・認証・管理機能を移植し、Flask への依存を完全に除去。
  - `presentation/fastapi/config.py`（Flask-free `BaseApplicationSettings`）
  - `presentation/fastapi/services/`（`token_service`, `access_token_signing`,
    `system_setting_service`, `service_account_api_key_service`, `service_account_service`,
    `password_reset_service`, `upload_service`, `storage_helpers`, `admin_config_service`）
  - `presentation/fastapi/auth/`（`totp`, `utils`, `api_key_auth`, `service_account_auth`, `passkeys`）
  - `presentation/fastapi/admin/system_settings_definitions.py`
  - `cli/src/celery/celery_app.py` から Flask アプリコンテキストを削除（純粋な Celery + SQLAlchemy）
  - `scripts/`, `tests/conftest.py`, `tests/config.py` の Flask 依存を除去
  - テスト更新: Flask TestClient → FastAPI TestClient（`test_health_api.py`, `test_version_api.py`）
  - テスト更新: Flask アプリコンテキスト → SQLAlchemy 直接使用（`test_migration_model_consistency.py`,
    `tests/wiki/conftest.py`, `test_celery_app.py`, `test_celery_context.py`, `test_logging.py`）
  - CI ワークフロー更新: `pip install Flask-Migrate` を削除（不要になった）
  - `pyproject.toml` に `norecursedirs = ["tests/manual"]` を追加


  `group_roles` 中間テーブルを追加し、グループにロールを付与できるようにした。
  所属ユーザーの `permissions` / `all_permissions` へグループ経由のロール権限が波及する。
  API: `GET /api/admin/groups/<id>/roles`・`PUT /api/admin/groups/<id>/roles`。
  マイグレーション: `7b4e3f1a9c2d_add_group_roles.py`。
- **アルバムスライドショー: 次の画像が用意できるまで現在画像を保持**（`SlideshowPage.tsx`）。
  署名済み URL のキャッシュ（`urlCacheRef`）と `new Image()` によるプリロードを実装。
  画像切替時は次の画像がブラウザにロードされてから `thumbUrl` を更新するため、
  切替中も前の画像を表示し続ける。ロード中はオーバーレイスピナーで待機を示す。
  次（+1）の画像はバックグラウンドで先読みする。

### Removed
- **DB焼き込みベースライン（`db/init/01_initialize.sql`）と再生成スクリプトを廃止**。
  マイグレーションが `init_master` + `seed_master_data` の2本に集約され、web コンテナの
  entrypoint が起動時に必ず `alembic upgrade head` を実行する現構成では、DBイメージへの
  スキーマ焼き込みは起動時マイグレーションと内容が二重で、モデルとの乖離リスクと保守コスト
  だけが残っていた。加えて `regenerate_db_baseline.sh` は Flask 撤廃で `flask db upgrade` が
  使えず既に壊れていた（`.venv` 有効化時に「flask コマンドが見つかりません」エラー）。
  - 削除: `db/init/01_initialize.sql`, `scripts/regenerate_db_baseline.sh`,
    `tests/integration/test_db_baseline_consistency.py`, Makefile の `regen-db-baseline` ターゲット
  - `db/Dockerfile`: 初期SQLの `COPY` を廃し、TZ を UTC に固定しただけの素の MariaDB イメージに
  - `deploy.sh` / `deploy-stg.sh`: `reset` モードを `alembic stamp head`（焼き込み前提）から
    `alembic upgrade head`（空DBにスキーマ+マスタデータを構築）へ変更
  - DDL変更時は migration を追加するだけでよく、ベースライン再生成・DBイメージ再ビルドは不要。
    ドキュメント（`docs/OPERATIONS.md`, `scripts/README.md`）も更新。

### Changed
- **T4: `bounded_contexts/email` を `email_sender` に統合**。
  `bounded_contexts/email` を削除し、すべての機能（`send_email`・`send_password_reset_email`・
  `validate_sender_config` 等）を `bounded_contexts/email_sender/application/email_service.py`
  に一本化。`presentation/web/services/password_reset_service.py` および各テストファイルの
  import パスを `bounded_contexts.email_sender` に変更。

### Added
- **T3: 初回ログイン時パスワード強制変更フロー実装**。
  `user.must_change_password` カラム（`migrations/versions/6a3f7d2e1b4c_add_user_must_change_password.py`）、
  ログイン API の `requires_password_change` レスポンスフラグ、
  `/api/auth/password/force-change` エンドポイント、
  フロントエンドの `/change-password` ページを追加。
  `REQUIRE_PASSWORD_CHANGE_ON_FIRST_LOGIN` 設定フラグが OFF（既定）のときは動作しない。
- **T5: Photo Exports ページ実装**（`/admin/photo-exports`）。
  インポート日でフィルタして元ファイルを ZIP でダウンロードする機能を実装。
  バックエンド: `/api/admin/photo-exports/preview`（件数・サイズプレビュー）と
  `/api/admin/photo-exports/download`（ZIP ストリーミング配信）を追加。
- **T7: グループへのユーザー紐づけ UI 実装**（`/admin/groups`）。
  グループ一覧の「メンバー管理」ボタンからモーダルを開き、
  ユーザーを検索・選択してグループへ所属させられるようにした。
  バックエンドの `PUT /api/admin/groups/<id>` (`memberIds`) は既存。

### Changed
- **サムネイル一覧の取得を直列から並列に変更**（`frontend/src/pages/MediaPage.tsx` /
  `frontend/src/pages/AlbumDetailPage.tsx` / `frontend/src/pages/AlbumsPage.tsx` /
  `frontend/src/components/MediaPickerModal.tsx`）。署名付きサムネイル URL を取得する
  `useEffect` は `for...await` で 1 件ずつ順番に `getPhotoThumbUrl()` を呼んでいたため、
  ディスクキャッシュにヒットしていても枚数分の HTTP 往復が直列に積み上がり表示が遅れていた。
  `Promise.all` による並列取得に変更し、全件解決後に 1 回だけ state を更新するようにした。
  あわせて依存配列から `thumbs`／`covers` を外し、URL が 1 件解決するたびに `useEffect` が
  再実行される問題を解消した。
- **メディア署名 URL をキャッシュ可能に変更**（`presentation/web/api/routes.py`）。
  サムネイル・オリジナル・再生用（`api_media_thumb_url` / `api_media_original_url` /
  `api_media_playback_url`）の署名 URL は従来、毎回 `nonce`（UUID）と秒単位の `exp` を
  含めていたため、同一メディアでもリクエストごとに `/api/dl/<token>` が変わり（アルバム
  表紙とメディア一覧で別 URL になる等）ブラウザ／CDN のキャッシュが効かなかった。共通
  ヘルパー `_cacheable_signed_exp()` を追加し、`exp` を TTL 幅のウィンドウ境界に丸めて
  `nonce` を除くことで署名を決定的にし、同一ウィンドウ内の繰り返し要求が同一 URL を返して
  キャッシュヒットするようにした（3 エンドポイント一律）。`cacheControl` の `max-age` は
  残存有効時間に合わせて返す。
- **新規生成サムネイルの画像フォーマットを AVIF に変更**（既存サムネイルは据え置き）。
  サムネイル生成（`bounded_contexts/photonest/tasks/thumbs_generate.py`）の出力拡張子を
  `.avif` に変更し、`shared/kernel/utils.register_avif_support()`（`pillow-heif` の
  `register_avif_opener`＋`image/avif` の MIME 登録）で読み書きを有効化。透過は AVIF が
  そのまま保持するため PNG 分岐は廃止。拡張子はメディアごとに `thumbnail_rel_path` に
  記録されるため、既存の `.jpg`/`.png` サムネイルはそのまま配信され、再生成された分のみ
  AVIF になる。配信側（`presentation/web/api/routes.py`）は候補パスに `.avif` を追加。

### Added
- **nginx を docker-compose に追加し、X-Accel-Redirect を既定で有効化**
  （`docker-compose.yml` / `docker/nginx/default.conf`）。`nginx` コンテナが公開ポート
  （`WEB_HOST_PORT`）を受け持ち、`web`(gunicorn) は内部専用にした。メディア（サムネイル・
  オリジナル・動画）は nginx が `X-Accel-Redirect` でディスクから直接配信する
  （`MEDIA_ACCEL_REDIRECT_ENABLED=true` を compose 既定に）。`internal` ロケーションのため
  外部から `/media/*` へ直アクセスは 404 で、署名を通った内部リダイレクト時のみ配信される。
  alias 先・accel ロケーションは settings 既定（`/media/*` → `/app/data/media/*`）と一致。
  CDN 利用時のオリジンはこの nginx を指す。
- **CloudFlare CDN バックエンドを実 API 実装に置き換え**
  （`bounded_contexts/storage/infrastructure/cloudflare_cdn.py`）。従来 `purge_cache` 等は
  HTTP 呼び出しを省略した擬似実装（固定 UUID・固定アナリティクス）だった。CloudFlare API
  v4 を `requests` で実際に呼ぶよう実装: キャッシュパージ（`/zones/{zone}/purge_cache`、
  url/prefix/tag/all）、ゾーン設定更新（`browser_cache_ttl` / `brotli` の PATCH）、
  キャッシュ状態取得（対象 URL への HEAD で `CF-Cache-Status` ヘッダーを読む）、
  アナリティクス（GraphQL の `httpRequestsAdaptiveGroups`）、プリフェッチ（対象 URL への
  実 GET でエッジを温める）。認証は API トークン（Bearer）、失敗は `StorageException` に変換。
- **画像・メディア配信方式のドキュメントを整備**（`docs/OPERATIONS.md`「4. 機能設定ガイド」）。
  Flask 直返し（既定）／Nginx 直接（`X-Accel-Redirect`）／CDN の 3 方式と、それぞれに必要な
  設定・データ整備を一覧化。既存の CDN 節・nginx 節と統合し重複を避けた。
- **取り込みのベル通知を「開始／終了の 2 段階」通知に変更**
  （`frontend/src/components/ImportActivityBell.tsx`）。従来はバッジが「進行中セッション数」
  だったため取り込み完了と同時に消え、終わったことを見逃していた。セッションごとの
  フェーズ（`active`/`done`）を `localStorage` に保存し、フェーズが変化＝未読としてバッジを
  立て、ベルを開いて中身を見るまで消えないようにした。

### Changed
- **マイグレーションを単一ベースライン（`init_master`）へ統合（全データリセット前提）**。
  断片化した増分マイグレーション8本（`3b7c2e9a1f08` 〜 `9d6e4a2b0f5c`、および
  ブランチ上の補正 `a1b2c3d4e5f6`）を削除し、`init_master` を現行モデルから再生成して
  全テーブル（`must_change_password` を含む）を一括作成するようにした。マスタデータ投入
  `2a1f9c0b3d4e_seed_master_data` は据え置きで新ヘッド。焼き込みベースライン
  `db/init/01_initialize.sql` もモデルから再生成し、`alembic_version` を新ヘッド
  `2a1f9c0b3d4e` に更新（旧来はヘッドの手書きSQLがモデルと乖離し、`user.must_change_password`
  欠落のまま stamp していたためログインが `Unknown column` で 500 になっていた）。
  - リセット手順: 旧DBボリュームを破棄し、再ビルドしたDBイメージ（`make build-db`）で
    起動する。`db/init/01_initialize.sql` がスキーマ + マスタデータ（ロール/権限/初期管理者）
    を投入し、web の `alembic upgrade head` は no-op になる。

### Fixed
- **`JWT_SECRET_KEY` 環境変数が未設定の環境でログインが 500 になる問題を修正**。
  組み込み(HS256)署名の秘密鍵は `settings.jwt_secret_key` で解決していたが、この
  `@property` は環境変数のみを参照するため、管理画面から `system_settings` の
  `app.config` に保存された値（および `DEFAULT_APPLICATION_SETTINGS` の既定値
  `default-jwt-secret`）を拾えなかった。環境変数を持たないステージングでは
  `resolve_signing_material()` が `AccessTokenSigningError("JWT secret key is not
  configured.")` を送出し、`POST /api/auth/login` が 500 になっていた。
  併せて、秘密鍵の解決ロジックが署名(`access_token_signing`)・検証・管理画面表示
  (`admin_config_service`, env を無視して DB のみ参照していた)の 3 箇所に分裂していた
  ため、`SystemSettingService.resolve_builtin_jwt_secret()` に一本化した。優先順位は
  設計方針どおり「環境変数 > DB(`app.config`) > デフォルト値」で、全経路がこのメソッドを
  唯一の出所とする。
- **nginx 設定がデプロイ時に host へ配布されず nginx が起動しない問題を修正**
  （`scripts/deploy.sh` / `scripts/deploy-stg.sh`）。compose の nginx サービスは設定を
  `./docker/nginx/default.conf` という相対パスでバインドマウントするが、この相対パスは
  compose ファイルと同じディレクトリ（NAS 上の `photonest-stg/` 等）を基準に解決される。
  デプロイスクリプトの `sync_assets_from_image` はイメージから `docker-compose.yml` と
  スクリプト自身だけを取り出しており、nginx 設定は host に配置されないため、起動時に
  `Bind mount failed: '.../docker/nginx/default.conf' does not exist` で nginx コンテナが
  落ちていた。compose と同じ「イメージを唯一の出所とする」方針に合わせ、両デプロイ
  スクリプトがイメージ内 `/app/docker/nginx/default.conf` を `$BASE_DIR/docker/nginx/`
  へ同期するようにした。回帰は `tests/integration/test_deploy_asset_sync_consistency.py`
  が検出する。
- **Google フォト取り込みのサーバーエラーがセッションログに残らない問題を修正**
  （`presentation/web/api/picker_session.py`）。取り込み開始／メディアアイテム取得の
  リクエストで発生した 500 系エラーは Flask 既定の 500 ハンドラが `Log` テーブルへ
  `api.server_error` として記録するが、`session_id` を持たずセッション詳細画面のログ
  （`WorkerLog` の `import.%` を `session_id` で照合）には現れず「ログに出ない」状態だった。
  これらのエンドポイントで例外・enqueue 失敗を捕捉し、`session_id` を含む
  `import.picker.*` イベントとして `WorkerLog` に記録するようにした。
- **アルバム詳細でサムネイル読込前に「表紙に設定」ボタンの表示が崩れる問題を修正**
  （`frontend/src/pages/AlbumDetailPage.tsx`）。`.ratio` 直下の要素として配置されたボタンが
  画像未読込時に崩れて見えるため、サムネイル読込完了までボタンを表示しないようにした。
- **スライドショーに全画面表示を追加**（`frontend/src/pages/SlideshowPage.tsx`）。
  ダブルクリック／右下の最大化アイコン／`F` キーで全画面を切り替え、全画面中は左上の
  アルバム名などのオーバーレイを非表示にした。

- **デプロイ後にセッション失効しても強制ログアウトされない問題を改善**。SPA を開いたまま
  サーバー再起動されると、画面に残った署名付き URL の画像（`<img>`）読み込みは axios を
  経由せず 401 を検知できないため、`forceLogout` が働かず画像だけが壊れて表示され続けていた。
  タブが前面に戻った時（`visibilitychange`/`focus`）に認証付きリクエストを1回投げて失効を
  検知し、既存のレスポンスインターセプター（リフレッシュ失敗→`forceLogout`）でログイン画面へ
  誘導するようにした（`frontend/src/App.tsx`）。
- **メディア一覧サムネイルを 200px 固定サイズに変更**。`/media`
  （`frontend/src/pages/MediaPage.tsx`）のレスポンシブ列（`Row xs=3 … xl=10`）を
  200px 固定幅タイルの flex-wrap レイアウトに変更し、広い画面でタイルが拡大しすぎる問題を解消。
- **ログアウト時の Welcome 画面ちらつきを解消**。ヘッダーの
  `handleLogout`（`frontend/src/components/Header.tsx`）が `logout()` 完了を待たずに
  `/login` へ遷移していたため、認証状態が true のまま `"/"`（Welcome）へ弾かれてから
  ログイン画面に変わっていた。`await dispatch(logout())` 後に `navigate('/login', {replace:true})`
  するよう修正。
- **右上ユーザー表示のちらつきを解消**。ヘッダーが `user?.username || 'User'` を表示するため
  `getCurrentUser` 解決前に固定文字列 "User" が出ていた。ロード中はフォールバック文言を出さず
  ユーザーアイコンを表示するよう変更（`frontend/src/components/Header.tsx`）。

### Added
- **Google フォト取り込みのステータス表示と自動取り込みを追加**。
  ①Photo Imports 画面の Google Photos セクションに Local Import と同様の
  「Import Status」カードを追加（直近セッションの進行状況・件数・詳細リンク、
  進行中は自動更新）。②ヘッダーに通知ベルを追加し、実行中/直近の取り込み作業
  （Google フォト・ローカル）の一覧と詳細へのリンク、実行中件数バッジを表示。
  ③セッションのステータスを「写真の選択待ち」「取り込み中」「完了」等の
  分かりやすいラベルで表示（Sessions 一覧・詳細も統一）。
- **セッション作成のきっかけ（誰の操作か／自動か）をセッション自体に記録**。
  `picker_session` に `trigger`（`user`=人の操作 / `worker`=自動処理、既存行は
  `unknown`。語彙は `job_sync.trigger` と統一）と `triggered_by_user_id`
  （`user.id` への FK、自動起動時は NULL）を追加
  （マイグレーション `5f2b8d4c7e10`、ベースライン `db/init/01_initialize.sql` も更新）。
  記録箇所: ローカルインポート手動実行 API・Google Photos Picker セッション作成
  （API/Web）が `user`、セッションID無しで走った取り込みのワーカー自動作成が
  `worker`。セッション一覧 API と状態 API のレスポンスに `trigger` /
  `triggeredByUserId` を追加
  （`tests/unit/application/picker_import/test_picker_session_trigger.py` で検証）。

### Fixed
- **アルバム・取り込み周りの UI 不具合をまとめて修正**。
  ①ヘッダー通知ベルの件数バッジがベルアイコンからずれて表示されていたのを修正
  （バッジの位置基準をアイコン自身に変更）。②取り込みステータスのバッジで
  `light` variant が既定の白文字となり「白地に白」で読めなかったのを修正
  （`light`/`warning`/`info` 背景には濃色文字を指定する `badgeTextColor` を追加し、
  セッション詳細・選択エラー・ジョブ画面のステータスバッジに適用）。
  ③アルバム・メディア一覧のサムネイルが解像度に対して大きすぎたため、
  グリッドの列数を増やして縮小。④アルバムへのメディア追加モーダルで選択時の
  チェックアイコンの白背景（`bg-white`）がアイコンとずれていたのを修正
  （固定サイズの白丸の上にアイコンを重ねる構造に変更）。⑤アルバムの
  スライドショーがサムネイル要求で 400 を返し表示されなかったのを修正
  （許可外の `size=1920` を許可値 `2048` に変更）。
- **Google フォトで選択した写真が取り込まれない問題を修正**。Picker で選択を
  終えても取り込みを開始する処理がどこからも呼ばれておらず、セッションが
  永遠に pending のままだった。Celery beat の定期タスク
  `picker_session.advance`（1分間隔）を追加し、サーバー側で Google を
  ポーリングして選択完了を検知→mediaItems 取得→取り込みキュー投入まで自動で
  行うようにした（ブラウザを閉じても取り込みが完了する）。フロントエンドも
  進行中セッションをポーリングし、選択完了を検知したら即時取り込みを開始する。
  期限切れ（未選択のまま放置）のセッションは expired へ自動遷移する。
- **STG デプロイ `reset` で `container mariadb-stg is unhealthy` になり DB が
  起動しない問題を修正**。初回起動（空 `db_data`）はシステムテーブル初期化→
  一時サーバー→ベースライン SQL 投入を経るが、Synology NAS の遅いディスクでは
  初期化だけで healthcheck の `start_period: 180s` を超え、TCP ping が通る前に
  unhealthy 判定されていた（一時サーバーはソケットのみのため ping 失敗は正常）。
  `start_period` を 600s、`retries` を 30 に拡大（probe は成功すれば即 healthy に
  なるため、2回目以降の通常起動は遅くならない）。

### Changed
- **ヘッダーの右側トグルをケバブ（縦三点）アイコンに変更**。左のサイドバー開閉
  （ハンバーガー）と右のメニュー開閉が同じアイコンで紛らわしかったため、
  折りたたみメニュー側を `fa-ellipsis-vertical` に変更して役割を区別した。
- **System Settings に「デフォルト値と異なる設定のみ表示」フィルタを追加**。
  初期構築時に何を設定済みか（ENV / DB で上書きされているか）を一覧確認できる。
  また、環境変数で上書きされている設定は実際に効いている ENV の値を読み取り専用
  で表示するようにした（シークレットは目アイコンで表示切替）。
- **未ログイン画面（Create an account / ロール選択）の背景を白に統一**。
- **Photo Imports 画面を Local / Google Photos で視覚的に区分**。
  「Upload Files」「Import Status」「Trigger Import」はローカル取り込みの
  機能であることが分かるよう、Google フォト取り込みカードと別に
  「GOOGLE PHOTOS」「LOCAL IMPORT」のセクション見出しを追加。
  Upload Files はドラッグ＆ドロップに対応し、選択したファイルは即アップロード
  せず「準備中ファイル」として一覧表示（ファイル名・サイズ）。アップロード実行
  （Step 2）前に複数回に分けて追加選択・個別取り消し・全解除ができるように
  フローを「準備 → アップロード実行」の2段階に分離した。

### Fixed
- **Google フォト取り込みが 502 で失敗する問題を修正**。Picker セッション作成時に
  Google Picker API（`POST /v1/sessions`）へ `title` フィールドを送信していたが、
  Session リソースに存在しないフィールドのため Google が
  400 INVALID_ARGUMENT（Cannot find field）を返し、アプリは 502 を返していた。
  リクエストボディを空にし、API・フロントエンドからも `title` パラメータを撤去。
- **Google 連携で他ユーザーのアカウントを奪う問題を修正**。OAuth コールバックの
  アカウント検索が `email` だけで引いていたため、同じ Google メールを別ユーザーが
  連携すると既存ユーザーの行の `user_id` が上書きされていた（`GoogleAccount` の
  一意制約は `(user_id, email)`）。連携先ユーザーの行を優先し、無ければ未紐付け
  （`user_id=None`）の行のみを引き取るよう修正
  （`tests/webapp/auth/test_google_oauth_callback.py` で回帰検証）。
- **Google フォト取り込みのクロスデバイス保存とストレージ孤児を修正**。
  ①セッション再生側の取り込み（`picker_import`）が `os.replace` 直呼びで、tmp と
  originals が別ファイルシステムだと `EXDEV` で失敗していた。per-item 側と同じ
  コピー→fsync→replace 退避を共通ヘルパー `_atomic_move_into_place` に集約して
  両経路で使用。②配信バイト変化（sha256 変化）による再取り込みで `local_rel_path`
  が変わると旧オリジナルファイルがディスクに取り残されていたため、DB コミット
  成功後に旧ファイルを削除するよう修正
  （`tests/unit/application/picker_import/test_picker_import_item.py` で回帰検証）。
- **環境変数で設定した値が無視される問題を修正**（`.env` に `ENCRYPTION_KEY`
  を設定しても「Encryption key not configured」が続く障害の根本原因）。
  `apply_persisted_settings` が「デフォルト + DB」の全キーを `app.config` へ
  書き込むため、環境変数の値がデフォルト（None 等）に潰されて設定解決が
  環境変数まで到達しなかった。文書化された優先順位「環境変数 > DB > デフォルト」
  どおり、環境変数が定義されたキーは env 値（デフォルトの型に合わせて
  bool/int/float/list へ変換）を採用するよう修正
  （`tests/webapp/test_settings_env_priority.py` で回帰検証）。
- **セッション失効時にログイン画面へ遷移しない問題を修正**。401 応答時の
  トークンリフレッシュが「例外ではなく失敗レスポンス」で返るパスに
  後続処理が無く、画面が止まったままだった。リフレッシュ失敗時は
  トークンを破棄して `/login` へ遷移する（多重リダイレクト防止付き）。

### Added
- **System Settings の各項目に実効値の取得元バッジ（ENV / DB / デフォルト）を
  表示**。環境変数で上書きされている項目には「ここで保存した変更は環境変数を
  外すまで反映されない」旨の注意を表示し、「.env に設定したのに反映されない」
  を画面上で診断できるようにした。
- **ENCRYPTION_KEY 未設定時に Google アカウント連携が 500 になる問題を修正**。
  トークン保存時の暗号化で `RuntimeError` が発生し、Google の同意画面を
  通過した後にサーバー内部エラーになっていた。①OAuth 開始 API で事前チェックし
  `encryption_key_not_configured`(400) と設定手順を返す（同意画面へ進む前に
  分かる）、②コールバックでも暗号化失敗を捕捉し `reason=encryption_key_missing`
  で画面へ戻す、③ENCRYPTION_KEY の default_hint が「preconfigured」と実態
  （デフォルトなし）に反していたのを生成コマンド付きの正しい説明に修正、
  ④OPERATIONS.md の .env 例に `ENCRYPTION_KEY` を追記。
- **設定更新が一部のリクエストで反映されない問題（OAuth の client_id が空になる等）
  を修正**。DB 保存設定（system_settings）は起動時と「更新リクエストを処理した
  ワーカー」の `app.config` にしか反映されず、Gunicorn の他ワーカーは再起動まで
  古い値を使い続けていた。リクエストごと（最大10秒間隔の軽量クエリ）に
  `system_settings.updated_at` を確認し、更新されていれば再適用する
  `refresh_persisted_settings_if_stale` を追加（`bootstrap/persisted_settings.py`）。
- **admin で権限管理・サービスアカウント管理に到達できない問題を修正**。
  権限 CRUD API のゲートを `admin:system-settings` → `permission:manage`、
  サービスアカウント管理を → `service_account:manage` に変更（ユビキタス言語の
  scope に統一）。これによりロール編集モーダルの権限チェックボックス
  （ロール⇔権限の紐づけ）と Permissions 画面（権限の作成・編集・削除）が
  admin で利用可能になった。
- **DB ベースライン（`db/init/01_initialize.sql`）と権限マスタの乖離を解消**。
  ベースラインに `admin:system-settings` が無く（`stamp head` 運用では同期
  マイグレーションも実行されないため）付与されなかった。ベースラインに権限と
  admin への付与を追加し、ベースライン側にのみ存在した `group:manage` を
  `master_data.py` の `PERMISSION_CODES` にも追加して整合させた。
- **OAuth トークン交換のログ改善**: トークンレスポンス全体（アクセストークン・
  リフレッシュトークンを含む）を INFO で出力していたのをやめ、成功時はキー名
  のみ、エラー時は ERROR レベルで記録。外向き HTTP ログ（http_logging）の
  マスク対象に `code`（認可コード）・`client_secret`・`password` を追加。
- **API リクエスト/レスポンスログに発生源を明記**。`{"method": "GET"}` のような
  発生源不明のログにならないよう、入出力ログのメッセージ本体に
  method / path / status / requestId を常に含めるようにした。

### Changed
- **`GOOGLE_OAUTH_REDIRECT_URI` 設定を `GOOGLE_OAUTH_REDIRECT_ORIGIN` に変更**
  （ラベル: Google OAuth redirect scheme and host）。設定値はスキーム・ホストのみ
  （例 `https://photos.example.com`）で、固定パス `/auth/google/callback` は
  自動付与される。管理画面の入力欄にも固定パスをサフィックス表示
  （`input_suffix`）。旧キー（フル URL）も後方互換で受け付ける。

### Added
- **プロフィールに「Google アカウント連携」セクションを追加**
  （`GoogleAccountLinkSection.tsx`）。自分のアカウントの登録（OAuth リンク）・
  一覧・連携解除ができる。バックエンド `GET /api/google/accounts` に
  `?mine=1`（自分に紐づくアカウントのみ返す）を追加。
- **Photo Imports に「Google フォトから取り込み」カードを追加**。共通モーダル
  `GooglePhotosImportModal.tsx`（Sessions ページの実装を共通化）で連携アカウント
  を選んで Picker セッションを作成する。アカウント未登録時はプロフィールの
  連携セクションへ誘導する。
- **サイドバーをカテゴリ折りたたみ式に変更**。「メディア」「取り込み・同期」
  「管理」のカテゴリヘッダで開閉でき、状態は localStorage に保存。
  アイコンのみの折りたたみ幅ではカテゴリを常時展開する。

### Fixed
- **admin でもロール管理画面が「権限がありません」になる問題を修正**。
  `admin:system-settings` と `media:session` が API・画面で要求されているのに
  権限マスタ（`shared/domain/auth/master_data.py` の `PERMISSION_CODES`）に
  存在せず、どのロールにも付与できなかった。マスタへ追加（admin は全権限、
  manager に `media:session` を付与）し、適用済み DB 向けに不足分を冪等同期する
  マイグレーション `4c8d1e2f5a09_sync_permission_master_data.py` を追加。
  これによりサイドバーの管理系リンク（System Overview / Permissions /
  Service Accounts / Google Accounts）と Sessions / Sync Jobs も admin に
  表示されるようになる。ロール⇔権限の紐づけ UI は Roles 画面の作成・編集
  モーダル（権限チェックボックス）で、権限一覧の取得失敗時もロール一覧表示は
  維持されるよう分離した。
- **Google アカウントリンク後に画面へ結果が反映されない問題を修正**。
  OAuth コールバックの成否が Flask flash のみで通知され React SPA では
  何も表示されなかった。結果をクエリパラメータ（`google_link=ok|error`・
  `email`・`reason`）で戻り先に引き渡し、Google Accounts 画面と
  プロフィールの連携セクションが成功／失敗アラートを表示する。
  併せてコールバックが `current_user.id` に依存していて JWT クッキー失効時に
  失敗する問題を、OAuth 開始時にユーザー ID をセッション state へ保存して
  解消（`tests/webapp/auth/test_google_oauth_callback.py` で検証）。

- **Google アカウント連携ページを新設**（`/admin/google-accounts`、
  `GoogleAccountsPage.tsx`）。Sidebar からリンクのみ存在しページ未実装だったものを
  実装。Google アカウント登録（`POST /api/google/oauth/start` → 認可 URL へ遷移、
  コールバック後に本ページへ復帰）、連携済みアカウント一覧・有効/無効切替
  （PATCH）・接続テスト（POST `/test`）・連携解除（DELETE、リフレッシュトークン
  失効込み）ができる。
- **Google フォトからの Photo インポート UI を追加**（Sessions ページ）。
  連携済みアカウントを選択して `POST /api/picker/session` で Picker セッションを
  作成し、`pickerUri` を新規タブで開く。作成後はセッション詳細への導線を表示。
- **Google 連携用のシステム設定項目を追加**: `GOOGLE_OAUTH_REDIRECT_URI`
  （OAuth コールバック URL のスキーム・ホスト上書き。パスは
  `/auth/google/callback`（Flask ルート）で固定・変更不可で、パスが異なる値は
  保存時に拒否、環境変数等から不正な値が入った場合も警告ログを出して自動生成へ
  フォールバックする。空ならリクエストから自動生成）と
  `GOOGLE_PHOTO_PICKER_SCOPES`（Photo Picker 連携で要求するスコープの一覧）。
  defaults / settings.py / system_settings_definitions.py の3点セットで追加。
  redirect_uri は認可開始とトークン交換で完全一致が必要なため、両方が共通の
  `google_oauth_callback_url()`（`presentation/web/utils/url_helpers.py`）で
  生成する。
- **メディア検索を追加**（Media Gallery）。タグ（複数選択）・撮影日時範囲・
  メディア種別（写真/動画）で絞り込める `MediaSearchBar.tsx` を新設。
  バックエンド `GET /api/media` の既存 `tags`/`after`/`before`/`type`
  パラメータを利用（従来フロントは未対応の `is_video` を送っており種別フィルタが
  効いていなかった不具合も修正）。
- **アルバムへのメディア追加・表紙選択を実装**（アルバム詳細ページ）。
  「メディアを追加」からメディア検索（タグ・撮影日時・種別）付きの複数選択
  モーダル（`MediaPickerModal.tsx`）で画像・動画を選んで追加
  （`PUT /api/albums/<id>` の `mediaIds`）。各メディアカードの
  「表紙に設定」ボタンで表紙（`coverMediaId`）を選択でき、現表紙には
  バッジを表示。

- **`/healthz` を Web・API 双方に追加**（`presentation/web/routes/health.py` /
  `presentation/web/api/health.py`）。既存の `/health/live`・`/health/ready`
  （DB・NAS・Redis 疎通チェック）とは別に、デプロイ後「どのビルドが動作しているか」を
  即座に確認できる軽量エンドポイント。`version`・`commit_hash`・`commit_hash_full`・
  `branch`・`build_date`・UTC の `server_time` を返す。認証不要。
- フロントエンド `npm run build` 完了時にコミットハッシュ・ブランチ・ビルド日時を表示
  （`frontend/scripts/print-build-info.js`）。バックエンドの `make build`（Docker
  イメージビルド）は既に `version.json` を表示していたため未対応だったフロントエンド側を
  補完した。
- `scripts/deploy.sh` / `scripts/deploy-stg.sh` の完了時に、実際にデプロイされた
  web コンテナの `version.json`（コミットハッシュ含む）を表示するようにした。
- 非管理画面（Home/Dashboard/Media/Albums/Tags/Sessions/Jobs/Photo Imports/
  Photo Settings/Profile/Wiki 等）のモバイル対応。Sidebar を
  react-bootstrap の `Offcanvas`（`responsive="md"`）化し、768px 未満では
  ハンバーガーボタンからオーバーレイ式のドロワーとして開閉できるようにした
  （デスクトップでは従来どおりの折りたたみ幅サイドバーのまま）。Header の
  ハンバーボタンをモバイル用（ドロワー開閉）とデスクトップ用（折りたたみ）に分離。
  回帰検知用に `frontend/e2e/mobile_responsive.spec.ts`（375px viewportでの
  横スクロール有無を機械的に検証）を追加。
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

### Changed
- **favicon の配信場所を `/static/favicon.ico` に変更**。`frontend/index.html`
  の参照先を変更し、実体は `frontend/public/static/favicon.ico`（Vite）と
  `presentation/web/static/favicon.ico`（Flask）に配置。旧 `/favicon.ico` への
  リクエストは 302 で `/static/favicon.ico` へリダイレクトする。
- **ログイン画面のスタイル修正**: ヘッダ以外の背景を白に統一
  （`bg-light` を除去、Footer も白背景化）。高さを `h-100` 固定から
  flex-grow ベースに変更し、内容が画面に収まる場合は縦スクロールが
  発生しないようにした。

### Fixed
- `deploy-stg.sh reset` の `flask db stamp head` が `Can't connect to MySQL server
  on 'db' (Connection refused)` で失敗する問題が、修正（compose の db healthcheck
  への `--protocol=tcp` 追加と、stamp 前の DB 接続待機ループ）をリポジトリに
  マージした後も NAS 上で再発し続けていた。原因は、NAS 上の
  `/volume1/docker/scripts/deploy-stg.sh` と `/volume1/docker/docker-compose.yml`
  が手動コピー運用のため更新されず、待機ループのない旧スクリプトと
  ソケット越しに誤って healthy 判定する旧 healthcheck のまま実行されていたこと
  （実行ログに `Waiting for DB to accept connections` が出ていないことで特定）。
  恒久対策として、アプリイメージの tar を唯一の配布物にした:
  `docker-compose.yml` をイメージに焼き込み（`.dockerignore` の除外を解除）、
  デプロイスクリプトが `docker load` 直後にイメージから compose と自分自身を
  取り出して自己更新・自動再実行するようにした（`deploy.sh` / `deploy-stg.sh` 共通）。
  あわせて `flask db stamp/upgrade` に3回リトライを追加。前提条件は
  `tests/integration/test_deploy_asset_sync_consistency.py` が検証する。
  ※この仕組みが働き始めるには、NAS 上のスクリプトを今回の版へ**最後に一度だけ**
  手動コピーする必要がある（以後は tar の転送のみでスクリプト・compose も更新される）。
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
- ログイン画面で `invalid_token` 等の内部エラーコードがそのまま表示されることが
  あった不具合を修正。ログイン成功直後の `getCurrentUser()` が一時的に失敗する
  ケースなどで `state.error` に生のバックエンドコードが入ることがあったため、
  `LoginPage` では既知の利用者向けコード（`invalid_totp`・`invalid_credentials`）
  以外は表示しないようにした。
- ログイン/登録画面の `Container` が `min-vh-100` でビューポート全体を占有していた
  ため、共通レイアウトの `Footer`（バージョン表示）がスクロールしないと見えなかった
  不具合を修正。`h-100`（親の `<main>` に対する相対高さ）に変更し、スクロールなしで
  フッタが見えるようにした。
- フッタのバージョン表示が `vv1a2b3c4` のように "v" が二重になっていた不具合を修正。
  `version.json`（`scripts/generate_version.sh` 生成）の `version` フィールドは
  既に `v` 接頭辞込みの文字列のため、`Footer.tsx` 側で追加していた `v` を削除。

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

## T11 — FastAPI 全面移行・Flask 完全撤廃（2026-07-08）

### Added
- `presentation/fastapi/routers/wiki.py` — `/wiki/api/*` 16エンドポイント（Wiki JSON API）
- `presentation/fastapi/routers/certs.py` — `/api/certs/*`, `/api/keys/*`, `/api/.well-known/*` 17エンドポイント
- `presentation/fastapi/routers/local_import_status.py` — `/api/local-import/*` 9エンドポイント
- `migrations/versions/9d6e4a2b0f5c_add_impersonation.py` — `impersonation_audit_log` テーブルと `admin:impersonate` 権限コードを追加（T9 準備）
- `shared/kernel/database/db.py` に Flask-SQLAlchemy 互換レイヤー追加：
  - `Model.query` 互換ディスクリプタ（`db.session.query(cls)` に委譲）
  - `Table` staticmethod（MetaData 自動注入）
  - `func`, `JSON`, `Index`, `Enum`, `CHAR`, `Numeric`, `SmallInteger`, `CheckConstraint`, `init_app_engine()` 追加

### Removed
- `presentation/web/` — Flask アプリケーション全体を削除（Blueprint, Jinja2 テンプレート等）
- `bounded_contexts/wiki/presentation/wiki/` — Flask Blueprint 削除（FastAPI 版は `routers/wiki.py`）
- `bounded_contexts/certs/presentation/` — Flask Blueprint 削除（FastAPI 版は `routers/certs.py`）
- `bounded_contexts/photonest/presentation/photo_view/` — Flask Blueprint 削除
- `bounded_contexts/photonest/presentation/local_import_status_api.py` — Flask Blueprint 削除（FastAPI 版は `routers/local_import_status.py`）
- `bounded_contexts/totp/presentation/` — Flask Blueprint 削除
- `Flask-Mailman` を `requirements.txt` から削除（Flask 完全撤廃）
- Flask 依存テストを約50件削除（`presentation.web` 等インポート不可のため）

### Fixed
- `shared/infrastructure/models/impersonation_audit_log.py` — FK を `users.id` → `user.id` に修正（テーブル名が `user` のため）
- `migrations/versions/9d6e4a2b0f5c_add_impersonation.py` — テーブル名修正（`users`→`user`, `roles`→`role`, `permission_id`→`perm_id`）
- `db/init/01_initialize.sql` — `alembic_version` を最新ヘッド `9d6e4a2b0f5c` に更新
- `bounded_contexts/email_sender/application/email_service.py` — `gettext()` へのキーワード引数渡しを修正（`%` 演算子でフォーマット）
