# ADR-0002: DB ネイティブ ENUM を使わない（native_enum=False）

- ステータス: Accepted
- 日付: 2026-06-28

## コンテキスト

「Enum 禁止・String を使う」という慣習がマイグレーションのコメントにのみ存在し、
CLAUDE.md に明文化されていなかったため、モデルでは `Enum` が多用され慣習と乖離して
いた（`local_import_audit_log` は旧マイグレが String、モデルは Enum という矛盾もあった）。

MariaDB のネイティブ `ENUM` は、値追加に `ALTER TABLE` が必要で DDL 運用と噛み合わず、
内部序数の変更でデータが壊れやすく、ORM ラベルと DB 値がズレやすい。

## 決定

DB ネイティブ ENUM カラムを使わない。SQLAlchemy の `Enum(...)` を使う場合は必ず
`native_enum=False`（全バックエンドで CHECK 制約付き VARCHAR になる）を指定する。
あるいは `String` + 許可値の定数管理とする。Python 側の列挙そのものは禁止しない。

## 選択肢と理由

- 案A（採用）: `native_enum=False`。型安全（許可値の集中管理）を保ったまま、
  MariaDB ENUM の運用上の弊害を回避できる。SQLite テストとも整合。
- 案B: 完全に `String` 化し許可値を別途定数管理。型安全が弱まり冗長。
- 案C: ネイティブ ENUM 継続。値追加のたびに ALTER が必要で却下。

## 影響

- 全モデルの `Enum(...)` 14 箇所に `native_enum=False` を付与し init_master を再生成。
- ルールを CLAUDE.md「DB モデリング」節とモデル定義ディレクトリのネスト CLAUDE.md に明記。
