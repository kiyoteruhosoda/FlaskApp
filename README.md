# PhotoNest
## FlaskApp

### セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env  # 必要に応じて編集
python main.py        # 開発サーバーを起動
```

古いバージョンの pip を使っている場合は先にアップデートします。

```bash
python -m pip install --upgrade pip
```

翻訳ファイルを更新する場合は次を実行します。

```bash
pybabel compile -d webapp/translations -f
```



## Google OAuth Token Encryption

`google_account.oauth_token_json` は AES-256-GCM で暗号化して保存します。
`OAUTH_TOKEN_KEY`（Base64）または `OAUTH_TOKEN_KEY_FILE` / `FPV_OAUTH_TOKEN_KEY_FILE` で 32 バイト鍵を指定してください。
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


```SQL
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS album;
DROP TABLE IF EXISTS album_item;
DROP TABLE IF EXISTS exif;
DROP TABLE IF EXISTS google_account;
DROP TABLE IF EXISTS media;
DROP TABLE IF EXISTS media_playback;
DROP TABLE IF EXISTS media_sidecar;
DROP TABLE IF EXISTS media_tag;
DROP TABLE IF EXISTS permission;
DROP TABLE IF EXISTS role;
DROP TABLE IF EXISTS role_permissions;
DROP TABLE IF EXISTS tag;
DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS user_roles;
DROP TABLE IF EXISTS job_sync;
DROP TABLE IF EXISTS alembic_version;

SET FOREIGN_KEY_CHECKS = 1;
```

```bash
flask db migrate -m "base"
```

出来たマイグレーションファイルのdef upgrade():末尾に以下を追記

```python
    op.execute("INSERT INTO role (id, name) VALUES (1, 'admin'), (2, 'manager'), (3, 'member')")
    op.execute(
        "INSERT INTO permission (id, code) VALUES " \
        "(1, 'admin:photo-settings'), (2, 'admin:job-settings'), (3, 'user:manage'), (4, 'album:create'), (5, 'album:edit'), " \
        "(6, 'album:view'), (7, 'media:view'), (8, 'permission:manage'), (9, 'role:manage'), (10, 'system:manage')")
    op.execute(
        "INSERT INTO role_permissions (role_id, perm_id) VALUES " \
        "(1, 1), (1, 2), (1, 3), (1, 4), (1, 5)," \
        "(1, 6), (1, 7), (2, 1), (2, 4), (2, 5), (2, 6), (2, 7), (3, 6), (3, 7)")
    op.execute("INSERT INTO user (id, email,  password_hash,created_at) VALUES (1, 'admin@example.com', 'scrypt:32768:8:1$7oTcIUdekNLXGSXC$fd0f3320bde4570c7e1ea9d9d289aeb916db7a50fb62489a7e89d99c6cc576813506fd99f50904101c1eb85ff925f8dc879df5ded781ef2613224d702938c9c8', NOW())")
    op.execute("INSERT INTO user_roles (user_id, role_id) VALUES (1, 1)")
```


### 4. 再度マイグレーションファイル作成に戻る

モデルを修正 → **1** に戻って再実行。


## Configuration

Configure via environment variables. Copy `.env.example` to `.env` (loaded automatically by `python-dotenv`).

```bash
cp .env.example .env
# edit values
```

Show and validate:

```bash
fpv config show                # display with masking
fpv config check               # basic validation
fpv config check --strict-path # also verify path existence
```

`FPV_OAUTH_KEY` references the existing `OAUTH_TOKEN_KEY` (set `FPV_OAUTH_KEY=${OAUTH_TOKEN_KEY}` in `.env`). Alternatively, specify `FPV_OAUTH_TOKEN_KEY_FILE` to load the key from a file (e.g. `FPV_OAUTH_TOKEN_KEY_FILE=${OAUTH_TOKEN_KEY_FILE}`). `OAUTH_TOKEN_KEY` should specify a 32-byte key in the form `base64:xxxxxxxxxx`.

## Sync 実行（ダウンロード→保存）

```bash
# まずは1ページだけ、実ダウンロード
fpv sync --no-dry-run --page-size 50 --max-pages 1

# ページ数を増やしていく場合
fpv sync --no-dry-run --page-size 100 --max-pages 5
```

- 既存重複は `hash_sha256` でスキップされます。
- 保存先は `originals/YYYY/MM/DD/` 以下、ファイル名は `YYYYMMDD_HHMMSS_gphotos_<hash8>.<ext>`。
- 動画は `media_playback` に `queued` で登録されます（変換は `fpv transcode` 側で処理）。
- 途中状態は `job_sync.stats_json.cursor.nextPageToken` に保持され、再実行で続きから再開します。

