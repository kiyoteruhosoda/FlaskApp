# PhotoNest 使い方手順書

## 1. 概要
PhotoNest は Flask をベースにしたウェブアプリケーションで、Google フォト同期やサムネイル生成などの処理をバックグラウンドジョブ（Celery）で行う構成です。

## 2. 必要環境
- Python 3.10 以上
- Redis（Celery の broker / backend 用）
- `requirements.txt` に記載されたライブラリ

## 3. セットアップ
```bash
pip install -r requirements.txt
cp .env.example .env  # 必要に応じて編集
python main.py        # 開発サーバーを起動
```

古い pip を使っている場合は先にアップデートします。
```bash
python -m pip install --upgrade pip
```

## 4. 開発サーバーの起動
アプリケーションファクトリから Flask アプリを生成し、デバッグモードで起動します。
```bash
python main.py
```

## 5. 翻訳ファイルのコンパイル
多言語対応のメッセージファイルを更新したら、次のコマンドでコンパイルします。
```bash
pybabel compile -d webapp/translations -f
```

## 6. 環境変数と設定
`.env` をコピーして必要な値を設定します。
```bash
cp .env.example .env
# 値を編集
```
主な設定項目（抜粋）:
- `SECRET_KEY`: アプリケーションの秘密鍵
- `DATABASE_URI`: SQLAlchemy の接続文字列
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: Google OAuth
- `OAUTH_TOKEN_KEY` または `OAUTH_TOKEN_KEY_FILE`: OAuth トークン暗号化用鍵

## 7. データベースマイグレーション
1. モデル変更後にマイグレーションファイルを作成  
   ```bash
   flask db migrate -m "変更内容のコメント"
   ```
2. マイグレーションを適用  
   ```bash
   flask db upgrade
   ```

## 8. Celery バックグラウンドジョブ
定義済みタスクを実行するにはワーカーとスケジューラを起動します。
```bash
# ワーカー
celery -A cli.src.celery.tasks worker --loglevel=info
# スケジューラ (beat)
celery -A cli.src.celery.tasks beat --loglevel=info
```

## 9. Google OAuth トークン暗号化
`google_account.oauth_token_json` は AES-256-GCM で暗号化されます。`OAUTH_TOKEN_KEY`（Base64 形式 32 バイト）または鍵ファイルを `.env` で指定してください。

## 10. テストの実行
`pytest` を使用してユニットテストを実行できます。
```bash
pytest
```
