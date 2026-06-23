# リファクタリング段階計画: `core`/`shared` 統合と逆依存解消

本書は、レイヤー間の構造的負債を解消するための段階計画である。対象は大きく2つ。

1. **`core` と `shared` の統廃合**（横断的関心事の置き場所の一本化）
2. **bounded context → `presentation.web` への逆依存（4箇所）の解消**

各フェーズは独立してマージ可能なように粒度を分けている。

---

## 1. 現状整理

### 1.1 `core` と `shared` の関係

DDD の **Shared Kernel** を `shared/kernel/` に集約する移行が**進行中**。`core` の
横断的モジュールは、すでに `shared/kernel` へ実体が移り、`core` 側は後方互換シムに
変わっている。

| `core/` モジュール | 状態 | 実体の場所 |
|---|---|---|
| `db.py` `settings.py` `crypto.py` `db_log_handler.py` `logging_config.py` `lifecycle_logging.py` `system_settings_defaults.py` | **シム** | `shared/kernel/{database,settings,crypto,logging}/...` |
| `storage_service.py` | シム | `core/storage/`（未移行） |
| `models/` `tasks/` `storage/` `utils.py` `time.py` `version.py` `celery_settings.py` | **実体（未移行）** | `core/` のまま |

`shared/` 側は kernel 以外にも DDD レイヤーが揃っている。

```
shared/
  kernel/         # Shared Kernel（db / settings / crypto / logging / time）← 統合先
  domain/         # user, auth principal
  application/    # auth_service, passkey_service, api_urls
  infrastructure/ # user/passkey repository, http_logging
  presentation/   # （現状ほぼ空のプレースホルダ）
```

**結論:** 統合の方向はすでに `core → shared/kernel` で確定している。残るのは
「シム参照の張り替え」と「未移行モジュール（models/tasks/storage/utils/time）の
置き場所決定」。

### 1.2 シム参照の残量（張り替え対象）

| シム | 参照ファイル数（core/shared 以外） |
|---|---|
| `core.db` | 83 |
| `core.settings` | 48 |
| `core.system_settings_defaults` | 14 |
| `core.storage_service` / `core.logging_config` | 各 7 |
| `core.db_log_handler` | 6 |
| `core.crypto` | 5 |
| `core.lifecycle_logging` | 3 |

### 1.3 逆依存4箇所（bounded context → presentation.web）

| # | 依存元 | 依存先 | 性質 | 状態 |
|---|---|---|---|---|
| 1 | `wiki/presentation` | `presentation.web.templating.timezone` | 純粋な datetime ユーティリティ | ✅ **解消済み**（Phase 0） |
| 2 | `certs/presentation` | `presentation.web.auth.utils.log_requests_and_send` | 外向き HTTP + ログ | ✅ **解消済み**（Phase 0） |
| 3 | `photonest/presentation` | `presentation.web.api.picker_session`（定数） | picker セッションのアプリロジック | ⬜ 未着手（Phase 3） |
| 4 | `photonest/presentation` | `presentation.web.api.picker_session_service.PickerSessionService` | 同上（1658 行） | ⬜ 未着手（Phase 3） |

---

## 2. 目標アーキテクチャ

- 横断的関心事はすべて `shared/kernel/` を単一の真実の源とし、`core` のシムは段階的に削除。
- `core` に残すのは「まだ移設方針が未決のもの」のみ。最終的には `core` を解体し、
  ORM モデル・タスク・ストレージを適切な層（`shared` もしくは各 bounded context）へ移す。
- bounded context は `presentation.web`（アプリホスト／合成ルート）に**依存しない**。
  共有が必要なものは `shared/` 配下へ。
- `presentation.web` は合成ルート（`create_app`、bootstrap、middleware、openapi、
  blueprint 配線）と未コンテキスト化機能（admin/auth/dashboard/api）に限定。

---

## 3. フェーズ計画

### Phase 0 — 軽量な逆依存解消 ✅（本コミットで完了）

低リスク・即効性のある #1・#2 を先行実施。

- **timezone** ユーティリティを `shared/kernel/time/timezone.py` へ移設。
  - `presentation/web/templating/timezone.py` は後方互換シムとして再エクスポート。
  - `wiki` と `auth/routes.py` の import を `shared.kernel.time.timezone` へ更新。
- **log_requests_and_send**（＋マスキング処理・定数）を
  `shared/infrastructure/http_logging.py` へ移設。
  - `presentation/web/auth/utils.py` は同名を再エクスポート（`api/routes.py`・
    `picker_session_service.py`・テストの後方互換を維持）。
  - `certs` の import を `shared.infrastructure.http_logging` へ更新。

**成果:** 逆依存 4 → 2 に削減。`wiki` と `certs` から `presentation.web` への依存が消滅。

### Phase 1 — `core` シムの張り替え（低リスク・機械的）✅（本コミットで完了）

参照が少ないものから順に、**本番コード（production）**の import を
`shared.kernel.*` へ張り替えた。

1. `core.crypto` → `shared.kernel.crypto.crypto`
2. `core.lifecycle_logging` → `shared.kernel.logging.lifecycle_logging`
3. `core.db_log_handler` → `shared.kernel.logging.db_log_handler`
4. `core.logging_config` → `shared.kernel.logging.logging_config`
5. `core.system_settings_defaults` → `shared.kernel.settings.system_settings_defaults`

張り替えた本番ファイル（計 17）: `presentation/web/`（auth/api/admin/bootstrap/services）、
`bounded_contexts/photonest/`（media_processing / local_import ロガー・scheduler）、
`cli/src/celery/`、`main.py`、`wsgi.py`、`scripts/`。

**シム本体は意図的に残す**（`__getattr__` 付き再エクスポート）。理由:

- `migrations/versions/8c1f2e3d4b5a_*.py` が `core.system_settings_defaults` を
  参照しており、マイグレーションは履歴として不変に保つ。
- `tests/unit/core/` 配下にシム再エクスポートの同一性を検証するテストがあり、
  後方互換の回帰検知に有用。

→ 本番コードの `core` シム依存は解消。残る `core.*` 参照は `tests/` と
`migrations/` のみ。シム削除はフルテストスイートで安全確認できた段階で実施する。

**`core.db`（83）と `core.settings`（48）は影響範囲が大きいため Phase 2 で単独実施。**

### Phase 2 — `core.db` / `core.settings` の張り替え ✅（本コミットで完了）

最も参照の多い 2 モジュール。**本番コード66ファイル**の import を
正本へ張り替えた（フレーズ単位置換で `core.db_log_handler` 等を誤爆させない）。

- `from core.db import ...` → `from shared.kernel.database.db import ...`
- `from core.settings import ...` → `from shared.kernel.settings.settings import ...`

**`db` インスタンス同一性を実機検証済み**:
`core.db.db is shared.kernel.database.db.db == True`、
`core.settings.settings is shared.kernel.settings.settings.settings == True`。
シムが正本を再エクスポートしているため、import パスを変えても同一の単一
SQLAlchemy インスタンス／設定シングルトンを参照する（`db.metadata` 断片化なし）。

**シムは Phase 1 と同様に残置**。`core.db` / `core.settings` の残参照は `tests/`
（55 ファイル）のみで、後方互換のため shim を保持する。本番からの直接 `core`
参照は消滅。シム削除はフルテストスイートで安全確認できた段階で実施する。

### Phase 3 — `picker_session` を `picker_import` コンテキストへ抽出 ✅（本コミットで完了）

逆依存 #3・#4 の本丸。`PickerSessionService`（1658 行）は実体が picker セッションの
**アプリケーションロジック**であり、既存の `bounded_contexts/picker_import/` に移設した。
シムパターン（移設＋旧位置に後方互換シム）で実施。

実施内容:

1. **汎用ヘルパを共有層へ移設**（旧位置にシム）:
   - `presentation/web/api/pagination.py` → `shared/application/pagination.py`
   - `presentation/web/api/concurrency.py` → `shared/application/concurrency.py`
2. **Google OAuth を共有層へ移設**: `refresh_google_token` / `RefreshTokenError` を
   `presentation/web/auth/utils.py` から `shared/infrastructure/google_oauth.py` へ。
   `auth.utils` は OAuth・HTTP ロギングともに再エクスポートのみの薄いモジュールになった。
3. **`PickerSessionService` ＋ 定数 ＋ モジュールヘルパを移設**:
   `bounded_contexts/picker_import/application/picker_session_service.py`。
   旧 `presentation/web/api/picker_session_service.py` はシム化。
   `SESSION_LOG_DEFAULT_LIMIT` / `SESSION_LOG_MAX_LIMIT` の正本もここに集約。
4. **consumer を更新**:
   - `photonest/presentation/photo_view/routes.py` は context から直接 import
     → **逆依存 #3・#4 解消**。
   - `presentation/web/api/picker_session.py` は context／shared から import。
5. **service 内の late import 逆依存を解消**: `_enqueue_new_items` が
   `presentation.web.api.picker_session` 経由で呼んでいた `enqueue_picker_import_item`
   を正本 `core.tasks.picker_import` 直呼びへ変更。該当テストの monkeypatch 先も
   正本へ更新（`ps_module` の import 元のみ差し替え、patch 行は不変）。

検証: 移設モジュールが正しいシンボルで解決すること、シムが `import *` で同一
オブジェクトを再公開すること、移設 service が photonest の必要 API
（`resolve_session_identifier` / `selection_error_payload`）・定数・内部ヘルパを保持し
`_enqueue_new_items` が presentation を参照しないことを実機 import で確認済み。
シムは Phase 1–2 同様に残置（routes / tests の後方互換）。

**Phase 3 で新たに判明した別件の逆依存（未対応・要追跡）**:
当初の調査は `*/presentation/` のみ対象だったが、`application/` `infrastructure/`
にも `presentation.web` 依存が残存する。これらは picker_session 抽出とは独立で、
別タスクとして扱う。

- `bounded_contexts/wiki/application/use_cases.py`
  → `presentation.web.bootstrap.config.BaseApplicationSettings`,
    `presentation.web.services.upload_service.commit_uploads_to_directory`
- `bounded_contexts/email{,_sender}/infrastructure/factory.py`
  → `presentation.web.bootstrap.extensions.mail`（遅延 import）
- **推移依存**: `core.tasks.local_import` → `presentation.web.bootstrap.config`
  （`core → presentation` の構造的逆転。Phase 4 の `core/tasks` 再配置で解消すべき）

### Phase 3.x — 別件の逆依存解消 ✅（本コミットで完了）

Phase 3 で判明した、picker_session 抽出とは独立の `presentation.web` 逆依存を解消した。

1. **`BaseApplicationSettings.X` 参照 → 共有の `DEFAULT_APPLICATION_SETTINGS` 直読み**:
   `BaseApplicationSettings.MEDIA_LOCAL_IMPORT_DIRECTORY` 等は実体が
   `DEFAULT_APPLICATION_SETTINGS.get("...")`（`shared.kernel.settings`）なので、
   consumer 側でそこから直接読む形に変更し import を除去した。
   - `core/tasks/local_import.py`（推移依存の解消も兼ねる）
   - `bounded_contexts/wiki/application/use_cases.py`
   - `shared/application/upload_service.py`（移設に伴い）
2. **`mail`（Flask-Mailman）を共有層へ移設**:
   `presentation/web/bootstrap/extensions.py` の `mail = Mail()` を
   `shared/infrastructure/mail.py` へ集約（`db` と同方針）。extensions は再公開、
   `email` / `email_sender` の factory は `shared.infrastructure.mail` を参照。
3. **`upload_service` を共有層へ移設**:
   `presentation/web/services/upload_service.py` → `shared/application/upload_service.py`
   （旧位置はシム）。`wiki` は shared から `commit_uploads_to_directory` を import。

**成果: `bounded_contexts/* → presentation.web` の逆依存はゼロになった。**
`core → presentation` も実質ゼロ（残るのは `core/tasks/local_import.py` の
`if __name__ == "__main__"` ブロックで合成ルート `create_app` を呼ぶスクリプト
エントリのみ。モジュール import 時には実行されないため構造的依存ではない）。

検証: 移設した `mail` / `upload_service` がシム経由で同一オブジェクトを再公開し、
`core.tasks.local_import` ・ `wiki` ・ `email_sender` factory が presentation 連鎖
なしで import 解決することを実機確認。

> 補足（別件・未対応）: `bounded_contexts/email/infrastructure/smtp_sender.py` に
> `bounded_contexts.email_sender.email_message`（正しくは `...domain.email_message`）
> を指す既存の壊れた import がある。本フェーズとは無関係の先在バグ。

### Phase 4 — `core` 残置モジュールの最終移設（strict DDD 分割）

方針: `core/models` ・ `core/tasks` は **bounded context ごとに分割**（横断的なものは
shared へ）。各移設はシムパターン（移設＋旧位置に後方互換シム）で実施し、
`core/*` シムは presentation / tests / migrations / cli の後方互換のため残置する。

**4-a. `core/time.py` → `shared/kernel/time/clock.py` ✅**
純粋な UTC 時刻ヘルパをカーネルへ集約（timezone.py と同居）。

**4-b. `core/models/` を所有 context／共有へ分割 ✅**
- context 所有: `photo_models`→photonest, `picker_session`/`picker_import_task`→picker_import,
  `totp`→totp, `wiki/models`→wiki（各 infrastructure 層）
- 横断的（`shared/infrastructure/models/`）: user, group, authz, passkey,
  password_reset_token, service_account(_api_key), system_setting, log, worker_log,
  celery_task, google_account, job_sync
- 各モデルの db import を `shared.kernel.database.db` へ、`bounded_contexts`/`shared`
  内の `core.models.X` 参照(65箇所)を正本パスへ更新。`shared/infrastructure/__init__`
  を遅延化し循環 import を回避。
- 検証: 全30テーブルが二重登録なく登録、シム＝正本の同一性、循環なし。

**4-c. `core/tasks/` を所有 context／共有へ分割 ✅**
- photonest: `local_import`, `thumbs_generate`, `transcode`, `media_post_processing`
  → `bounded_contexts/photonest/tasks/`
- picker_import: `picker_import`, `session_recovery` → `bounded_contexts/picker_import/tasks/`
- 横断（maintenance）: `backup_cleanup`, `log_cleanup` → `shared/application/tasks/`
- Celery タスク名は `cli/src/celery/tasks.py` で `name="..."` 明示のため**不変**
  （cli は未変更）。`bounded_contexts`/`shared` 内の `core.tasks.X` 参照を正本へ更新。
- 検証: 全タスクモジュールが循環なく import 解決、シム＝正本の同一性、
  cli ラッパの import がシム経由で解決。

**4-d. 残りの軽量モジュール**

- **`core/utils.py` → `shared/kernel/utils.py` ✅**（シム）。`core.settings` 依存を
  shared へ。context 内参照（photonest/picker のメディア処理）を正本へ更新。
- **`core/celery_settings.py` → `shared/kernel/celery_settings.py` ✅**（シム）。
- **`core/storage/` + `core/storage_service.py`（据え置き・要設計）**:
  `core/storage`（`StorageService` 系の高レベル API）と
  `bounded_contexts/storage/infrastructure`（`LocalStorage`/repository 系）は
  **並行する別抽象**で `local.py` 等の名前衝突がある。機械的シム移設ではなく
  「2つの storage 抽象の統合」という設計判断を要するため、独立タスクとして扱う。
  現状 `core/storage` は既に `bounded_contexts.storage.domain` に依存しており
  部分的に DDD 整合済み。
- **`core/version.py`（据え置き）**: `core/version.json` 生成成果物と密結合のため
  移設価値が低く、`core/` に残す。

> 残置している `core/` の実体は `models/__init__`（シム集約）・`db.py`/`settings.py`
> 等のシム群・`storage*`・`version.py`・`tasks/__init__`（シム集約）のみ。
> 実装の本体は context／shared へ移動済み。

---

## 4. 進め方の原則

- 1 フェーズ = 1 PR を基本とし、各 PR でテストを緑にする。
- シムは「張り替え完了 → 削除」の順で、後方互換を一時的に維持。
- bounded context → `presentation.web` の新規依存は今後追加しない（レビュー観点）。

---

## 5. 進捗

- [x] Phase 0: 逆依存 #1（timezone）・#2（http_logging）解消
- [x] Phase 1: 参照少数の `core` シム張り替え（本番コード／シムは後方互換で残置）
- [x] Phase 2: `core.db` / `core.settings` 張り替え（本番66ファイル／同一性検証済・シム残置）
- [x] Phase 3: `picker_session` を `picker_import` へ抽出（逆依存 #3・#4 解消／シム残置）
- [x] Phase 3.x: 別件の逆依存解消（bounded_contexts → presentation はゼロに）
- [x] Phase 4-a: `core/time.py` → `shared/kernel/time/clock.py`
- [x] Phase 4-b: `core/models/` を context／shared へ strict DDD 分割（30テーブル検証済）
- [x] Phase 4-c: `core/tasks/` を context／shared へ strict DDD 分割（Celery 名不変・検証済）
- [x] Phase 4-d: `core/utils.py` ・ `core/celery_settings.py` → `shared/kernel/`
- [ ] Phase 4-e（要設計）: `core/storage` と `bounded_contexts/storage` の統合（並行抽象）
