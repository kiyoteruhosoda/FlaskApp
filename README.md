# nolumia

nolumia は、DDD（ドメイン駆動設計）アーキテクチャを採用した Flask ベースの家族写真管理・同期プラットフォームです。Google Photos 同期、ローカルファイルインポート、動画変換、サムネイル生成などの処理を Celery によるバックグラウンドジョブで実行します。

## 📚 ドキュメント

- **[開発ガイド](docs/DEVELOPMENT.md)** - 詳細なセットアップ、Celery、テスト実行
- **[シングルサーバ構成ガイド](docs/SINGLE_SERVER_GUIDE.md)** - 1台構成での起動手順
- **[Synology デプロイ](docs/synology-deployment.md)** - Synology NAS 専用デプロイガイド
- **[TOTP 管理ガイド](docs/totp_management.md)** - TOTP 資格情報の登録・インポート/エクスポート手順
- **[システム要件・API 仕様](docs/requirements.md)** - 技術仕様書・API/DB/UI 設計
- **[ドキュメント一覧](docs/)** - その他の設計・運用ドキュメント

## 🚀 クイックスタート

### 開発環境（ローカル）
```bash
# 1. 仮想環境作成・有効化
python -m venv .venv
source .venv/bin/activate  # Linux/Mac

# 2. 依存関係インストール
pip install --upgrade pip
pip install -r requirements.txt

# 3. 環境設定
cp .env.example .env
# .env ファイルを編集してデータベース接続情報等を設定

# 4. データベースセットアップ
flask db upgrade
flask seed-master

# 5. アプリケーション起動
python main.py
```

### 本番環境（Docker 推奨）
```bash
# 1. Docker イメージビルド
docker build -t nolumia:latest .

# 2. 環境設定
cp .env.example .env
# .env ファイルを本番環境用に編集

# 3. サービス起動
docker-compose up -d

# 4. 初期データベースセットアップ
docker-compose exec web flask db upgrade
docker-compose exec web flask seed-master
```

## 🏗️ アーキテクチャ

DDD のレイヤード/ヘキサゴナル構成を採用し、ビジネスロジックを **境界づけられたコンテキスト（bounded contexts）** に分割しています。各コンテキストは `domain` / `application` / `infrastructure`（必要に応じて `presentation` / `tasks`）の層を内包します。

```
nolumia/
├── bounded_contexts/   # 境界づけられたコンテキスト（ドメインごとの中核ロジック）
│   ├── photonest/      #   写真・メディア管理の中核ドメイン
│   ├── picker_import/  #   Google Photos ピッカー連携・インポート
│   ├── storage/        #   ストレージ抽象（ローカル/クラウド）
│   ├── email/          #   メール送信ユースケース
│   ├── email_sender/   #   メール送信の実装（SMTP 等）
│   ├── certs/          #   アクセストークン署名証明書管理
│   ├── totp/           #   TOTP（多要素認証）
│   └── wiki/           #   Wiki/ドキュメント
│       └── {domain, application, infrastructure, presentation, tasks}/
│
├── shared/             # 複数コンテキストで共有する要素
│   ├── domain/         #   共有ドメイン（user, auth など）
│   ├── application/    #   共有アプリケーションサービス
│   ├── infrastructure/ #   共有インフラ（リポジトリ実装など）
│   ├── presentation/   #   共有プレゼンテーション部品
│   └── kernel/         #   共有カーネル（crypto, database, logging, settings）
│
├── presentation/       # プレゼンテーション層（Flask Web アプリ）
│   └── web/            #   create_app・Blueprint・API・認証・テンプレート等（Web の単一実体）
│
├── core/               # 共通基盤（暗号化・Celery タスク・モデル・設定・ストレージ・version）
├── cli/                # Celery タスク定義・CLI（cli.src.celery 配下）
├── migrations/         # データベースマイグレーション（Alembic）
│
├── frontend/           # フロントエンド（React/TypeScript・Vite。独立した SPA）
├── db/                 # DB コンテナ用 Dockerfile と初期化 SQL
├── scripts/            # 運用・デモ・シードスクリプト
├── docs/               # ドキュメント
├── tests/              # テスト（unit / integration ほか）
│
├── main.py             # 開発用エントリポイント（flask run 相当）
├── wsgi.py             # 本番 WSGI エントリポイント（gunicorn 用）
├── Makefile / frontend.mk  # Docker イメージ・フロントエンドのビルドタスク
└── docker-compose.yml  # ローカル/本番のコンテナ構成
```

> **補足:** Web アプリの実体は `presentation/web/` に一本化されています（旧 `webapp/` パッケージは撤去済み）。OpenAPI 拡張は pip の `flask-smorest`（`requirements.txt` で固定）を使用し、`/api/overview` のインタラクティブ仕様表・favicon 付き Swagger UI・エラースキーマ拡張などの独自機能は `presentation/web/openapi/smorest_ext.py` とアプリのテンプレートでアドオンしています（本体フォークは廃止）。

### 主要機能
- 🔐 **セキュア認証**: JWT + ロールベース権限管理、TOTP 多要素認証
- 📸 **メディア管理**: 写真・動画の統合管理
- ☁️ **Google Photos 同期**: OAuth 認証による自動同期
- 🎬 **動画変換**: FFmpeg による H.264/AAC 変換
- 🖼️ **サムネイル生成**: 多段階サムネイル（256/1024/2048px）
- ⚡ **バックグラウンド処理**: Celery + Redis による非同期処理
- 🔢 **TOTP 管理**: otpauth URI や QR コードからの登録、OTP プレビュー、JSON インポート/エクスポート

## 🔧 必要環境

### 開発環境
- Python 3.10+
- Redis（Celery 用）
- MariaDB 10.11+
- FFmpeg（動画変換用）

### 本番環境（Docker）
- Docker 20.10+
- Docker Compose v2+
- 2GB+ RAM
- 10GB+ ディスク容量

## 🚨 重要な注意事項

### Celery ワーカー（必須）
nolumia のバックグラウンド処理には **Celery ワーカーが必須** です：

```bash
# 正しいワーカー起動コマンド
celery -A cli.src.celery.tasks worker --loglevel=info

# スケジューラも起動（自動リカバリ機能用）
celery -A cli.src.celery.tasks beat --loglevel=info
```

### 📊 Celery タスクの状況確認
アプリケーションのデータベースに保存された Celery タスクの状態は、次のヘルパースクリプトで一覧できます。

```bash
# 直近50件（デフォルト）のタスクをテーブル表示
python -m cli.src.celery.inspect_tasks

# 実行中・待機中タスクだけを確認
python -m cli.src.celery.inspect_tasks --pending

# JSON形式で全タスクを取得
python -m cli.src.celery.inspect_tasks --json --limit 0
```

`--include-payload` や `--include-result` を付与すると、各レコードに保存されている詳細情報も確認できます。

### 初期ユーザー
マスタデータ投入後、以下でログイン可能：
- **Email**: `admin@example.com`
- **Password**: `admin123`
- **⚠️ 初回ログイン後は必ずパスワード変更してください**

## 🔒 セキュリティ

### OAuth トークン暗号化
Google アカウントの OAuth トークンは AES-256-GCM で暗号化保存：

```bash
# 暗号化鍵生成（32バイト）
python -c "
import os, base64
key = base64.b64encode(os.urandom(32)).decode()
print(f'ENCRYPTION_KEY=base64:{key}')
"
```

### 環境変数設定
`.env.example` をコピーして必要な値を設定：

```env
# セキュリティキー（必ず変更）
SECRET_KEY=<your-strong-secret-key>

# データベース接続
DATABASE_URI=mysql+pymysql://<user>:<pass>@<host>/<db>

# Google OAuth（Google Photos 同期用）
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
```

## 🧪 テスト実行

```bash
# 全テスト実行
pytest

# カバレッジ付き
pytest --cov=presentation --cov=bounded_contexts --cov=shared --cov=core

# 特定テスト
pytest tests/unit/core/test_celery_*.py -v
```

## 📦 デプロイ方法

### 開発環境
詳細は [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) を参照

### Synology NAS
Synology Container Manager 用の詳細デプロイガイド：
[docs/synology-deployment.md](docs/synology-deployment.md)

### 本番サーバー
```bash
# Docker イメージ・成果物 tar のビルド（Makefile）
make build

# Docker デプロイ
docker-compose -f docker-compose.yml up -d
```

## 🆘 トラブルシューティング

### よくある問題

#### 1. 「Celery 処理待ち中...」が消えない
```bash
# 自動リカバリが動作しているか確認
ps aux | grep "celery.*beat"

# 手動でセッションクリーンアップ
python -c "
from cli.src.celery.tasks import cleanup_stale_sessions_task
result = cleanup_stale_sessions_task.delay()
"
```

#### 2. ログインできない
```bash
# マスタデータ投入確認
flask seed-master
```

#### 3. Redis 接続エラー
```bash
# Redis 起動確認
redis-cli ping

# Docker 使用の場合
docker run -d -p 6379:6379 redis:7-alpine
```

詳細なトラブルシューティングは [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) を参照してください。

## 🤝 コントリビューション

1. このリポジトリをフォーク
2. 機能ブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## 📄 ライセンス

[MIT License](LICENSE)

---

**📖 詳細情報**: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | **🚀 Synology デプロイ**: [docs/synology-deployment.md](docs/synology-deployment.md)
