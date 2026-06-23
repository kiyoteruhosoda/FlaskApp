# CLAUDE.md

このプロジェクト固有の設計ルール・制約事項をまとめる。一般的なDDD/OOPの知識は省略し、このコードベースで迷う可能性のある判断のみを記載する。

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
