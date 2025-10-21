# AGENTS.md

本ドキュメントは、開発における共通ルール・設計指針・システム要件を定義します。
目的は **重複ロジックの排除**、**可読性・保守性の確保**、**責務分離**、**安定したテスト**、および **国際化対応の統一** です。

---

## ⚙️ システム要件

### 1. 権限（Permission / Role）管理

* 権限は **コード値（Scope名）** によって一意に識別する。
* ユーザーは複数のロール（Role）を保持可能。
* ロールには1つ以上の権限（Permission）が紐づく。
* 有効な権限は「ユーザーの全ロールに含まれる権限の和集合」として算出する。
* アクセストークン（JWT）発行時の `scope` は、ユーザーが保有する権限の範囲内で指定可能。
* スコープが未指定または空の場合、デフォルトは「権限なし」とする。
* 権限検証は **Application 層** で行い、**Presentation 層** には結果のみ渡す。
* 各リソースアクセスに対して、`@require_perms("scope_name")` 形式のデコレータを利用。
* ロールでの認可は行わない、必ず権限（scope）を使うこと。

---

### 2. 言語リソース（国際化対応）

* 翻訳は **gettext 形式のリソースファイル (`messages.po`)** を使用する。
* デフォルト言語は **英語（en）**。
* 日本語（ja）用の `messages.po` を別途作成する。
* `.mo` ファイル（コンパイル済みバイナリ）は **生成しない**。

  * 理由：軽量なホットリロード対応を優先し、`.po` を直接読み込む運用とする。
* 翻訳ファイル配置構成：

  ```
  /webapp
    /translations
      /en/LC_MESSAGES/messages.po
      /ja/LC_MESSAGES/messages.po
  ```
* 新規メッセージは英語で定義し、それを翻訳キーとして扱う。
* 日本語訳は `ja/messages.po` に手動で追記する。
* Flask-Babel などを利用する場合も `.mo` 生成は禁止。開発環境・本番環境とも `.po` のみを読み込む設定とする。

---

### 3. データベーススキーマ変更（DDL管理）

* すべての DDL 変更は **手動で SQL を直接編集せず、Alembic マイグレーションスクリプト (`.py`) を作成** する。
* マイグレーションファイルは `migrations/versions/` 以下に配置する。
* 命名規則：

  ```
  migrations/versions/<revision_id>_<short_description>.py
  ```

  例：

  ```
  migrations/versions/cc5f8f58c7d4_add_totp_credentials_table.py
  ```
* 各マイグレーションファイルには以下を明記：

  * **revision**：UUID または自動採番（`alembic revision -m`）
  * **down_revision**：直前の revision ID
  * **upgrade() / downgrade()**：双方向操作を実装
* **DDLを直接変更（ALTER, CREATE）することは禁止**。

  * 理由：DBとモデル間の不整合を防止するため。
* モデル変更 → マイグレーション作成 → `flask db upgrade`（または `alembic upgrade head`）で適用。
* Alembic ヘッダ内で `from __future__ import annotations` を必ず指定。

---

### 4. 環境要件

| 項目           | バージョン／仕様                   | 備考                                  |
| ------------ | -------------------------- | ----------------------------------- |
| **Python**   | 3.11 以上                    | `python:3.11-slim` ベース              |
| **DB**       | MariaDB 10.11.x            | SQLAlchemy + Alembic による管理          |
| **ORM**      | SQLAlchemy 2.x             | Declarative Base 構文                 |
| **マイグレーション** | Alembic                    | `/migrations` 配下で統一管理               |
| **非同期処理**    | Celery + Redis             | worker / beat 構成                    |
| **Redis**    | 7.x                        | password 保護済み                       |
| **Webサーバ**   | Gunicorn                   | `--workers=2 --threads=4` 推奨        |
| **OS/ホスト**   | Linux / Synology (DSM 7.x) | Docker環境上で運用                        |
| **構成管理**     | Docker Compose             | 各サービスを独立化（web, worker, beat, redis） |

---

## 🎯 対象

* 本リポジトリ全体（アプリ／テスト／スクリプト／インフラ構成管理）

---

## 1. 基本原則（必須）

* 重複ロジックを持たない（DRY）。共通化は **ドメイン側** を優先。
* 可読性・保守性を最優先（「書く人」より「読む人」）。
* クラス責務は単一に限定し、相互に独立動作できるように設計（SRP）。
* すべてのクラスに対してテストを書く（最低ユニット、必要に応じて結合）。
* どの環境でも失敗しないテストのみを許容（時刻・並列・IO・順序依存を排除）。
* ユビキタス言語に基づく命名。ビジネス用語を **そのまま** 型／メソッド名に。

---

## 2. DDD（ドメイン駆動設計）に沿った開発

### 2.1 レイヤードアーキテクチャ

* 依存方向は一方向のみ：

  ```
  Presentation → Application → Domain
                    ↑
              Infrastructure
  ```
* Domain は純粋（フレームワーク・DB・IO依存なし）。
* Application はユースケース制御・トランザクション境界・イベント発行。
* Infrastructure は実装ディテール（DB、外部API、メッセージング、FS 等）。
* Presentation は API/UI。**ビジネスロジックを置かない**。

### 2.2 エンティティ／値オブジェクト

* **Entity**：識別子で同一性を判定（例：`User`, `Order`）。
* **Value Object**：値で等価、原則不変（例：`Money`, `EmailAddress`）。
* 値オブジェクトは `equals/hash` を値比較で実装、変更は新インスタンス。

### 2.3 集約と不変条件

* 集約は「1トランザクションで完結」できる最小単位に。
* 外部からの変更は **集約ルート** 経由のみ。
* 不変条件は集約内部で完結して守る。外部に委ねない。

### 2.4 サービスの分離

| 層                       | 目的                         | 例                                      |
| ----------------------- | -------------------------- | -------------------------------------- |
| **Domain Service**      | 複数エンティティにまたがる純粋ロジック（副作用なし） | `PaymentPolicy`, `ShippingCalculator`  |
| **Application Service** | ユースケース制御、トランザクション、イベント発行   | `OrderApplicationService.placeOrder()` |

### 2.5 リポジトリ

* 集約単位で定義。Domain には **IF のみ**、実装は Infrastructure。
* クエリ最適化は **仕様（Specification）** または **Query Model** を用いる。

### 2.6 ドメインイベント

* 重要な状態変化はイベントで表現（過去形：`OrderPlaced`）。
* 非同期処理や外部連携はイベント購読で疎結合化。
* 冪等性と再送耐性を確保（イベントID、処理記録）。

### 2.7 バウンデッドコンテキスト

* コンテキストごとに独立モデル。名称が同じでも意味が異なり得る。
* 境界越えはイベント／API契約で通信。モノリスでも論理分割を徹底。

### 2.8 実装上の注意

* Domain 層は業務例外のみ。技術例外は Infrastructure で補足・変換。
* 例外メッセージはユビキタス言語で具体的に。
* モデルは進化が前提。定期的にリファクタリングと用語整合を行う。

---

## 3. OOP（現代的アプローチ）

* SOLID を遵守。特に SRP / OCP / DIP を重視。
* 依存はコンストラクタインジェクション。new の直接使用を避ける（Factory/DI）。
* 可能な限り不変オブジェクトを採用。
* 副作用は境界で隔離（IO・時刻・乱数・スレッド）。
* 拡張に強く、変更に強すぎない構造を意識（OCP の誤用に注意）。

---

## 4. コーディング規約（抜粋）

* 命名：ドメイン語彙を用いる。略語を避け、曖昧語（util/helper）禁止。
* メソッドは「意図」が一読で伝わる長さに分割。
* 早期 return／ガード節でネスト削減。
* Null 許容は設計で最小化（Option/Result パターン等）。
* ログは構造化（キー＝値）。PII/機密は出力禁止。
* コメントは **なぜ** を書く（**何を** はコードで表現）。

---

## 5. テスト方針

* **ピラミッド**：Unit（厚）、Integration（中）、E2E（薄）。
* Domain は純粋ユニットテストで網羅（外部依存ゼロ）。
* Application はユースケース単位の結合テスト（リポジトリはテスト実装）。
* Infrastructure は契約テスト（外部APIモック、SQLスナップショット等）。
* 不安定要因（時刻・乱数・並列・ネットワーク）は固定化／仮想化。
* テストデータは **読みやすい定義** を優先（ビルダー／Fixture／Factory）。
* **失敗を放置しない**：赤、黄のままマージ禁止。

**最低品質ゲート（例）**

* ステートメント/ブランチカバレッジ：Domain 90% / Application 80% 以上
* 新規コードは過去30日の平均カバレッジを下回らない
* テスト実行は 10 分以内、並列化とキャッシュ活用

---

## 6. Git / PR ルール

* トランクベース推奨（短命ブランチ、こまめに統合）。
* 1 PR = 1 目的。大規模変更は論理単位で分割。
* PR テンプレート（変更目的／設計意図／影響範囲／テスト観点／リスク）。
* レビューは **設計の一貫性** と **ドメイン語彙** を最優先。
* レビューチェックリスト（後述）に準拠。
* Rebase を基本、衝突は作成者が解消。

---

## 7. CI/CD

* すべての PR で：lint／型検査／ユニット＆結合テスト／脆弱性スキャン。
* main へのマージで自動デプロイ（環境に応じたガード：手動承認・段階ロールアウト）。
* 成果物はリリースノートとアーティファクトを保存。
* フィーチャーフラグで段階的提供・容易なロールバック。

---

## 8. 例外・エラーハンドリング／ロギング

* 例外は境界で変換して上位にドメイン文脈を伝える。
* ログはレベル運用（Domain：DEBUG/INFO 低頻度、Infra：WARN/ERROR 重点）。
* 追跡性：相関ID／リクエストIDをスレッドローカル等で引き回し。
* セキュリティ上の機微情報はマスク。

### ログ出力方針


* すべてのログは 構造化（JSON形式） で出力し、
「あとから追える」完全な監査・分析が可能な形でDBに保存する。

* 出力経路は アプリ用 (log テーブル) と Celeryワーカー用 (worker_log テーブル) に分離。

* ログはリアルタイム出力（stdout, ファイル）と同時にDBへ非同期書き込みされる。

* 各ログレコードには共通の識別子（requestId または taskId）を持たせ、
Webリクエスト・Celeryジョブ・DB操作を横断的に関連付けられるようにする。

| コンポーネント              | 出力先テーブル                       | 役割            | 追跡キー        | 備考            |
| -------------------- | ----------------------------- | ------------- | ----------- | ------------- |
| Flask / API アプリ      | `appdb.log`                   | API入力・認証・例外など | `requestId` | リクエスト単位で一意    |
| Celery Worker / Beat | `appdb.worker_log`            | タスク開始・完了・エラー  | `taskId`    | バックグラウンドジョブ単位 |
| DB監査ログ               | `appdb.certificate_events`（例） | セキュリティ／証明書操作  | `event_id`  | 任意テーブル名可      |



#### 追跡方法（後追い分析）

アプリ・ワーカーいずれも共通ID（requestId / taskId）で追跡できるようにする。
これにより、
「あるAPI呼び出し → それがキュー投入したCeleryタスク → 生成された成果物」
というフローをDBログから一気通貫で再構成できる。


6. ベストプラクティス

UTC で一貫した時刻管理（created_at は UTC_TIMESTAMP(6)）
JSON 構造を壊さないため、アプリ側で json.dumps() して保存
traceback フィールドは NULLABLE（例外時のみ記録）

セキュリティ対策：
user.id_hash のみを保持（PII禁止）
外部リクエストログには ip と userAgent を記録


---

## 9. セキュリティ

* 依存性は自動スキャン＆定期更新（Renovate/Dependabot）。
* シークレットはコードに置かない（Vault/環境変数/マネージドID）。
* 入力検証・出力エンコード・最小権限。
* 監査ログ：重要操作は不可否的に記録（だれが／いつ／何を）。

---

## 10. パフォーマンス／スケーラビリティ

* 設計段階で SLA/SLI/SLO を明確化。
* N+1 の検出と防止（リポジトリ層で集約最適化）。
* キャッシュは整合性戦略を明示（TTL/無効化条件/キー設計）。
* ベンチの再現性を確保（固定データ・同一環境）。

---

## 11. ドキュメント

* アーキテクチャ決定記録（ADR）を運用。
* ドメイン用語集（ユビキタス言語）を維持。
* 公開 API はスキーマ駆動（OpenAPI/JSON Schema）で契約テスト。

---

## 12. ディレクトリ標準（例）

```
/src
  /presentation      # API/UI（Thin）
  /application       # UseCase, Tx, Event dispatcher
  /domain            # Entity, VO, Domain Service, Repository IF, Events
  /infrastructure    # Repository impl, Clients, DB, FS, Messaging
/tests
  /unit              # Domain 中心の純ユニット
  /integration       # Application/Infra の結合
  /e2e               # 最小限のE2E
/docs                # ADR, 用語集, 設計補足
```

---

## 13. レビュー・チェックリスト（抜粋）

* [ ] 目的とスコープが PR 説明で明確か
* [ ] ドメイン語彙で命名されているか（UI/技術語で上書きされていないか）
* [ ] 責務は単一か（1クラス・1メソッドの意図が明確か）
* [ ] 依存方向が規約通りか（Presentation→Application→Domain、Infra は下位）
* [ ] 例外・ログ・監査に抜けがないか（機微情報なし）
* [ ] テストは意図（振る舞い）を検証しているか（モック過多でないか）
* [ ] どの環境でも安定して通るか（時刻/並列/IO 非依存）
* [ ] パフォーマンス退行・N+1 の兆候がないか
* [ ] ドキュメント（ADR/スキーマ）の更新が必要なら含まれているか

---

## 14. Definition of Done

* ドメイン観点での受け入れ条件を満たす
* レイヤ規約と命名規約に適合
* テスト（自動）とカバレッジ基準を満たす
* セキュリティ／監査観点の確認済み
* ドキュメント（ADR/用語集/APIスキーマ）が更新済み
* CI/CD が成功し、レビュー承認済み

---

## 15. アンチパターン（禁止）

* Fat Controller／Fat Service（UI や Application にビジネスロジックを寄せる）
* ドメインからインフラ依存を直接参照
* 「便利クラス」「Utils」「Helper」の乱造
* 魔法の DI 設定（依存が不透明）
* テストのための条件分岐（本番コードの if test）
* 環境依存・順序依存テスト、時刻に依存するアサート

---

## 16. 成果物（出力形式）

1. リファクタ後のコード（対象クラス／メソッド明示）
2. 分離したクラスごとの **単体テスト**（モック／スタブの使用方針を記述）
3. 適用した原則や改善点（箇条書きで根拠を明示）
4. 既存テストの修正／追加（失敗テストの原因と対策を記述）

---

以下のように **「17. API設計と実装（Flask-Smorest＋Marshmallow）」** セクションを追加するのが最も自然です。
既存の DDD／テスト／セキュリティ原則と整合する形で、「どこまでをPresentation層に置くか」「Schemaの責務」「ドキュメント生成との統合」などを明示しています。

---

## 17. API設計と実装（Flask-Smorest + Marshmallow）

* **APIフレームワーク**は Flask-Smorest を使用し、
  各エンドポイントは Flask-Smorest の `Blueprint` として Presentation 層に実装する。

* **リクエスト／レスポンス構造**はすべて Marshmallow の `Schema` クラスで定義し、
  Application 層・Domain 層へは **バリデーション済みの純粋データ（dict）** のみを渡す。

* **Swagger UI**（/api/docs）は Flask-Smorest の OpenAPI 自動生成機能により構築し、
  `@bp.arguments()` および `@bp.response()` デコレータから仕様を抽出する。

### 設計方針

| 項目                 | 指針                                                                                      |
| ------------------ | --------------------------------------------------------------------------------------- |
| **責務分離**           | Presentation 層にのみ Flask-Smorest / Marshmallow を配置し、Domain 層へは依存させない。                    |
| **Schema命名規則**     | `〇〇RequestSchema`（入力用）、`〇〇ResponseSchema`（出力用）を基本とする。                                   |
| **Validation**     | Marshmallow により型・必須項目・値範囲を明示。`required=True` と `validate` パラメータを積極利用。                   |
| **Error Handling** | Marshmallow のバリデーション例外は自動的に HTTP 400 として処理される。独自メッセージが必要な場合は Flask-Smorest のエラーハンドラを拡張。 |
| **ドキュメント**         | `description` や `metadata` を Schema フィールドに付与し、Swagger UI の説明欄に反映させる。                    |
| **型安全性**           | Schema から直接 Domain モデルを生成せず、Application 層で明示的に変換（Mapper／Assembler パターン推奨）。              |
| **ユニットテスト**        | Schema 単体でのバリデーションテストを必ず実施し、想定外入力での失敗を確認。                                               |

### 実装例（最小構成）

```python
from flask_smorest import Blueprint
from marshmallow import Schema, fields

bp = Blueprint("auth", __name__, url_prefix="/api")

class LoginRequestSchema(Schema):
    username = fields.String(required=True, description="ユーザー名")
    password = fields.String(required=True, description="パスワード")

class LoginResponseSchema(Schema):
    access_token = fields.String(required=True)
    refresh_token = fields.String(required=True)

@bp.post("/login")
@bp.arguments(LoginRequestSchema)
@bp.response(200, LoginResponseSchema)
def login(data):
    """ユーザーログインAPI"""
    # Application層のユースケースを呼び出す
    result = login_usecase.execute(data)
    return result
```

### 運用上の考慮事項

* **Blueprint単位でAPIグループを整理**し、`features/<domain>/presentation/routes.py` に配置。
* **SchemaはDomain単位でまとめる**（例：`features/<domain>/domain/schemas.py`）。
* Schema 定義が長大化する場合、`Nested` フィールドで構造を分割し再利用性を高める。
* 国際化が必要なレスポンスメッセージは Presentation 層で `_()` により翻訳する。

---

この章を追加すると、既存の「2. DDD」「4. コーディング規約」「11. ドキュメント」と整合しつつ、
Flask-Smorest＋Marshmallowによる **API設計の標準的ルール** が体系的に定義されます。


以下のような新セクションを **「18. 設定管理（Config）」** として追加するのが自然です。
既存の DDD・環境変数・マイグレーション方針と整合し、
「直接取得禁止（必ず Config クラス経由）」を明文化します。

---

以下のように修正版を提示します。
「Configクラス（またはSettingsクラス）の @property を必ず経由する」ことを明確に規定した文面です。

---

## 18. 設定管理（Settings）

### 原則

* **設定値は必ず `Settings` クラスの `@property` を経由して取得する。**
* 環境変数・Flask設定・DB設定などへの **直接アクセスは禁止**。
  例：
  ❌ `os.getenv("API_BASE_URL")`
  ❌ `current_app.config["DB_URL"]`
  ❌ `SystemSetting.query.get("api_base_url")`

---

### 理由

* 設定値の **取得元・型・デフォルト値を一元管理** し、参照箇所の整合性を維持するため。
* テスト時に設定をモック・スタブ化できるようにするため。
* 設定ソースを将来 Vault／外部設定サーバ等に置き換えても、呼び出し側を変更しないため。

---

### 実装指針

| 項目          | 指針                                                                                       |
| ----------- | ---------------------------------------------------------------------------------------- |
| **定義場所**    | `core/settings.py` に `class 用途名Settings`を定義。                                  |
| **アクセス経路**  | すべてのコードは `from core.settings import settings` をインポートし、<br>**`settings.py` プロパティ経由で取得**。 |
| **内部構造**    | 各設定値は `@property` で定義し、内部で環境変数・DB・デフォルト値を統合する。                                           |
| **優先順位**    | 環境変数 ＞ DB設定 ＞ デフォルト値（`system_settings_defaults.py`）                                      |
| **キャッシュ方針** | 値はプロパティ内で Lazy Load または初期化時キャッシュ。                                                        |
| **レビュー基準**  | `@property` 経由以外の設定参照は **レビューチェックリスト違反** として修正対象。                                        |

---

### 運用ルール

* 新しい設定キーを追加する場合は必ず以下を更新：

  * `core/system_settings_defaults.py`（デフォルト値）
  * `core/settings.py`（`@property` を追加）
  * `webapp/admin/system_settings_definitions.py`（管理画面項目）
* 設定値を参照するすべてのコードは **`settings.py` プロパティ経由のみ** 使用可。
* 直接アクセスを検出した場合、リファクタリング対象とする。

---



## 付録：安定テストの作法（クイックリスト）

* 時刻は `Clock`/`TimeProvider` で注入し固定化
* 乱数・UUID も Provider で注入し固定化
* 並列はテスト毎に隔離、グローバル状態禁止
* IO は Contract テスト or Test Double（メモリDB/HTTPモック）
* リトライ／バックオフはテストで無効化スイッチを用意

---

*本ドキュメントは設計・国際化・権限・マイグレーションに関する共通合意に基づき、
変更がある場合は Issue にて協議のうえ更新する。*
