# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T9 | ユーザースイッチ（運用管理者ロールによる成り代わり） | ⬜未着手 | 中 | 大 |
| 2 | T11 | FastAPI 全面移行（Flask-Smorest → FastAPI、既存 Blueprint 含む） | 🚧進行中 | 大 | 大 |

---

## 詳細

- **T9 ユーザースイッチ** — 運用管理者ロールが他ユーザーに成り代わって画面を確認できる
  機能（impersonation）。監査ログ（誰がいつ誰に切り替えたか）と成り代わり中の表示、
  元ユーザーへ戻る導線が必須。認可・セッション設計に影響するため ADR を書いてから着手。
- **T11 FastAPI 全面移行** — Flask + Flask-Smorest から FastAPI への全面移行。認証
  （flask_login / JWT）、Blueprint 群（→ APIRouter）、Celery 連携、OpenAPI 自動生成の
  置き換え。移行順序・共存戦略は ADR-0005 で決定済み（Strangler Fig パターン）。

  **完了済み（Phase 1 - Foundation）**:
  - ADR-0005 記述（`docs/decisions/ADR-0005-fastapi-migration.md`）
  - `requirements.txt` に FastAPI スタック追加（fastapi, uvicorn, pydantic, a2wsgi）
  - `shared/kernel/database/session.py` — 独立 SQLAlchemy セッションファクトリ
  - `presentation/fastapi/` — ディレクトリ構造・依存関係モジュール
  - `presentation/fastapi/app.py` — FastAPI アプリファクトリ
  - `asgi.py` — ASGI エントリポイント（Strangler Fig 構成）
  - `TokenService` の Flask 非依存化（`current_app` 除去）

  **完了済み（Phase 2 - ルーター移植）**:
  - `routers/health.py` — ヘルスチェック
  - `routers/auth.py` — ログイン/ログアウト/リフレッシュ/2FA/サービスアカウントトークン
  - `routers/auth_profile.py` — プロフィール更新・パスワードリセット・新規登録
  - `routers/auth_passkeys.py` — パスキー管理
  - `routers/version.py`, `routers/echo.py`, `routers/user_preferences.py`
  - `routers/totp.py` — TOTP 管理（CRUD + エクスポート/インポート）
  - `routers/sync_jobs.py` — 同期ジョブ履歴
  - `routers/local_import.py` — ローカルインポート管理
  - `routers/upload.py` — ファイルアップロード（prepare/commit）
  - `routers/service_account_keys.py` — API キー管理
  - `routers/service_account_signing.py` — 署名エンドポイント
  - `routers/maintenance.py` — メンテナンス API
  - `routers/picker_session.py` — Google Photos Picker セッション管理
  - `routers/admin/users.py`, `roles.py`, `groups.py`, `permissions.py`
  - `routers/admin/service_accounts.py`, `misc.py`, `config.py`, `photo_exports.py`

  **残作業（Phase 3）**:
  - `routes.py`（4238 行）のメディア/Google OAuth エンドポイント移植
  - Flask 側ルーターの段階的削除
  - 本番環境での uvicorn 起動への切り替え
  - 統合テストの追加
