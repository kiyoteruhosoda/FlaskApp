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

### 2.2 `core/` の中身（実体はシムのみ）

`core/` の **非シム実体は `core/version.py` のみ**（`core/version.json` 生成成果物と
密結合のため意図的に据え置き）。それ以外はすべて後方互換シム。

シムと正本（移動先）の対応:

| 旧パス（シム） | 正本（移動先） |
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

シムは `from <正本> import *` ＋ PEP 562 `__getattr__` で正本へ委譲しており、
旧パスの import は同一オブジェクトを返す（後方互換は保たれている）。

### 2.3 まだ `core.*` シムを参照している層（張替が必要な箇所）

**Phase A 完了**。すべての consumer を正本パスへ張替済み。

`grep -rn "from core\.\|import core\b" --include='*.py' .`（`core/` 除く）の出力:
- `core.version` 関連のみ残存（`presentation/web/admin/routes.py`、
  `presentation/web/api/version.py`、`presentation/web/bootstrap/cli_commands.py`）
- それ以外はゼロ（完了条件達成）

### 2.4 検証状況（重要）

本リファクタは、実行環境にフル依存（sqlalchemy / flask 拡張群 / ffmpeg 等）が
**未導入**のため、検証は **実機 import・シンボル同一性・ORM メタデータ登録・
構文チェック**で実施した。**`pytest` 全体は未実行**。

> したがって、以降の各ステップは **CI でのフルテスト緑を前提**に進めること。

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

### Phase B — `core/` シムの削除

Phase A 完了後、`core/` 配下のシムを削除する。

- 対象: `core/{db,settings,crypto,db_log_handler,logging_config,lifecycle_logging,
  system_settings_defaults,time,utils,celery_settings,storage_service}.py`、
  `core/storage/`、`core/models/`（`__init__` 含む）、`core/tasks/`（`__init__` 含む）。
- `core/__init__.py` が `from .utils import greet` / `from .db import db` を参照しているため、
  併せて整理（`core` パッケージ自体を削除するか、`version` のみ残すか決める）。
- 削除のたびに CI フルテストを実行し緑を確認。

### Phase C — `core/version.py` の最終配置

`core/version.py` は `core/version.json`（Docker ビルド生成物）を読む。`core/` を完全に
畳むなら、`shared/kernel/version.py` ＋ `version.json` の配置・生成スクリプト
（`scripts/generate_version.sh`）・参照（`flask version` / `GET /api/version`）を併せて移す。
据え置く判断もあり得る。要方針決定。

### Phase D — `settings` の storage factory 責務の整理

`shared/kernel/settings/settings.py` が遅延 import で
`bounded_contexts.storage.infrastructure.filesystem`（旧 `core.storage_service`）の
`StorageService` 実装を構築している（`settings.storage.service()` 系）。これは
**shared → bounded context** の逆方向結合であり smell。storage サービスの生成責務を
storage context（application/factory）へ移し、settings からは設定値のみを供給する形に
整理する。

---

## 4. 進め方の原則

- 1 Phase = 1 PR。各 PR で **CI フルテスト緑**を確認してからマージ。
- 移設・張替は「正本へ張替 → 動作確認 → シム削除」の順。後方互換を一時維持する。
- `bounded_contexts → presentation` および `shared → bounded_context` の**新規依存を
  追加しない**（レビュー観点）。
- ORM は単一 `db` への登録を維持（モデル移動時は二重登録・metadata 断片化に注意）。
- Celery タスク名は `cli/src/celery/tasks.py` の `name=` で明示されており不変
  （タスク実装ファイルの移動では名前は変わらない）。
