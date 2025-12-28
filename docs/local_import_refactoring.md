# Local Import リファクタリング設計書

## 概要

local import処理をDDD（ドメイン駆動設計）の原則に沿ってMECE（漏れなく重複なく）構造にリファクタリングしました。

## 設計目標

1. **責務の明確な分離**：各層が明確な責務を持つ
2. **テスト容易性の向上**：依存性注入により単体テスト可能に
3. **保守性の向上**：変更の影響範囲を最小化
4. **拡張性の向上**：新機能追加が容易に

---

## アーキテクチャ概要

```
┌─────────────────────────────────────────────┐
│        Presentation Layer (Celery Tasks)    │
│            cli/src/celery/tasks.py          │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│          Application Layer                   │
│  - Use Cases (ユースケース調整)             │
│  - Services (トランザクション管理)           │
│  - DTOs (データ転送オブジェクト)             │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│            Domain Layer                      │
│  - Value Objects (値オブジェクト)            │
│  - Domain Services (ビジネスロジック)        │
│  - Specifications (仕様パターン)             │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│        Infrastructure Layer                  │
│  - Repositories (永続化)                     │
│  - Storage (ファイル操作)                    │
│  - External Services (外部連携)              │
└──────────────────────────────────────────────┘
```

---

## ディレクトリ構造

```
features/photonest/
├── domain/local_import/              # Domain層（純粋なビジネスロジック）
│   ├── value_objects/                # 値オブジェクト
│   │   ├── file_hash.py             # ファイルハッシュ（SHA-256, pHash）
│   │   ├── import_status.py         # インポート状態（Enum）
│   │   └── relative_path.py         # 安全な相対パス
│   ├── services/                     # ドメインサービス
│   │   ├── duplicate_checker.py     # 重複チェックロジック
│   │   └── path_calculator.py       # パス計算ロジック
│   └── specifications/               # 仕様パターン
│       └── media_match_spec.py      # メディア一致判定仕様
│
├── application/local_import/          # Application層（ユースケース）
│   ├── use_cases/                    # ユースケース
│   │   └── (TODO: orchestrator実装)
│   ├── services/                     # アプリケーションサービス
│   │   ├── transaction_manager.py   # トランザクション境界管理
│   │   └── file_processor.py        # ファイル処理調整
│   └── dto/                          # データ転送オブジェクト
│       └── import_result_dto.py     # 処理結果DTO
│
└── infrastructure/local_import/       # Infrastructure層（技術詳細）
    ├── repositories/                 # リポジトリ実装
    │   └── media_repository.py      # Media永続化
    └── storage/                      # ストレージ実装
        ├── file_mover.py            # ファイル移動
        └── metadata_extractor.py    # メタデータ抽出
```

---

## 各層の責務

### Domain層（純粋なビジネスロジック）

**特徴**：
- フレームワーク・DB・IOへの依存ゼロ
- ユビキタス言語を用いた命名
- 不変性を重視

**主要コンポーネント**：

#### 1. Value Objects（値オブジェクト）

- **FileHash**：ファイルのハッシュ値（SHA-256 + pHash）
  - 値による等価性
  - バリデーション機能
  - 一致判定メソッド（暗号学的/知覚的）

- **ImportStatus**：インポート状態（Enum）
  - `ENQUEUED`, `IMPORTING`, `IMPORTED`, `DUPLICATE`, `ERROR`, `CANCELLED`
  - 状態判定メソッド（終端状態か、成功か、エラーか）

- **RelativePath**：安全な相対パス
  - パストラバーサル攻撃の防止
  - 正規化機能
  - パス操作メソッド

#### 2. Domain Services（ドメインサービス）

- **MediaDuplicateChecker**：重複チェック
  - ビジネスルール：優先度付き一致判定
    1. pHash + 解像度 + 撮影日時 + 動画長
    2. pHash + 動画長（撮影日時・解像度不一致）
    3. SHA-256 + サイズ
  
- **PathCalculator**：パス計算
  - 撮影日時ベースのディレクトリ階層決定
  - ファイル名生成規則: `YYYYMMDD_HHMMSS_src_hash8.ext`

#### 3. Specifications（仕様パターン）

- AND/OR/NOT による複雑な条件の組み立て
- 再利用可能な一致判定ロジック

---

### Application層（ユースケース調整）

**特徴**：
- ユースケースの実行制御
- トランザクション境界の管理
- ドメイン層とインフラ層の連携

**主要コンポーネント**：

#### 1. Services（アプリケーションサービス）

- **TransactionManager**：トランザクション管理
  - コミット/ロールバック
  - エラー時の詳細ログ記録
  - コンテキストマネージャによる境界制御

- **FileProcessor**：ファイル処理調整
  - メタデータ抽出 → 重複チェック → ファイル移動 → DB保存の連携
  - エラーハンドリングとロギング

#### 2. DTOs（データ転送オブジェクト）

- **ImportResultDTO**：全体処理結果
  - カウント情報（成功/重複/エラー）
  - エラー情報
  - 辞書変換メソッド

- **FileImportDTO**：単一ファイル処理結果

---

### Infrastructure層（技術実装）

**特徴**：
- 外部システム（DB、ファイルシステム）との接続
- ドメイン層のインターフェースを実装
- 技術的な詳細を隠蔽

**主要コンポーネント**：

#### 1. Repositories（リポジトリ）

- **MediaRepositoryImpl**：Media永続化
  - 重複検索クエリの実装
  - ORMモデルとドメインオブジェクトの変換

#### 2. Storage（ストレージ）

- **FileMover**：ファイル移動
  - アトミックな移動
  - フォールバック（コピー＋削除）
  - ディレクトリ自動作成

- **MetadataExtractor**：メタデータ抽出
  - ファイルハッシュ計算
  - EXIF/動画メタデータ抽出
  - 日時の正規化

---

## 設計原則の適用

### 1. DDD原則

✅ **ユビキタス言語**
- ビジネス用語をそのまま型名・メソッド名に
- 例：`MediaDuplicateChecker`, `ImportStatus`, `FileHash`

✅ **境界づけられたコンテキスト**
- local_import は独立したコンテキスト
- 外部との通信はDTOを介する

✅ **集約と不変条件**
- 値オブジェクトは不変
- エンティティの変更は集約ルート経由

✅ **レイヤードアーキテクチャ**
- 依存方向は一方向：Presentation → Application → Domain
- Infrastructure は Domain に依存しない（インターフェース経由）

### 2. SOLID原則

✅ **SRP（単一責任原則）**
- 各クラスは1つの責務のみ
- 例：`FileMover`はファイル操作のみ、`TransactionManager`はトランザクション管理のみ

✅ **OCP（開放閉鎖原則）**
- 新機能追加は既存コードを変更せずに可能
- 例：新しい重複チェックロジックは`Specification`を追加するだけ

✅ **LSP（リスコフの置換原則）**
- インターフェース（Protocol）による抽象化
- テスト時に実装を簡単に置き換え可能

✅ **ISP（インターフェース分離原則）**
- 小さなインターフェース（Protocol）に分割
- 必要なメソッドのみを要求

✅ **DIP（依存性逆転原則）**
- 高レベルモジュールは低レベルモジュールに依存しない
- 両者とも抽象（Protocol）に依存

### 3. MECE（漏れなく重複なく）

✅ **責務の分離**
- ファイル操作 → `FileMover`
- メタデータ抽出 → `MetadataExtractor`
- 重複チェック → `MediaDuplicateChecker`
- パス計算 → `PathCalculator`
- トランザクション管理 → `TransactionManager`

✅ **重複の排除**
- 共通ロジックはドメインサービスに集約
- 各層で責務が明確に分離され、重複なし

---

## 利点

### 1. テスト容易性

- **単体テスト可能**：各クラスが独立してテスト可能
- **モック不要なDomain層**：純粋関数のみ、外部依存なし
- **依存注入**：テスト時に実装を簡単に置き換え

### 2. 保守性

- **変更の影響範囲が明確**：層の境界が明確
- **可読性の向上**：小さなクラスに分割、責務が明確
- **バグの特定が容易**：どの層で問題が発生したか特定しやすい

### 3. 拡張性

- **新機能追加が容易**：既存コードを変更せずに拡張可能
- **仕様変更に強い**：ビジネスロジックがDomain層に集約

---

## 次のステップ

### 短期

1. ✅ Domain層の実装完了
2. ✅ Application層の実装完了
3. ✅ Infrastructure層の実装完了
4. ⏳ 既存コード（`core/tasks/local_import.py`）から新構造への移行
5. ⏳ テストの修正と実行

### 中期

1. UseCaseの完全実装
2. Presentation層（Celeryタスク）の整理
3. エラーハンドリングの強化
4. ログ出力の統一

### 長期

1. 他のモジュールへのDDD適用
2. イベント駆動アーキテクチャの導入
3. CQRSパターンの検討

---

## リファクタリングの実施ガイド

### 段階的移行

1. **Phase 1**：新構造の実装（完了）
2. **Phase 2**：既存コードから新構造へのアダプター作成
3. **Phase 3**：テストの修正
4. **Phase 4**：既存コードの段階的置き換え
5. **Phase 5**：旧コードの削除

### 注意点

- **下位互換性の維持**：既存のAPIインターフェースは変更しない
- **段階的リリース**：一度にすべてを変更しない
- **テストカバレッジの維持**：リファクタリング中もテストが通る状態を保つ

---

## 参考資料

- [AGENTS.md](../../AGENTS.md) - プロジェクト共通ルール
- [requirements.md](../../requirements.md) - システム要件定義
- Eric Evans著『ドメイン駆動設計』
- Vaughn Vernon著『実践ドメイン駆動設計』
