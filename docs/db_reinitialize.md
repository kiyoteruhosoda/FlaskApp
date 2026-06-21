# データベース再初期化手順（Synology / Docker）

初期化 SQL（`db/init/01_initialize.sql`）を更新した際に、DB を作り直して
再初期化トリガーを走らせるためのステップバイステップ手順です。

## ① 修正済み `01_initialize.sql` を `db/init` に保存

```
db/init/01_initialize.sql
```

## ② DB イメージを再ビルド

```bash
make build-db
```

これで新しい `photonest-db:latest` と `photonest-db-latest.tar` が生成されます。

## ③ Synology（ホスト側）で既存 DB を削除して再ロード

```bash
# 停止
docker compose -p photonest -f /volume1/docker/photonest/docker-compose.yml down

# 古い DB データを削除（初期化トリガー）
rm -rf /volume1/docker/photonest/db_data/*

# 新しい DB イメージをロード
docker load -i /volume1/docker/photonest-db-latest.tar
```

## ④ 再起動

```bash
docker compose -p photonest -f /volume1/docker/photonest/docker-compose.yml up -d
```

## 💬 確認方法

初期化 SQL が再実行されたか確認するには：

```bash
docker logs mariadb | grep Entrypoint
```

この中に以下が出ていれば、新しい SQL が実行されています。

```
[Entrypoint]: Initializing database files
[Entrypoint]: Running /docker-entrypoint-initdb.d/01_initialize.sql
```
