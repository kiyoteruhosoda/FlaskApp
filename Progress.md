# Progress — マイグレーション健全化とデータ整合性

マイグレーション整合性調査から派生したタスクの進捗管理。

凡例: ✅完了 / 🚧進行中 / ⬜未着手 / 🟡要判断（ユーザー決裁待ち）

---

## 完了

- ✅ **マイグレーション整合性の調査** — 旧 `versions/` はベース2・ヘッド3・テーブル
  重複定義・モデル乖離で `flask db upgrade` 不能だったことを特定。
- ✅ **単一ベースライン `init_master` への統合** — 現行モデル `db.metadata` から全42
  テーブルを機械生成。空 DB 適用結果が `db.create_all()` と完全一致を検証。旧
  リビジョン33本を削除し置換（base/head = 1 系統）。
- ✅ **マスタデータの分離・永続化** —
  - `shared/domain/auth/master_data.py`（ロール/権限/付与/管理者の唯一の出所）
  - `versions/2a1f9c0b3d4e_seed_master_data.py`（`flask db upgrade` で冪等投入）
  - `scripts/seed_master_data.py` をカタログ参照に統一（DRY）
  - 初期管理者パスワードを `ADMIN_INITIAL_PASSWORD` で上書き可能化
- ✅ **モデル↔マイグレーション乖離の解消＋再発防止** — 全チェーン適用後のスキーマが
  モデルと一致することを確認。回帰テスト
  `tests/integration/test_migration_model_consistency.py` を追加
  （単一ベース/ヘッド検証 + autogenerate 差分ゼロ検証 = `flask db migrate` ガード）。
- ✅ **migrations/README.md** — ベースライン運用・既存 DB の stamp 手順・seed 経路を記載。

---

## 未着手 / 要対応

- ⬜ **`media` への一意制約追加（冪等性のハード担保）** — 現状は重複判定が
  「SELECT してから INSERT」のアプリ層実装で、`hash_sha256` / `google_media_id` に
  DB 一意制約が無い。Celery 並行ワーカーで二重登録の競合リスク。
  - ローカル取り込み: `hash_sha256` に部分一意制約（`is_deleted=False` 条件付きは
    MariaDB では関数インデックス/別設計が必要 → 設計検討）。
  - Google Photos: `google_media_id` を安定キーに一意化（再エンコードで sha256 は
    変わりうるため、GP は sha256 だけでは冪等にならない）。
  - 差分マイグレーションを `2a1f9c0b3d4e` 以降に追加する。

- ✅ **Enum 方針の統一** — 方針確定（DB ネイティブ ENUM 不使用＝`native_enum=False`）。
  全モデルの `db.Enum(...)` 14 箇所に `native_enum=False` を付与し、init_master を
  再生成。CLAUDE.md に「DB モデリング」節を新設し、モデル定義ディレクトリへネスト
  CLAUDE.md を追加（コード近傍で再強調）。ドリフトテスト・seed 検証ともに緑。

- ⬜ **重複判定の二重実装の解消** — `check_duplicate_media` が新実装を try し例外で
  旧実装へサイレントフォールバック。障害が隠れるため一本化する。

- ⬜ **originals 直接再構築 CLI** — inbox は取り込み後に削除されるため、DB 初期化後の
  メタデータ再生成は手作業。`MEDIA_ORIGINALS_DIRECTORY` を直接走査して再登録する
  CLI（冪等）を用意すると運用が安定。

- ⬜ **初期管理者のセキュリティ強化** — env 上書きは対応済み。さらに初回ログイン時の
  パスワード強制変更フローがあると堅い。

- ⬜ **CI への drift テスト組み込み** — `tests/integration/test_migration_model_consistency.py`
  を CI で必須実行にする（ローカルでは追加済み）。

---

## メモ: Enum ルールの妥当性（要判断材料）

「Enum 禁止・String を使う」は**部分的に妥当**。論点を以下に整理（詳細は会話ログ）。

- MariaDB の `ENUM` は値追加に `ALTER TABLE` が必要で DDL 運用ルールと噛み合いにくい、
  値の順序変更が壊れやすい、ORM/DB 間の値ズレが起きやすい、という実害がある。
- 一方、SQLAlchemy の `Enum(...)` は **`native_enum=False` で CHECK 制約付き VARCHAR**
  として扱え、Python 側の型安全（許可値の集中管理）を保ったまま MariaDB ENUM の
  欠点を回避できる。「`Enum` 型そのものの禁止」ではなく「**ネイティブ ENUM カラムの
  禁止**」とするのがより正確で実用的。
- 推奨: ルールを「DB ネイティブ ENUM を使わない（`native_enum=False` か String + 値の
  定数管理）」に改訂し、既存モデルを段階移行。
