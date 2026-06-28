# DB モデル定義のルール（このディレクトリ）

SQLAlchemy モデルを編集するときは以下を厳守する（全体方針はリポジトリ直下の `CLAUDE.md` 参照）。

- **DB ネイティブ ENUM を使わない。** `Enum(...)` には必ず `native_enum=False` を付ける
  （MariaDB の `ENUM` は値追加に `ALTER TABLE` が必要で運用と噛み合わない）。
  代替として `String` + 許可値の定数管理でもよい。
- `BigInteger` 主キーは `sa.BigInteger().with_variant(sa.Integer(), "sqlite")`。
- モデル変更時は必ず Alembic マイグレーションを追加する。乖離は
  `tests/integration/test_migration_model_consistency.py` が検出する。
- マスタデータの値は `shared/domain/auth/master_data.py` を唯一の出所とする。
