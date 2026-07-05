# CHANGELOG

完了した重要な変更を記録する（運用ルール: 完了項目は Progress.md から本ファイルへ移す）。
新しいものを上に追記する。書式は概ね Keep a Changelog 準拠。

## [Unreleased]

### Added
- **Google フォト取り込みのステータス表示と自動取り込みを追加**。
  ①Photo Imports 画面の Google Photos セクションに Local Import と同様の
  「Import Status」カードを追加（直近セッションの進行状況・件数・詳細リンク、
  進行中は自動更新）。②ヘッダーに通知ベルを追加し、実行中/直近の取り込み作業
  （Google フォト・ローカル）の一覧と詳細へのリンク、実行中件数バッジを表示。
  ③セッションのステータスを「写真の選択待ち」「取り込み中」「完了」等の
  分かりやすいラベルで表示（Sessions 一覧・詳細も統一）。

### Fixed
- **Google フォトで選択した写真が取り込まれない問題を修正**。Picker で選択を
  終えても取り込みを開始する処理がどこからも呼ばれておらず、セッションが
  永遠に pending のままだった。Celery beat の定期タスク
  `picker_session.advance`（1分間隔）を追加し、サーバー側で Google を
  ポーリングして選択完了を検知→mediaItems 取得→取り込みキュー投入まで自動で
  行うようにした（ブラウザを閉じても取り込みが完了する）。フロントエンドも
  進行中セッションをポーリングし、選択完了を検知したら即時取り込みを開始する。
  期限切れ（未選択のまま放置）のセッションは expired へ自動遷移する。

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
