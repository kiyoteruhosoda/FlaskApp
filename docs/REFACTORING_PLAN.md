# `core` 解体・DDD 整理 ハンドオフ計画

次セッションへの引き継ぎ用。**目的・現状・残りの計画**のみを記載する。

---

## 1. 目的

DDD レイヤード構造を徹底し、レガシーな `core/` パッケージを解体する。

- **bounded context は `presentation` に依存しない**（依存方向は presentation → context → shared）。
- **横断的関心事は `shared/` に集約**する。
  - `shared/kernel/`（db / settings / crypto / logging / time / utils 等の Shared Kernel）
  - `shared/application/`（横断アプリケーションサービス）
  - `shared/infrastructure/`（横断 infrastructure・共有 ORM モデル）
- **実装本体は所有 bounded context または `shared` に置く**。`core/` は最終的に削除する
  （現状は後方互換シムのみが残っている）。
- 各モデル／タスク／サービスは **strict DDD**（所有 context ごと）に配置する。横断的な
  もののみ `shared` に置く。

---

## 2. 現状

### 2.1 達成済みの不変条件（壊さないこと）

- `bounded_contexts/* → presentation` の参照は **ゼロ**。
- `bounded_contexts/* ・ shared/* → core.* シム` の参照は **ゼロ**
  （context／shared は正本パスのみを参照する）。
- ORM は単一の `shared.kernel.database.db` に全 30 テーブルが**二重登録なく**登録される。

### 2.2 `core/` の中身（Phase B 完了）

**Phase B 完了**。`core/` のシムファイルはすべて削除済み。

残存ファイル（削除対象外）:
- `core/__init__.py` — 空パッケージ宣言のみ（`version` 参照のため残置）
- `core/version.py` — 非シム実体（`core/version.json` と密結合）

削除済みシムのうち正本（移動先）の対応は以下のとおり（参照用）:

| 旧パス（シム、削除済み） | 正本（移動先） |
|---|---|
| `core.db` | `shared.kernel.database.db` |
| `core.settings` | `shared.kernel.settings.settings` |
| `core.crypto` | `shared.kernel.crypto.crypto` |
| `core.logging_config` / `core.db_log_handler` / `core.lifecycle_logging` | `shared.kernel.logging.*` |
| `core.system_settings_defaults` | `shared.kernel.settings.system_settings_defaults` |
| `core.time` | `shared.kernel.time.clock` |
| `core.utils` | `shared.kernel.utils` |
| `core.celery_settings` | `shared.kernel.celery_settings` |
| `core.storage` / `core.storage_service` | `bounded_contexts.storage.infrastructure.filesystem` |
| `core.models.photo_models` | `bounded_contexts.photonest.infrastructure.photo_models` |
| `core.models.picker_session` / `picker_import_task` | `bounded_contexts.picker_import.infrastructure.*` |
| `core.models.totp` | `bounded_contexts.totp.infrastructure.totp_models` |
| `core.models.wiki.models` | `bounded_contexts.wiki.infrastructure.wiki_models` |
| `core.models.{user,group,authz,passkey,password_reset_token,service_account,service_account_api_key,system_setting,log,worker_log,celery_task,google_account,job_sync}` | `shared.infrastructure.models.*` |
| `core.tasks.{local_import,thumbs_generate,transcode,media_post_processing}` | `bounded_contexts.photonest.tasks.*` |
| `core.tasks.{picker_import,session_recovery}` | `bounded_contexts.picker_import.tasks.*` |
| `core.tasks.{backup_cleanup,log_cleanup}` | `shared.application.tasks.*` |

### 2.3 `core.*` 参照状況

Phase A〜C 完了により `core/` は完全削除済み。`core.*` 参照はゼロ。
`shared → bounded_context` 逆方向結合も Phase D で解消済み。

### 2.4 検証状況

Phase D 完了時点（2026-06-23）の pytest フルテスト:
145 failed, 1000 passed, 50 skipped — Phase C 比 同一カウント（新規回帰なし）。
479 errors は Phase D 着手前（Phase C/B 並行作業中）に修正済み:
`cli/src/celery/celery_app.py` に cross-context モデルの先行 import を追加することで解消。

> `test_password_reset`・`test_csrf`・`test_version_admin` 等の既存失敗は本リファクタ範囲外。

---

## 3. 計画（残作業）

各 Phase は独立 PR とし、着手時に対象 grep で最新状況を再確認すること。

### Phase A — consumer の core.* 参照を正本へ張替 ✅ 完了

`core/` シムをまだ参照している層を正本へ張り替えた（§2.2 の対応表を使用）。

完了条件: `grep -rn "from core\.\|import core\b" --include='*.py' .`（`core/` 除く）が
`core.version` 関連を除きゼロ → **達成済み**。

付随作業:
- `shared/infrastructure/models/__init__.py` に全共有モデルの一括エクスポートを追加
  （SQLAlchemy マッパー文字列解決の順序を保証するため）。
- `presentation/web/__init__.py` のモデル import を `apply_persisted_settings`
  より前に移動（マッパー設定前の全モデル登録を保証）。
- `presentation/web/templating/jinja_filters.py` を新規作成（欠落していた実装）。

### Phase B — `core/` シムの削除 ✅ 完了

`core/` 配下のシムをすべて削除した。

削除対象:
- `core/{db,settings,crypto,db_log_handler,logging_config,lifecycle_logging,
  system_settings_defaults,time,utils,celery_settings,storage_service}.py`
- `core/storage/`、`core/models/`（`__init__` 含む）、`core/tasks/`（`__init__` 含む）

付随作業:
- `core/__init__.py` を空パッケージ宣言のみに整理
  （削除した `.utils.greet` / `.db.db` の参照を除去）。
- `tests/unit/core/test_crypto.py` を正本パス
  `from shared.kernel.crypto import crypto` へ更新（唯一残っていた shim 参照）。

完了条件: `core/` 内に残るのは `__init__.py`・`version.py` のみ → **達成済み**。

### Phase C — `core/version.py` の最終配置 ✅ 完了

`core/version.py` を `shared/kernel/version.py` へ移動し、`core/` ディレクトリを完全に削除した。

変更内容:
- `shared/kernel/version.py` 新規作成（`core/version.py` の実体を移動）
- `shared/kernel/version.json` 生成先として `scripts/generate_version.sh` を更新
- 参照先を更新: `presentation/web/api/version.py`、`presentation/web/admin/routes.py`、
  `presentation/web/bootstrap/cli_commands.py`
- `tests/unit/core/test_version_*.py` のパッチ文字列・インポートを正本パスへ更新
- `core/` ディレクトリを完全削除

完了条件: `from core.` 参照がゼロ → **達成済み**。

### Phase D — `settings` の storage factory 責務の整理 ✅ 完了

`shared/kernel/settings/settings.py` の `shared → bounded_context` 逆方向結合を解消した。

変更内容:
- `StorageBackendType` / `StorageDomain` / `StorageIntent` / `StorageResolution` を
  `shared/kernel/storage_types.py` へ昇格（純粋な enum; 依存なし）
- `bounded_contexts/storage/domain/types.py` は `shared.kernel.storage_types` から再エクスポート
- `bounded_contexts/storage/application/filesystem_factory.py` を新規作成:
  `LocalFilesystemStorageService` / `AzureBlobStorageService` / `ExternalRestStorageService` の
  ファクトリ責務をここに集約（`create_storage_service()` / `get_storage_service()`）
- `settings.py` の `_StorageAccessor` から factory 責務を除去し、設定値アクセサ
  （`configured()` / `environment()`）のみに縮小
- `settings.storage_*_directory` 各プロパティを `_path_or_default()` 直呼び出しに変更
  （StorageService 経由でなく設定値から直接解決）
- `settings.storage.service()` の呼び出し元（10 ファイル）を
  `filesystem_factory.get_storage_service(settings)` へ張替
- `tests/unit/core/test_storage_service.py` を新 API に合わせて更新

完了条件: `settings.py` に `bounded_contexts.*` import が残らないこと → **達成済み**。

---

## 4. 進め方の原則

- 1 Phase = 1 PR。各 PR で **CI フルテスト緑**を確認してからマージ。
- 移設・張替は「正本へ張替 → 動作確認 → シム削除」の順。後方互換を一時維持する。
- `bounded_contexts → presentation` および `shared → bounded_context` の**新規依存を
  追加しない**（レビュー観点）。
- ORM は単一 `db` への登録を維持（モデル移動時は二重登録・metadata 断片化に注意）。
- Celery タスク名は `cli/src/celery/tasks.py` の `name=` で明示されており不変
  （タスク実装ファイルの移動では名前は変わらない）。
