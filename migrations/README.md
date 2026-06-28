# マイグレーション管理

Alembic（Flask-Migrate 経由）でデータベーススキーマを管理する。

---

## ベースライン（init_master）

`migrations/versions/init_master.py` が**唯一のベースライン**。現行の SQLAlchemy
モデル定義（`db.metadata`）から機械生成しており、全テーブルを一括作成する。
過去の断片的なリビジョン群は、ヘッド分岐・重複テーブル定義・モデルとの乖離が
あったため、この単一ベースラインに統合・置換した。

- リビジョン ID: `init_master` / `down_revision = None`（ベース）
- `init_master` は**スキーマ（DDL）専用**。マスタデータは含めない。

### マスタデータ（ロール・権限・管理者）

認可マスタデータの値は `shared/domain/auth/master_data.py` を**唯一の出所**とし、
以下の2経路が同じカタログを参照する（二重管理を排除）:

| 経路 | ファイル | 用途 |
|---|---|---|
| データマイグレーション | `versions/2a1f9c0b3d4e_seed_master_data.py` | `flask db upgrade` で自動投入（冪等） |
| 投入スクリプト | `scripts/seed_master_data.py` | 手動投入・システム設定も含む（冪等） |

初期管理者のパスワードは環境変数 `ADMIN_INITIAL_PASSWORD`（平文）で上書き可能。
未指定時はフォールバックハッシュ（平文 `admin`）が使われるため**本番では必ず変更**する。

### 新規 DB の初期化

```bash
# スキーマ + 認可マスタデータ（ロール/権限/管理者）まで一括
ADMIN_INITIAL_PASSWORD='set-a-strong-one' flask db upgrade

# システム設定（app.config / app.cors）も含めて投入する場合
python scripts/seed_master_data.py
```

### 既存（本番）DB への適用

既存 DB は旧リビジョンで `alembic_version` が記録されているため、スキーマを
作り直さずにベースラインの印だけ付け替える:

```bash
flask db stamp init_master
```

> スキーマ自体が旧 DB とモデルで食い違う場合は、別途差分マイグレーションを
> 追加する（`init_master` 以降に積み増す）。

---

## ディレクトリ構成

```
migrations/
  alembic.ini          # Alembic ロガー設定
  env.py               # Flask アプリと SQLAlchemy を繋ぐ実行環境
  script.py.mako       # マイグレーションファイルのテンプレート
  versions/            # 各リビジョンのマイグレーションスクリプト
    init_master.py     # ← 現行ベースライン（全テーブル）
    <revision_id>_<description>.py   # 以降の追加リビジョン
```

---

## 基本コマンド

### マイグレーション適用

```bash
# 最新リビジョンまで適用
flask db upgrade

# 特定リビジョンまで適用
flask db upgrade <revision_id>
```

### ロールバック

```bash
# 1つ前のリビジョンに戻す
flask db downgrade

# 特定リビジョンまで戻す
flask db downgrade <revision_id>

# ベース（init_master の手前＝全テーブル削除）まで戻す
flask db downgrade base
```

### 現在の状態確認

```bash
# 現在適用済みリビジョンを確認
flask db current

# リビジョン履歴を表示
flask db history
```

### 新規マイグレーション作成

```bash
# モデルとの差分から自動生成
flask db migrate -m "add_xxx_table"

# 空ファイルを生成（手書き用）
flask db revision -m "add_xxx_table"
```

---

## マイグレーションファイルの規則

### ファイル名

```
<revision_id>_<description>.py
```

`revision_id` は Alembic が自動生成する 12 桁の hex 文字列。`description` はスネークケースで変更内容を端的に表す。

### 必須事項

```python
from __future__ import annotations  # ← 先頭に必ず記述

from alembic import op
import sqlalchemy as sa

revision = "xxxxxxxxxxxxxxxx"
down_revision = "yyyyyyyyyyyyyyyy"  # 直前のリビジョン ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    # スキーマ変更を記述
    ...


def downgrade() -> None:
    # upgrade() の逆操作を必ず実装する
    ...
```

- `from __future__ import annotations` を必ず先頭に書く。
- `upgrade()` と `downgrade()` の両方を実装する。`pass` のみの `downgrade()` は原則禁止（マージ用リビジョンは例外）。
- `ALTER TABLE` / `CREATE TABLE` を直接 DB に発行することは禁止。必ずマイグレーションスクリプト経由で行う。

### データ操作を含む場合

DDL と DML を同一トランザクションで混在させる場合は `op.get_bind()` を使う。

```python
def upgrade() -> None:
    op.create_table("example", ...)

    conn = op.get_bind()
    conn.execute(sa.text("INSERT INTO example (code) VALUES (:code)"), {"code": "value"})
```

---

## ブランチ（複数ヘッド）が生じた場合

並行開発でリビジョンツリーが分岐すると `flask db upgrade` が失敗する。以下の手順でマージする。

```bash
# 現在のヘッド一覧を確認
flask db heads

# マージリビジョンを生成
flask db merge -m "merge_heads" <rev_id_1> <rev_id_2> ...

# 生成されたファイルを確認してから適用
flask db upgrade
```

マージリビジョンは `upgrade()` / `downgrade()` ともに `pass` のみで構わない。

---

## 自動生成の注意点

`flask db migrate` の自動生成は**完璧ではない**。生成後に必ず以下を確認する。

| 確認項目 | 理由 |
|---|---|
| カラム型の差分が正しいか | SQLAlchemy の型と DB の型が常に 1:1 対応しない |
| インデックス・制約の過不足 | 自動検出されないケースがある |
| `downgrade()` の逆操作が正しいか | 自動生成は不正確なことがある |
| データ移行が必要な箇所 | DDL のみ生成されるためデータ変換は手書き |

---

## テンプレート（script.py.mako）

`flask db revision` / `flask db migrate` 実行時に `script.py.mako` をもとにファイルが生成される。テンプレートを直接編集する必要はない。

---

## env.py の役割

Flask アプリのコンテキスト内で SQLAlchemy エンジンを取得し、Alembic に渡す。`flask db` コマンド経由で実行されるため、直接呼び出す必要はない。スキーマ変更が検出されない場合（差分なし）は自動的にファイル生成をスキップする。
