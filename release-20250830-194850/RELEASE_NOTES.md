# PhotoNest Release 20250830-194850

## デプロイ手順

### 1. 環境変数の設定
```bash
cp .env.production .env
# .envファイルを編集して適切な値を設定してください
```

### 2. Dockerを使用したデプロイ
```bash
# イメージをビルド
./build-release.sh 20250830-194850

# アプリケーションを起動
docker-compose up -d
```

### 3. 手動デプロイ
```bash
# 依存関係をインストール
pip install -r requirements-prod.txt

# データベースマイグレーション
./deploy.sh
```

## 本番環境チェックリスト

- [ ] .envファイルの設定確認
- [ ] データベース接続設定
- [ ] Google OAuth設定
- [ ] セキュリティキーの変更
- [ ] SSL証明書の設定
- [ ] ファイアウォール設定
- [ ] バックアップ設定

## パッケージ内容

- アプリケーションコード
- 本番用Docker設定
- デプロイスクリプト
- データベース設定
- 環境変数テンプレート

