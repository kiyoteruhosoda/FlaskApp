# ADR-0001: マイグレーション履歴を単一ベースラインに統合

- ステータス: Accepted
- 日付: 2026-06-28

## コンテキスト

`migrations/versions/` の旧リビジョン群に以下の不整合があり `flask db upgrade` が
通らなかった。

- ベースが 2 つ（`31b1901dba43` と孤立した `local_import_audit_log`）。
- ヘッドが 3 つ。`local_import_audit_log` テーブルを 2 リビジョンが重複定義。
- モデルには存在するが履歴に作成処理が無いテーブル（`certificate_events`,
  `certificate_private_keys` 等）があり、モデルとマイグレーションが乖離していた。

## 決定

現行の SQLAlchemy モデル `db.metadata` から全テーブルを機械生成した単一ベースライン
`migrations/versions/init_master.py`（`down_revision = None`）に統合し、旧リビジョン
33 本を削除する。マスタデータは別リビジョン（seed）へ分離する。

## 選択肢と理由

- 案A（採用）: モデルから init_master を生成し履歴を置換。空 DB 適用結果が
  `db.create_all()` と完全一致することを検証でき、乖離を一掃できる。
- 案B: 旧履歴のヘッド/ベースを merge して修復。重複テーブル定義とモデル乖離は
  残るため、不整合の根治にならない。

## 影響

- 新規 DB は `flask db upgrade` で即構築可。
- 既存（本番）DB は `flask db stamp init_master` でベースラインを付け替える。
- 再発防止に `tests/integration/test_migration_model_consistency.py` を追加。
