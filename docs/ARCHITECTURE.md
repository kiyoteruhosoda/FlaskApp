# nolumia アーキテクチャガイド

家族向け写真・動画管理プラットフォーム。DDD（ドメイン駆動設計）・SOLID原則・レイヤードアーキテクチャを基盤とする。

---

## 1. システム概要

### 技術スタック

| コンポーネント | 技術 |
|---|---|
| バックエンド | Python / Flask |
| フロントエンド | React SPA（Vite + Redux + react-router） |
| データベース | MariaDB 10.11 |
| タスクキュー | Celery（Broker: Redis） |
| コンテナ | Docker / Docker Compose |

### 主要機能

- Google Photos 複数アカウント同期（差分取得・レジューム対応）
- ローカルファイルインポート（重複検出・DDD構造）
- 動画変換（FFmpeg、H.264/AAC、最大1080p）
- サムネイル生成（256 / 1024 / 2048px）
- アルバム管理・タグ管理・全文検索
- ロール・権限による多段アクセス制御
- TOTP 二要素認証・パスキー（WebAuthn）対応

---

## 2. DDDレイヤードアーキテクチャ

すべてのドメイン機能はこの4層構造に従う。依存方向は上から下の一方向のみ。

```
┌─────────────────────────────────────┐
│  Presentation Layer                  │  Flask Blueprint / API / Celery Tasks
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Application Layer                   │  Use Cases / Services / DTOs
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Domain Layer                        │  Value Objects / Domain Services / Specs
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Infrastructure Layer                │  Repositories / Storage / External APIs
└─────────────────────────────────────┘
```

### 各層の責務

| 層 | 責務 | 禁止事項 |
|---|---|---|
| Presentation | HTTPリクエスト受付・レスポンス整形・Celeryタスク起動 | ビジネスロジック |
| Application | ユースケース調整・トランザクション境界・DTO変換 | ドメインルール直接実装 |
| Domain | ビジネスロジック・値オブジェクト・仕様パターン | フレームワーク・DB依存 |
| Infrastructure | DB永続化・ファイル操作・外部API連携 | ビジネスロジック |

### ディレクトリ構造

```
bounded_contexts/          # bounded_contexts ごとに独立
  storage/
    domain/
    application/
    infrastructure/

features/photonest/        # メイン機能
  domain/local_import/
    value_objects/         # FileHash, ImportStatus, RelativePath
    services/              # MediaDuplicateChecker, PathCalculator
    specifications/        # 仕様パターン（AND/OR/NOT 組み合わせ）
  application/local_import/
    use_cases/
    services/              # TransactionManager, FileProcessor
    dto/                   # ImportResultDTO, FileImportDTO
  infrastructure/local_import/
    repositories/          # MediaRepositoryImpl
    storage/               # FileMover, MetadataExtractor

core/                      # 横断的関心事（設定・ロギング等）
shared/                    # 共有ユーティリティ
```

---

## 3. メールモジュール（Strategy + DI パターンの実装例）

メール送信をDDDに基づいて分離し、SMTP / Console を設定で切り替え可能にした設計。

### レイヤー構成

| Layer | コンポーネント |
|---|---|
| Application | `application.email_service.EmailService` |
| Domain | `domain.email_sender.IEmailSender`（抽象）、`EmailMessage`（値オブジェクト） |
| Infrastructure | `SmtpEmailSender`、`ConsoleEmailSender`、`EmailSenderFactory` |

### インターフェースと値オブジェクト

```python
class IEmailSender(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> bool: ...

    @abstractmethod
    def validate_config(self) -> bool: ...

@dataclass(frozen=True)
class EmailMessage:
    to: List[str]
    subject: str
    body: str
    html_body: Optional[str] = None
    from_address: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    reply_to: Optional[str] = None
```

### ファクトリと環境設定

```env
MAIL_PROVIDER=smtp          # smtp または console（テスト用）
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@example.com
```

新しいプロバイダー（例: SendGrid）を追加する場合：
1. `infrastructure/email_sender/` に `IEmailSender` 実装クラスを追加
2. `EmailSenderFactory` に分岐を追加
3. `.env` に `MAIL_PROVIDER=api` など追加

---

## 4. ローカルインポート設計

### 重複判定ルール（優先度順）

1. pHash + 解像度 + 撮影日時 + 動画長 → 完全一致
2. pHash + 動画長（撮影日時・解像度が微妙に異なるケース）
3. SHA-256 + ファイルサイズ → 暗号学的同一ファイル

### ファイル名規則

```
YYYYMMDD_HHMMSS_src_hash8.ext
例: 20250101_123456_local_a1b2c3d4.jpg
```

`src` は `gphotos`（Google Photos）/ `local`（ローカル取込）/ `cam`（カメラ直接）

### 状態遷移

セッション・アイテムそれぞれに状態機械を持ち、不正遷移を防止する。

```
セッション: PENDING → RUNNING → COMPLETED / FAILED / CANCELLED
アイテム:   ENQUEUED → IMPORTING → IMPORTED / DUPLICATE / ERROR / CANCELLED
```

### スケーラビリティ対応

大量ファイル（10万件以上）処理時の DB 肥大化を防ぐため：

- 監査ログの `details` JSON は **900KB 上限** で自動切り詰め
- 配列が10件超の場合は先頭5件＋末尾5件のみ保存
- エラーは件数・タイプ別サマリーのみ保存（全メッセージは保存しない）

```python
MAX_DETAILS_SIZE_BYTES = 900_000
MAX_ACTIONS_COUNT = 50
MAX_ARRAY_ITEMS = 10
```

---

## 5. 設計原則

### SOLID

| 原則 | 適用例 |
|---|---|
| SRP | `FileMover`はファイル操作のみ、`TransactionManager`はトランザクション管理のみ |
| OCP | 新重複チェックロジックは `Specification` 追加のみ、既存コード不変 |
| LSP | `Protocol` による抽象化でテスト時に実装を差し替え可能 |
| ISP | 小さな `Protocol` に分割し、必要なメソッドのみ要求 |
| DIP | 上位レイヤーは抽象（`Protocol`）に依存、具体実装は Infrastructure 層 |

### ユビキタス言語

ビジネス用語をそのまま型名・メソッド名に使用する。

- 良い例: `MediaDuplicateChecker`, `ImportStatus`, `FileHash`, `AlbumItem`
- 避ける例: `Manager`, `Helper`, `Util`, `Data`

---

## 6. 命名規則

### データベース・モデル

- テーブル名: **単数形** (`user`, `media`, `album`, `tag`)
- 中間テーブル: 2テーブル名を単数形で結合（`user_roles`, `media_tag`, `album_item`）

### URL・エンドポイント

- RESTful API リソース名: **単数形**
  - `GET /admin/user` — 一覧
  - `GET /admin/user/<id>` — 個別
  - `POST /admin/user` — 作成
  - `PUT /admin/user/<id>` — 更新
  - `DELETE /admin/user/<id>` — 削除

### Python

- 個別オブジェクト: `user`（単数）
- コレクション: `users`、`user_list`
- カウント: `user_count`

### JavaScript / TypeScript

- camelCase: `userId`, `userList`, `editUser()`

---

## 7. テスト戦略

### マーカー分類（pytest）

```toml
[tool.pytest.ini_options]
markers = [
    "unit: 外部依存のない高速なユニットテスト",
    "integration: DB・ファイルシステムを使う統合テスト",
    "ffmpeg: FFmpegが必要なテスト（デフォルトでスキップ）",
    "filesystem: 実ファイルシステムアクセスが必要なテスト（デフォルトでスキップ）",
    "smtp: SMTPサーバーが必要なテスト（デフォルトでスキップ）",
]
# デフォルトで外部依存テストをスキップ
addopts = ["-v", "--strict-markers", "-m", "not (ffmpeg or filesystem or smtp)"]
```

### 実行コマンド

```bash
# デフォルト（unit + integration のみ）
pytest

# 特定カテゴリのみ
pytest -m unit
pytest -m integration

# 全テスト（FFmpeg等が必要）
pytest -m ""

# 特定ファイル
pytest tests/domain/email_sender/ -v
```

### Domain層テストの原則

Domain層は外部依存ゼロなので、モック不要で単体テスト可能。
Infrastructure層はリポジトリインターフェースを通じて差し替える。

---

## 8. バージョン管理

バージョンは `core/version.json`（Dockerビルド時自動生成）から読み込む。

```bash
# バージョンファイル生成（開発環境）
./scripts/generate_version.sh

# バージョン確認（CLI）
flask version

# バージョン確認（API）
GET /api/version
```

バージョン文字列形式:
- mainブランチ: `v{コミットハッシュ}` (例: `va0b7e23`)
- その他: `v{コミットハッシュ}-{ブランチ名}` (例: `va0b7e23-feature`)

本番環境では `core/version.json` が存在すれば Git 不要。
