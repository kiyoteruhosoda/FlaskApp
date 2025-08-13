# FlaskApp

Python パッケージをまとめてインストールする場合
pip install -r requirements.txt

古いバージョンの pip を使っている場合は、先にアップデート
python -m pip install --upgrade pip

pybabel compile -d app/translations -f



## Google OAuth Token Encryption

`google_account.oauth_token_json` は AES-256-GCM で暗号化して保存します。
`OAUTH_TOKEN_KEY`（Base64）または `OAUTH_TOKEN_KEY_FILE` で 32 バイト鍵を指定してください。
鍵は OS の KMS もしくは鍵ファイルで管理できます。

## Flask-Migrate マイグレーション手順

### 1. モデル変更後にマイグレーションファイルを作成

```bash
flask db migrate -m "変更内容のコメント（例: add column xxx）"
```

### 2. マイグレーションを適用

```bash
flask db upgrade
```


### 3. マイグレーション失敗時の対応

#### ■ 手動で戻す場合

対象テーブルやカラムを削除・修正し、`alembic_version` を前のバージョンに戻す

```sql
DROP TABLE IF EXISTS xxxx;
UPDATE alembic_version 
SET version_num = '7ddda1a4f37x' 
WHERE version_num = '6d1ad4f0b9ax';
```

#### ■ 特定バージョンまで巻き戻す場合

```bash
flask db downgrade 6d1ad4f0b9ax
```

#### ■ すべてのマイグレーションを取り消して初期状態に戻す場合

```bash
flask db downgrade base
```


### 4. 再度マイグレーションファイル作成に戻る

モデルを修正 → **1** に戻って再実行。

