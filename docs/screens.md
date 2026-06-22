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
| サービスログイン | `/auth/servicelogin` | サービスアカウント用 | — | ⬜ |
| 登録 | `/auth/register`(+`/totp`,`/no_totp`) | 新規ユーザー登録・TOTP セットアップ | `POST /api/auth/register` | ✅ `/register` |
| プロフィール | `/auth/profile` | 自分の情報表示・編集 | `GET /api/auth/me`, `PUT /api/auth/profile` | ✅ `/profile` |
| 編集 | `/auth/edit` | 表示名等の編集 | `PUT /api/auth/profile` | ✅（ProfilePage に統合） |
| TOTP 設定 | `/auth/setup_totp`(+cancel) | 2FA 登録・解除 | `GET /api/auth/2fa/status`, `POST /api/auth/2fa/setup`, `POST /api/auth/2fa/confirm`, `DELETE /api/auth/2fa` | ✅（ProfilePage に統合） |
| パスキー | `/auth/passkey/*` | WebAuthn 登録/ログイン/削除 | `POST /auth/passkey/options\|verify/{register,login}` | 🟡（ログインに統合） |
| パスワード再設定 | `/auth/password/forgot`,`/reset` | 失念時の再設定 | — | ⬜ |
| ログアウト | `/auth/logout` | セッション破棄 | `POST /api/auth/logout` | ✅ |
| Google 連携 | `/auth/settings/google-accounts` | OAuth 連携 | — | ⬜ |

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

### 2.2 React（移行中）
| 画面 | パス | 機能 | API | React |
|---|---|---|---|---|
| メディアギャラリー | `/media` | グリッド・種別フィルタ・追加読込・詳細モーダル(EXIF/タグ編集/動画再生) | `GET /api/media`, `POST /api/media/<id>/thumb-url`, `POST /api/media/<id>/playback-url`, `PUT /api/media/<id>/tags` | ✅ |
| アルバム一覧 | `/albums` | 表紙・件数・検索・**作成/編集/削除** | `GET /api/albums`, `POST /api/albums`, `PUT /api/albums/<id>`, `DELETE /api/albums/<id>` | ✅ |
| アルバム詳細 | `/albums/:id` | メディアグリッド・編集・削除・**DnD 並び替え** | `GET /api/albums/<id>`, `PUT /api/albums/<id>`, `DELETE /api/albums/<id>`, `PUT /api/albums/<id>/media/order` | ✅ |
| タグ一覧 | `/tags` | 一覧・検索・**タグ作成** | `GET /api/tags`, `POST /api/tags` | ✅ |
| 取り込みセッション一覧 | `/sessions` | 状態/種別/件数/詳細リンク | `GET /api/picker/sessions` | ✅ |

**写真管理 API（実装済）**: media 一覧/詳細・サムネ/再生署名URL・タグ付与、albums
CRUD＋メディア並び替え(`PUT /api/albums/<id>/media/order`)、tags 作成/一覧/付与。
React 側 write（CRUD/付与/動画再生）の配線が完了。

---

## 3. 同期ジョブ（Sync Jobs）

| 画面 | パス | 機能 | API | React |
|---|---|---|---|---|
| ジョブ履歴 | `/jobs` | 一覧・status/target/期間フィルタ・詳細(stats)・JSON DL・**再実行** | `GET /api/sync/jobs`,`GET /api/sync/jobs/<id>`,`POST /api/sync/jobs/<id>/retry` | ✅ |

要件 §18.10「同期ジョブ履歴 `/photo-view/sync/jobs`」は React `/jobs` で実現。
元データは `JobSync`（全 Celery 実行を記録）。

---

## 4. 管理（/admin, /dashboard 等）

> ℹ️ **ユーザー管理**は JSON API + React 画面が実装済み。他の管理系は引き続き
> Jinja フォーム POST が実体（JSON API 未整備）。

| 画面 | パス | 機能 | JSON API | React |
|---|---|---|---|---|
| ダッシュボード | `/dashboard/` | 統計 | ⬜ | ⬜ |
| ユーザー管理 | `/admin/user`(Jinja) / `/admin/users`(React) | CRUD・ロール付与・TOTP リセット | ✅ `GET/POST /api/admin/users`, `GET/PUT/DELETE /api/admin/users/<id>`, `PUT /api/admin/users/<id>/roles`, `POST /api/admin/users/<id>/reset-totp` | ✅ `/admin/users` |
| ロール一覧 | — | ロール一覧（ユーザー管理画面で利用） | ✅ `GET /api/admin/roles` | ✅（UsersPage に統合） |
| グループ | `/admin/groups`(+add/edit/delete) | CRUD | ⬜ | ⬜ |
| ロール CRUD | `/admin/roles`(+add/edit) | CRUD・権限割当 | ⬜ | ⬜ |
| 権限 | `/admin/permissions`(+add/edit/delete) | CRUD | ⬜ | ⬜ |
| サービスアカウント | `/admin/service-accounts`(+API keys) | CRUD・APIキー | ✅(`.json`) | ⬜ |
| Google アカウント | `/admin/google_accounts` | 連携管理 | ⬜ | ⬜ |
| 設定 | `/admin/config` | アプリ設定 | ⬜ | ⬜ |
| バージョン情報 | `/admin/version` | ビルド情報 | (`GET /api/version`) | ⬜ |
| データファイル | `/admin/data-files` | DLログ等 | ⬜ | ⬜ |
| TOTP 管理 | `/totp/` | 2FA 管理 | ✅ `/api/totp/*` | ⬜ |
| 証明書 | `/certs/*` | 証明書グループ/失効 | ⬜ | ⬜ |
| Wiki | `/wiki/*` | 一覧/閲覧/編集/履歴/カテゴリ/検索 | (`/wiki/api/*`) | ⬜ |

**管理 API（実装済）**: `presentation/web/api/admin_users.py`。要 `user:manage` 権限。
ロール CRUD / グループ / 権限 / 設定等の管理 JSON API は未整備。

---

## 5. ナビゲーション

- **Jinja**（`base.html`）: Home / Dashboard / Photo▼(Sessions, Media, Albums,
  Settings) / Wiki / Certs / Profile / Management▼(各管理) / Logout
- **React**（`Sidebar`）: Home / Dashboard / Media(Sessions, Sync Jobs, Media
  Gallery, Albums, Tags) / Administration(Users※, System Settings, Google Accounts)

※ Users リンクは `user:manage` 権限保有時のみ表示。

---

## 6. React 移行ロードマップ

1. ✅ 基盤（ビルド/ルーティング/JWT認証/APIクライアント/レイアウト）
2. ✅ 同期ジョブ履歴（一覧/詳細/再実行）＋取り込みセッション一覧
3. ✅ 写真管理 read（メディア/アルバム/タグ一覧・メディア詳細）
4. ✅ ログイン（パスワード/TOTP/ロール選択/ログアウト、パスキー統合）
5. ✅ 写真管理 write（アルバム CRUD/並び替え、タグ作成/付与、動画再生）
6. 🟡 管理 JSON API 層の新設 → 管理画面の React 化（**ユーザー管理完了**、ロール/グループ/権限/設定は未着手）
7. ✅ 認証 React 化（登録・プロフィール表示/編集・2FA 設定/解除）
8. ⬜ パスワード再設定・Google 連携の React 化
9. ⬜ Wiki の React 化
10. ⬜ Jinja からの完全切替（React `/` ホーム実装、旧テンプレート撤去）

## 7. 開発・テスト

- フロント: `cd frontend && npm ci && npm run build`（`tsc && vite`）。
- E2E: `npm run test:e2e`（Playwright）。API は `page.route` でモックし
  Flask/DB 非依存で実行。
- バックエンド: `pytest`（API は `tests/unit/presentation/api/`）。
- 依存: `frontend/node_modules` は **git 管理外**。CI/デプロイは `npm ci` 前提。
