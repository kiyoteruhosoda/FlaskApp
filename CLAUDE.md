# CLAUDE.md

このプロジェクト固有の設計ルール・制約事項をまとめる。

## ドキュメント運用

進捗・変更・設計判断は `docs/` 配下で管理する。

```
docs/
├── ARCHITECTURE.md    # 設計・レイヤー構成・命名規則（DDDの実装パターン解説）
├── OPERATIONS.md       # 手順書（下記「ドキュメントの役割分担」参照）
├── Progress.md        # 進行中・未着手タスクのみ
├── CHANGELOG.md       # 完了した重要な変更の要約
├── decisions/         # 設計判断（ADR-NNNN-*.md、雛形は ADR-template.md）
└── history/           # 後から経緯を追いたい規模の変更記録
```

運用ルール:

1. **開発開始時** → `docs/Progress.md` に TODO を追加する。
2. **作業中** → `docs/Progress.md` を更新する（状態・メモ）。
3. **完了時** → `docs/Progress.md` から削除し、重要なら `docs/CHANGELOG.md`（要約）／
   `docs/history/`（経緯）へ移す。Progress には完了項目を残さない。
4. **重要な変更だけ** `docs/history/` に記録する（細かな進捗は残さない）。
5. **設計判断は ADR** として `docs/decisions/ADR-NNNN-*.md` に残す。

### ドキュメントの役割分担（何をどこに書くか）

| ドキュメント | 役割 | 書くこと | 書かないこと |
|---|---|---|---|
| `docs/OPERATIONS.md` | 手順書 | 「〇〇したいとき、〇〇する」という操作手順・コマンドのみ | なぜそうなっているか、過去に何が起きたか、内部の仕組み、API仕様 |
| `docs/ARCHITECTURE.md` | 設計ガイド | レイヤー構成・命名規則・DDDパターンの解説 | 個別機能の操作手順、環境変数の一覧（OPERATIONS.md へ） |
| `scripts/README.md`（および各コンテキストの README） | 仕様書 | スクリプト・設定が**現在どう動くか**（現状の挙動・制約・注意点） | 「以前は〜だったが」「原因は〜だった」という過去の不具合の経緯 |
| `docs/CHANGELOG.md` | 変更履歴 | 過去の不具合とその原因・修正内容 | — |

迷ったら「これは手順か（OPERATIONS）」「設計の解説か（ARCHITECTURE）」
「現在の仕様か（README）」「過去の経緯か（CHANGELOG）」で判断する。
同じ内容を複数箇所に重複して書かない。

**APIエンドポイント仕様は手書きしない。** Flask-Smorest が自動生成する
Swagger UI（`/api/docs`）・一覧ページ（`/api/overview`）・`/api/openapi.json`
が唯一の出所。ドキュメントにはそこへのリンクだけを書く。

`docs/Progress.md` は**優先順・番号・概要・状態・影響度・工数の表**で書く。
補足が必要なものだけ表の下に「詳細」として番号付きで記載する。

```
| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T1 | 〇〇を実装 | 🚧進行中 | 中 | 大 |
```

- 状態: ⬜未着手 / 🚧進行中 / 🟡要判断
- 影響度・工数: 大 / 中 / 小

---

## 設計方針

- **DDD（ドメイン駆動設計）** を採用する。Presentation / Application / Domain / Infrastructure の4層構造。依存方向は Presentation → Application → Domain、Infrastructure は Domain のインターフェースを実装する。
- **SOLID 原則**を遵守する。特に SRP（単一責務）と DIP（依存性逆転）を重視。
- **依存注入**を使う。`new` の直接使用より Factory / コンストラクタインジェクションを優先。
- `util` / `helper` といった曖昧な名前のクラス・モジュールを作らない。
- 命名はドメイン語彙（ユビキタス言語）を使う。技術用語・略語で上書きしない。

---

## 環境要件

| 項目 | バージョン |
|---|---|
| Python | 3.11 以上（`python:3.11-slim` ベース） |
| MariaDB | 10.11.x |
| SQLAlchemy | 2.x（Declarative Base 構文） |
| Alembic | migrations/ 配下で管理 |
| Redis | 7.x（パスワード保護必須） |
| Gunicorn | `--workers=2 --threads=4` 推奨 |
| Node.js | 20.x LTS（フロントエンドビルド用） |
| ホスト | Linux / Synology DSM 7.x（Docker 上） |

---

## ディレクトリ構成

```
bounded_contexts/<context>/
  domain/           # ビジネスロジック（フレームワーク・DB依存なし）
  application/      # ユースケース・トランザクション境界
  infrastructure/   # DB・外部API実装
  presentation/     # Blueprint・Schema（そのコンテキスト固有のAPI）
  tasks/            # Celery タスク定義

shared/kernel/
  settings/         # settings.py, system_settings_defaults.py
  logging/          # 構造化ログ
  database/         # db.py (SQLAlchemy)
  crypto/           # 暗号化ユーティリティ

presentation/web/
  api/              # 共通・管理API（Blueprint群）
  api/schemas/      # Marshmallow スキーマ（presentation/web 全域で共有）
  translations/     # i18n .po ファイル
```

---

## 権限管理

- 認可は **ロールではなく scope（権限コード値）** で行う。ロール名での分岐禁止。
- 有効な scope = ユーザーの全ロールが持つ権限の和集合。
- 各エンドポイントに `@require_perms("scope_name")` デコレータを付ける。
- 権限の検証は Application 層で行い、Presentation 層には結果のみ渡す。
- JWT 発行時の scope はユーザーの保有権限の範囲内で指定。未指定・空 = 権限なし。

---

## DDL 管理

- テーブル変更は必ず **Alembic マイグレーションスクリプト** で行う。`ALTER TABLE` / `CREATE TABLE` を直接実行しない。
- マイグレーションファイルは `migrations/versions/<revision_id>_<description>.py`。
- 各ファイルの先頭に `from __future__ import annotations` を必ず記述。
- `upgrade()` / `downgrade()` の両方を実装する。
- ベースラインは `migrations/versions/init_master.py`（全テーブルを現行モデルから生成）。詳細は `migrations/README.md`。
- マスタデータ（ロール・権限・初期管理者）は `shared/domain/auth/master_data.py` を唯一の出所とし、`versions/*_seed_master_data.py` と `scripts/seed_master_data.py` の双方が参照する。値をどちらかに直書きしない。

---

## DB モデリング（SQLAlchemy）

- **DB ネイティブ ENUM カラムを使わない。** MariaDB の `ENUM` は値追加に `ALTER TABLE` が必要で DDL 運用と噛み合わず、序数変更でデータが壊れる。SQLAlchemy の `Enum(...)` を使う場合は必ず **`native_enum=False`**（全バックエンドで CHECK 制約付き VARCHAR になる）を指定する。あるいは `String` + 許可値の定数管理とする。
- 型安全のための Python 側の許可値集中管理（`enum.Enum` クラスや定数タプル）は推奨。禁止しているのは「DB 側のネイティブ ENUM 型」であって、Python の列挙そのものではない。
- 主キー等の `BigInteger` は SQLite テストとの両立のため `sa.BigInteger().with_variant(sa.Integer(), "sqlite")` を使う。
- モデルを変更したら必ず対応するマイグレーションを追加する。乖離は `tests/integration/test_migration_model_consistency.py` が検出する。

---

## 設定管理（Settings）

設定値の取得は **必ず `settings` オブジェクトの `@property` 経由**。直接アクセス禁止。

```python
# OK
from shared.kernel.settings.settings import settings
value = settings.some_property

# NG
os.getenv("SOME_KEY")
current_app.config["SOME_KEY"]
SystemSetting.query.get("some_key")
```

優先順位: 環境変数 > DB（system_settings テーブル）> デフォルト値

新しい設定キーを追加する場合は以下の3ファイルすべてを更新する:

1. `shared/kernel/settings/system_settings_defaults.py` — デフォルト値
2. `shared/kernel/settings/settings.py` — `@property` の追加
3. `presentation/web/admin/system_settings_definitions.py` — 管理画面項目

---

## API 設計（Flask-Smorest + Marshmallow）

- エンドポイントは Flask-Smorest の `Blueprint` として実装。
- リクエスト・レスポンスは Marshmallow `Schema` で定義し、Application 層には **バリデーション済みの dict** のみを渡す。
- Schema から直接 Domain モデルを生成しない（Application 層で変換）。

**Schema 命名規則**: `〇〇RequestSchema` / `〇〇ResponseSchema`

**配置先**:
- `presentation/web` 全体で使う共通スキーマ → `presentation/web/api/schemas/`
- 特定コンテキスト固有のスキーマ → `bounded_contexts/<context>/presentation/`

**デコレータ**: `@bp.arguments()` と `@bp.response()` を使うと OpenAPI 仕様が自動生成される。

---

## 国際化（i18n）

- 翻訳は `presentation/web/translations/` 配下の `.po` ファイルで管理。
- **`.mo` ファイルは生成しない**。`.po` を直接読み込む運用（ホットリロード優先）。
- 新規メッセージは英語で定義し翻訳キーとして扱う。日本語訳は `ja/LC_MESSAGES/messages.po` に手動追記。

```
presentation/web/translations/
  en/LC_MESSAGES/messages.po
  ja/LC_MESSAGES/messages.po
```

---

## ログ

- すべてのログは **JSON 形式**で出力し、同時に DB へ非同期書き込みする。
- ログには **PII を含めない**。ユーザー識別子は `user.id_hash` のみ使用。

| 出力先 | 追跡キー | 用途 |
|---|---|---|
| `appdb.log` テーブル | `requestId` | Flask/API リクエスト単位 |
| `appdb.worker_log` テーブル | `taskId` | Celery ジョブ単位 |

`requestId` と `taskId` を紐付けることで「APIリクエスト → Celeryタスク → 成果物」を一気通貫で追跡できる。

時刻は常に UTC（`UTC_TIMESTAMP(6)`）。traceback フィールドは NULLABLE（例外時のみ記録）。

---

## テスト

```
tests/
  unit/         # 外部依存なし（Domain 中心）
  integration/  # DB・ファイルシステムを使う
```

テスト収集は `--import-mode=importlib`（同名ファイルの衝突回避のため `pyproject.toml` に設定済み）。

デフォルトで除外されるマーカー: `ffmpeg`, `filesystem`, `smtp`（外部リソース要）。

時刻・乱数・UUID はテスト内で固定する（`unittest.mock.patch` で差し替え）。実環境の Clock クラスは存在しない。

---

## 動的呼び出しの制限

`getattr()` / `setattr()` / `eval()` / `exec()` / `globals()` / `locals()` による動的ディスパッチは原則禁止。標準ライブラリに対する参照（`hashlib` のアルゴリズム取得など）は例外。

メソッド名や属性名を文字列で渡して実行時に解決するパターンは避け、明示的なインターフェースを使う。
