# nolumia

nolumiaは、DDD（ドメイン駆動設計）アーキテクチャを採用したFlaskベースの家族写真管理・同期プラットフォームです。Google Photos同期、ローカルファイルインポート、動画変換、サムネイル生成などの処理をCeleryによるバックグラウンドジョブで実行します。


## 開発向けDOC

/docs/DEVELOPMENT.md

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
# .envファイルを編集してデータベース接続情報等を設定

# 4. データベースセットアップ
flask db upgrade
flask seed-master

# 5. アプリケーション起動
python main.py
```

### 本番環境（Docker推奨）
```bash
# 1. Dockerイメージビルド
docker build -t photonest:latest .

# 2. 環境設定
cp .env.example .env
# .envファイルを本番環境用に編集

# 3. サービス起動
docker-compose up -d

# 4. 初期データベースセットアップ
docker-compose exec web flask db upgrade
docker-compose exec web flask seed-master
```

## 📚 ドキュメント

- **[開発ガイド](DEVELOPMENT.md)** - 詳細なセットアップ、Celery、テスト実行
- **[Synologyデプロイ](synology-deployment.md)** - Synology NAS専用デプロイガイド
- **[TOTP 管理ガイド](docs/totp_management.md)** - TOTP資格情報の登録・インポート/エクスポート手順
- **[API仕様](requirements.md)** - 技術仕様書・API設計

## 🏗️ アーキテクチャ

### DDD構成
```
nolumia/
├── webapp/           # Webアプリケーション層（Flask）
├── domain/          # ドメイン層（ビジネスロジック）
├── application/     # アプリケーションサービス層
├── infrastructure/  # インフラストラクチャ層（DB、外部API）
├── core/           # 共通機能（暗号化、タスク）
├── cli/            # Celeryタスク定義
└── migrations/     # データベースマイグレーション
```

### 主要機能
- 🔐 **セキュア認証**: JWT + ロールベース権限管理
- 📸 **メディア管理**: 写真・動画の統合管理
- ☁️ **Google Photos同期**: OAuth認証による自動同期
- 🎬 **動画変換**: FFmpegによるH.264/AAC変換
- 🖼️ **サムネイル生成**: 多段階サムネイル（256/1024/2048px）
- ⚡ **バックグラウンド処理**: Celery + Redisによる非同期処理
- 🔢 **TOTP 管理**: otpauth URI や QR コードからの登録、OTP プレビュー、JSON インポート/エクスポート

## 🔧 必要環境

### 開発環境
- Python 3.10+
- Redis（Celery用）
- MariaDB 10.11+
- FFmpeg（動画変換用）

### 本番環境（Docker）
- Docker 20.10+
- Docker Compose v2+
- 2GB+ RAM
- 10GB+ ディスク容量

## 🚨 重要な注意事項

### Celeryワーカー（必須）
nolumiaのバックグラウンド処理には**Celeryワーカーが必須**です：

```bash
# 正しいワーカー起動コマンド
celery -A cli.src.celery.tasks worker --loglevel=info

# スケジューラも起動（自動リカバリ機能用）
celery -A cli.src.celery.tasks beat --loglevel=info
```

### 📊 Celeryタスクの状況確認
アプリケーションのデータベースに保存されたCeleryタスクの状態は、次のヘルパースクリプトで一覧できます。

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
Google アカウントのOAuthトークンはAES-256-GCMで暗号化保存：

```bash
# 暗号化鍵生成（32バイト）
python -c "
import os, base64
key = base64.b64encode(os.urandom(32)).decode()
print(f'ENCRYPTION_KEY=base64:{key}')
"
```

### 環境変数設定
`.env.example`をコピーして必要な値を設定：

```env
# セキュリティキー（必ず変更）
SECRET_KEY=<your-strong-secret-key>

# データベース接続
DATABASE_URI=mysql+pymysql://<user>:<pass>@<host>/<db>

# Google OAuth（Google Photos同期用）
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
```

## 🧪 テスト実行

```bash
# 全テスト実行
pytest

# カバレッジ付き
pytest --cov=webapp --cov=core

# 特定テスト
pytest tests/test_celery_*.py -v
```

## 📦 デプロイ方法

### 開発環境
詳細は [DEVELOPMENT.md](DEVELOPMENT.md) を参照

### Synology NAS
Synology Container Manager用の詳細デプロイガイド：
[synology-deployment.md](synology-deployment.md)

### 本番サーバー
```bash
# リリースパッケージ作成
./create-release.sh

# Dockerデプロイ
docker-compose -f docker-compose.yml up -d
```

## 🆘 トラブルシューティング

### よくある問題

#### 1. 「Celery処理待ち中...」が消えない
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

#### 3. Redis接続エラー
```bash
# Redis起動確認
redis-cli ping

# Docker使用の場合
docker run -d -p 6379:6379 redis:7-alpine
```

詳細なトラブルシューティングは [DEVELOPMENT.md](DEVELOPMENT.md) を参照してください。

## 🤝 コントリビューション

1. このリポジトリをフォーク
2. 機能ブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## 📄 ライセンス

[MIT License](LICENSE)

---

**📖 詳細情報**: [DEVELOPMENT.md](DEVELOPMENT.md) | **🚀 Synologyデプロイ**: [synology-deployment.md](synology-deployment.md)

