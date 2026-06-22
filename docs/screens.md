# 画面ドキュメント（Screen Reference）

PhotoNest の全画面・遷移・機能と、React 移行状況／API 対応をまとめる。
UI は現在 **2系統**が併存している：

- **Jinja サーバーレンダリング**（実体・全機能）— `base.html` を継承する各 Blueprint。
- **React SPA**（移行中）— `frontend/`（Vite + React + Redux + react-router）。
  ルートに**未マッチの非API**は React の catch-all が SPA を返す。`frontend/build`
  が無い場合は開発案内 HTML を返す。

> 凡例（React 状況）: ✅=React実装済 / 🟡=部分 / ⬜=未着手（Jinjaのみ）

---

## 1. 認証（/auth, /api/auth）

| 画面 | パス | 機能 | API | React |
|---|---|---|---|---|
| ログイン | `/auth/login` | ID/パスワード、TOTP、失敗時メッセージ | `POST /api/auth/login` | ✅ `/login` |
| ロール選択 | `/auth/select-role` | 複数ロール時に有効ロール選択 | `GET /api/auth/roles`, `POST /api/auth/select-role` | ✅ `/select-role` |
| サービスログイン | `/auth/servicelogin` | サービスアカウント用（機械間通信） | — | ✅ 画面なし |
| 登録 | `/auth/register`(+`/totp`,`/no_totp`) | 新規ユーザー登録・TOTP セットアップ | `POST /api/auth/register` | ✅ `/register` |
| プロフィール | `/auth/profile` | 自分の情報表示・編集 | `GET /api/auth/me`, `PUT /api/auth/profile` | ✅ `/profile` |
| 編集 | `/auth/edit` | 表示名等の編集 | `PUT /api/auth/profile` | ✅（ProfilePage に統合） |
| TOTP 設定 | `/auth/setup_totp`(+cancel) | 2FA 登録・解除 | `GET /api/auth/2fa/status`, `POST /api/auth/2fa/setup`, `POST /api/auth/2fa/confirm`, `DELETE /api/auth/2fa` | ✅（ProfilePage に統合） |
| パスキー管理 | `/auth/passkey/*` | WebAuthn 登録/ログイン/削除 | `GET /api/auth/passkeys`, `DELETE /api/auth/passkeys/<id>`, `POST /auth/passkey/options\|verify/{register,login}` | ✅（ProfilePage に統合） |
| パスワード再設定 | `/auth/password/forgot`,`/reset` | 失念時の再設定 | `POST /api/auth/password/forgot`, `POST /api/auth/password/reset` | ✅ `/forgot-password`, `/reset-password` |
| ログアウト | `/auth/logout` | セッション破棄 | `POST /api/auth/logout` | ✅ |
| Google 連携 | `/auth/settings/google-accounts` | OAuth 連携（OAuthリダイレクトフロー） | — | ✅ 画面なし |

**ログイン認証フロー（API）**: `POST /api/auth/login` は
`invalid_credentials`(401) / `totp_required`(401) / `invalid_totp`(401) を返し、
成功時は `access_token`/`refresh_token` と、複数ロール時 `requires_role_selection`。

---

## 2. 写真管理（PhotoNest）

### 2.1 Jinja（/photo-view, 要 `media:view`）
| 画面 | パス | 機能 |
|---|---|---|
| ルート | `/photo-view/` | → albums へリダイレクト |
| セッション一覧 | `/photo-view/session` | 取り込みセッション一覧・作成・実行/停止 |
| セッション詳細 | `/photo-view/session/<id>` | セッション詳細・ログ |
| 取込失敗詳細 | `/photo-view/session/<id>/selection/<sid>/error` | ファイル単位の失敗詳細 |
| メディア一覧 | `/photo-view/media` | 写真/動画一覧・検索 |
| メディア詳細 | `/photo-view/media/<id>` | 原寸/再生・EXIF・タグ |
| アルバム一覧 | `/photo-view/albums` | アルバム一覧 |
| アルバム詳細 | `/photo-view/albums/<id>` | アルバム内メディア・並び替え |
| アルバム作成/編集 | `/photo-view/albums/create`,`/<id>/edit` | フォーム |
| スライドショー | `/photo-view/albums/<id>/slideshow` | 再生 |
| タグ一覧 | `/photo-view/tags` | タグ一覧 |
| 設定 | `/photo-view/settings` | NASパス・サムネ/変換・同期状態（要 `admin:photo-settings`） |
| エクスポート | `/photo-view/admin/exports`(+`/<id>`) | エクスポート（要 `system:manage`） |

### 2.2 React（移行完了）
| 画面 | パス | 機能 | API | React |
|---|---|---|---|---|
| メディアギャラリー | `/media` | グリッド・種別フィルタ・追加読込・詳細モーダル(EXIF/タグ編集/動画再生) | `GET /api/media`, `POST /api/media/<id>/thumb-url`, `POST /api/media/<id>/playback-url`, `PUT /api/media/<id>/tags` | ✅ |
| アルバム一覧 | `/albums` | 表紙・件数・検索・**作成/編集/削除** | `GET /api/albums`, `POST /api/albums`, `PUT /api/albums/<id>`, `DELETE /api/albums/<id>` | ✅ |
| アルバム詳細 | `/albums/:id` | メディアグリッド・編集・削除・**DnD 並び替え**・**スライドショー起動** | `GET /api/albums/<id>`, `PUT /api/albums/<id>`, `DELETE /api/albums/<id>`, `PUT /api/albums/<id>/media/order` | ✅ |
| スライドショー | `/albums/:id/slideshow` | フルスクリーン再生・自動再生・キーボード操作 | `GET /api/albums/<id>`, `POST /api/media/<id>/thumb-url` | ✅ |
| タグ一覧 | `/tags` | 一覧・検索・**タグ作成** | `GET /api/tags`, `POST /api/tags` | ✅ |
| 取り込みセッション一覧 | `/sessions` | 状態/種別/件数/詳細リンク | `GET /api/picker/sessions` | ✅ |
| セッション詳細 | `/sessions/:sessionId` | セッション情報・取込ファイル一覧（ステータスフィルタ）・ログ | `GET /api/picker/session/<id>`, `GET /api/picker/session/<id>/selections`, `GET /api/picker/session/<id>/logs` | ✅ |
| 取込失敗詳細 | `/sessions/:sessionId/selection/:id/error` | 失敗ファイルのエラーメッセージ・関連ログ | `GET /api/picker/session/<id>/selections/<sid>/error` | ✅ |
| 写真設定 | `/photo-settings` | NASパス状態・ローカルインポート実行（要 `admin:photo-settings`） | `GET /api/sync/local-import/status`, `POST /api/sync/local-import` | ✅ |
| エクスポート | `/admin/photo-exports` | エクスポート管理（プレースホルダー、要 `system:manage`） | — | ✅ |

**写真管理 API（実装済）**: media 一覧/詳細・サムネ/再生署名URL・タグ付与、albums
CRUD＋メディア並び替え(`PUT /api/albums/<id>/media/order`)、tags 作成/一覧/付与、
セッション詳細・選択エラー・ログ、ローカルインポートステータス/実行。

---

## 3. 同期ジョブ（Sync Jobs）

| 画面 | パス | 機能 | API | React |
|---|---|---|---|---|
| ジョブ履歴 | `/jobs` | 一覧・status/target/期間フィルタ・詳細(stats)・JSON DL・**再実行** | `GET /api/sync/jobs`,`GET /api/sync/jobs/<id>`,`POST /api/sync/jobs/<id>/retry` | ✅ |

要件 §18.10「同期ジョブ履歴 `/photo-view/sync/jobs`」は React `/jobs` で実現。
元データは `JobSync`（全 Celery 実行を記録）。

---

## 4. 管理（/admin, /dashboard 等）

| 画面 | パス | 機能 | JSON API | React |
|---|---|---|---|---|
| システム概要 | `/admin/dashboard` | 統計・最近のジョブ | ✅ `GET /api/admin/dashboard` | ✅ `/admin/dashboard` |
| ユーザー管理 | `/admin/users` | CRUD・ロール付与・TOTP リセット | ✅ `GET/POST /api/admin/users`, `GET/PUT/DELETE /api/admin/users/<id>`, `PUT /api/admin/users/<id>/roles`, `POST /api/admin/users/<id>/reset-totp` | ✅ `/admin/users` |
| ロール管理 | `/admin/roles` | CRUD・権限割当 | ✅ `GET/POST /api/admin/roles`, `GET/PUT/DELETE /api/admin/roles/<id>` | ✅ `/admin/roles` |
| グループ管理 | `/admin/groups` | CRUD・階層（親子） | ✅ `GET/POST /api/admin/groups`, `GET/PUT/DELETE /api/admin/groups/<id>` | ✅ `/admin/groups` |
| 権限管理 | `/admin/permissions` | CRUD・検索 | ✅ `GET/POST /api/admin/permissions`, `GET/PUT/DELETE /api/admin/permissions/<id>` | ✅ `/admin/permissions` |
| サービスアカウント | `/admin/service-accounts` | CRUD・スコープ | ✅ `GET/POST /api/admin/service-accounts`, `GET/PUT/DELETE /api/admin/service-accounts/<id>` | ✅ `/admin/service-accounts` |
| Google アカウント | `/admin/google_accounts` | OAuth 連携管理（外部OAuth設定依存） | ⬜ | ✅ 画面なし |
| 設定 | `/admin/config` | アプリ設定（セクション別・検索・CORS・トークン署名）。モダンUIに刷新 | ✅ `GET /api/admin/config`, `PUT /api/admin/config`, `PUT /api/admin/config/cors`, `PUT /api/admin/config/signing` | ✅ `/admin/config` |
| バージョン情報 | `/admin/version` | ビルド情報 | `GET /api/version` | ✅ 画面なし |
| データファイル | `/admin/data-files` | DLログ等（バックエンド管理ツール） | ⬜ | ✅ 画面なし |
| TOTP 管理 | `/totp/` | 2FA 管理（管理者用） | ✅ `/api/totp/*` | ⬜ |
| 証明書 | `/certs/*` | 証明書グループ/失効（PKI管理ツール） | ⬜ | ✅ 画面なし |
| Wiki | `/wiki/*` | 一覧/閲覧/編集/履歴（Jinja複合UI） | `/wiki/api/*` | ✅ 画面なし |

**管理 API（実装済）**:
- `presentation/web/api/admin_users.py` — ユーザー CRUD（`user:manage`）
- `presentation/web/api/admin_roles.py` — ロール CRUD（`user:manage`）
- `presentation/web/api/admin_groups.py` — グループ CRUD（`user:manage`）
- `presentation/web/api/admin_permissions.py` — 権限 CRUD（`admin:system-settings`）
- `presentation/web/api/admin_service_accounts.py` — サービスアカウント CRUD（`admin:system-settings`）
- `presentation/web/api/admin_misc.py` — ダッシュボード統計（`admin:system-settings`）
- `presentation/web/api/admin_config.py` — アプリ設定／CORS／トークン署名（`system:manage`）

---

## 5. ナビゲーション

- **Jinja**（`base.html`）: Home / Dashboard / Photo▼(Sessions, Media, Albums,
  Settings) / Wiki / Certs / Profile / Management▼(各管理) / Logout
- **React**（`Sidebar`）: Home / Media(Sessions, Sync Jobs, Media
  Gallery, Albums, Tags) / Administration(System Overview, Users, Roles, Groups, Permissions, Service Accounts, System Settings, Google Accounts)

管理メニューは権限によって表示制御：
- `admin:system-settings`: System Overview, Permissions, Service Accounts, System Settings, Google Accounts
- `user:manage`: Users, Roles, Groups

---

## 6. React 移行ロードマップ

1. ✅ 基盤（ビルド/ルーティング/JWT認証/APIクライアント/レイアウト）
2. ✅ 同期ジョブ履歴（一覧/詳細/再実行）＋取り込みセッション一覧
3. ✅ 写真管理 read（メディア/アルバム/タグ一覧・メディア詳細）
4. ✅ ログイン（パスワード/TOTP/ロール選択/ログアウト、パスキー統合）
5. ✅ 写真管理 write（アルバム CRUD/並び替え、タグ作成/付与、動画再生）
6. ✅ 管理 JSON API 新設＋React 化（ユーザー/ロール/グループ/権限/サービスアカウント/ダッシュボード）
7. ✅ 認証 React 化（登録・プロフィール表示/編集・2FA 設定/解除・パスキー管理）
8. ✅ パスワード再設定 React 化（`/forgot-password`, `/reset-password`）
9. ✅ 写真管理 全画面 React 化（セッション詳細/取込失敗詳細/スライドショー/写真設定/エクスポート）
10. ✅ アプリ設定 React 化（`/admin/config` — セクション別UI・検索・CORS・トークン署名）
11. ⬜ Wiki の React 化
12. ⬜ Jinja からの完全切替（React `/` ホーム実装、旧テンプレート撤去）

## 7. 開発・テスト

- フロント: `cd frontend && npm ci && npm run build`（`tsc && vite`）。
- E2E: `npx playwright test`（Playwright、`frontend/e2e/`）。API は `page.route` でモックし
  Flask/DB 非依存で実行。テスト対象: login, register, profile, sessions, jobs, photos,
  photos_extended（セッション詳細/スライドショー/写真設定/エクスポート）, auth (forgot/reset password),
  admin (dashboard/roles/groups/permissions/service-accounts), config（アプリ設定）。
- バックエンド: `uv run pytest`（API は `tests/unit/presentation/api/`）。
  新規テスト: `test_api_admin_crud.py`（26件）、`test_api_new_auth_endpoints.py`（15件）、
  `test_api_admin_config.py`（22件）。
- 依存: `frontend/node_modules` は **git 管理外**。CI/デプロイは `npm ci` 前提。
