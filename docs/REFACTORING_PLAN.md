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

### Phase 1 — `core` シムの張り替え（低リスク・機械的）

参照が少ないものから順に、import を `shared.kernel.*` へ張り替える。

1. `core.crypto`（5） → `shared.kernel.crypto.crypto`
2. `core.lifecycle_logging`（3） → `shared.kernel.logging.lifecycle_logging`
3. `core.db_log_handler`（6） → `shared.kernel.logging.db_log_handler`
4. `core.logging_config`（7） → `shared.kernel.logging.logging_config`
5. `core.system_settings_defaults`（14） → `shared.kernel.settings.system_settings_defaults`

各ステップ: import 張り替え → テスト → シム削除（または `__getattr__` のみ残す）。
**`core.db`（83）と `core.settings`（48）は影響範囲が大きいため Phase 2 で単独実施。**

### Phase 2 — `core.db` / `core.settings` の張り替え

最も参照の多い 2 モジュール。張り替えは機械的だが、ORM の `db` インスタンス同一性と
設定シングルトンの初期化順序に注意。

- `from core.db import db` → `from shared.kernel.database.db import db`
- `from core.settings import settings, ApplicationSettings` → `shared.kernel.settings.settings`
- 全テスト（unit + integration）で `db.metadata` の同一性・マイグレーション認識を確認。
- 完了後、`core/db.py` `core/settings.py` のシムを削除。

### Phase 3 — `picker_session` を `picker_import` コンテキストへ抽出（高リスク）

逆依存 #3・#4 の本丸。`presentation/web/api/picker_session{,_service}.py`（計 3000 行超）は
実体が picker セッションの**アプリケーションロジック**であり、本来は既存の
`bounded_contexts/picker_import/`（domain/application/infrastructure 完備）に属する。

現状の依存（`picker_session_service.py`）:
`core.settings` / `core.models.*` / `auth.utils`（→Phase 0 で共有化済の http_logging と
Google トークン更新）/ `core.tasks.local_import` / `concurrency` / `pagination` / `core.time`。

手順案:
1. `PickerSessionService` と定数（`SESSION_LOG_DEFAULT_LIMIT` 等）を
   `bounded_contexts/picker_import/application/picker_session_service.py` へ移設。
2. `auth.utils` への依存（`refresh_google_token` 等の Google OAuth）は
   `shared/` もしくは `email`/認証系コンテキストの application サービスへ切り出し。
3. `presentation/web/api/picker_session.py` と
   `photonest/presentation/photo_view` の双方を、コンテキストの application サービス
   経由に変更。
4. `pagination` / `concurrency` の共有ヘルパは `shared/` へ。

**前提:** Phase 1–2 完了（`core.settings`/`core.db` の張り替え済み）が望ましい。
影響が大きいため独立 PR とし、契約テストを先に用意する。

### Phase 4 — `core` 残置モジュールの最終移設（方針決定が必要）

| 対象 | 候補の移設先 | 論点 |
|---|---|---|
| `core/models/` | `shared/infrastructure/models/` もしくは各 context の infrastructure | 複数コンテキストで共有される ORM モデルの所有権 |
| `core/tasks/` | `shared/` もしくは各 context（Celery タスクはコンテキスト跨ぎのオーケストレーション） | タスク起動の責務分担 |
| `core/storage/` | `shared/kernel/storage/` もしくは `storage` bounded context | 既に `bounded_contexts/storage/` が存在 |
| `core/utils.py` `core/time.py` `core/version.py` | `shared/kernel/` | 純粋ユーティリティはカーネルへ |

このフェーズは設計判断を伴うため、着手前に方針合意を取る。

---

## 4. 進め方の原則

- 1 フェーズ = 1 PR を基本とし、各 PR でテストを緑にする。
- シムは「張り替え完了 → 削除」の順で、後方互換を一時的に維持。
- bounded context → `presentation.web` の新規依存は今後追加しない（レビュー観点）。

---

## 5. 進捗

- [x] Phase 0: 逆依存 #1（timezone）・#2（http_logging）解消
- [ ] Phase 1: 参照少数の `core` シム張り替え
- [ ] Phase 2: `core.db` / `core.settings` 張り替え
- [ ] Phase 3: `picker_session` を `picker_import` へ抽出（逆依存 #3・#4）
- [ ] Phase 4: `core` 残置モジュールの最終移設
