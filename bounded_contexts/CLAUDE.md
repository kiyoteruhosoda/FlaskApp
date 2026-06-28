# bounded_contexts のルール（DB モデル含む）

各コンテキストの `infrastructure/` に SQLAlchemy モデルを定義する際は以下を厳守する
（全体方針はリポジトリ直下の `CLAUDE.md`、DDD 構成も同ファイル参照）。

- **DB ネイティブ ENUM を使わない。** `db.Enum(...)` / `sa.Enum(...)` には必ず
  `native_enum=False` を付ける（MariaDB ENUM は値追加に `ALTER TABLE` が必要で
  DDL 運用と噛み合わない）。代替として `String` + 許可値の定数管理でもよい。
- `BigInteger` 主キーは `sa.BigInteger().with_variant(sa.Integer(), "sqlite")`。
- モデル変更時は必ず Alembic マイグレーションを追加する。乖離は
  `tests/integration/test_migration_model_consistency.py` が検出する。
- 依存方向は Presentation → Application → Domain。Infrastructure は Domain の
  インターフェースを実装する。`util` / `helper` 等の曖昧な名前を作らない。
