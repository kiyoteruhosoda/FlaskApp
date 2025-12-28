ステップバイステップの手順
① 修正済み 01_initialize.sql をローカルの db/init に保存
/workspace/FlaskApp/db/init/01_initialize.sql

② DB イメージを再ビルド
make build-db


これで新しい photonest-db:latest と
photonest-db-latest.tar が生成されます。

③ Synology（ホスト側）で既存DBを削除して再ロード
# 停止
docker compose -p photonest -f /volume1/docker/photonest/docker-compose.yml down

# 古いDBデータを削除（初期化トリガー）
rm -rf /volume1/docker/photonest/db_data/*

# 新しいDBイメージをロード
docker load -i /volume1/docker/photonest-db-latest.tar

④ 再起動
docker compose -p photonest -f /volume1/docker/photonest/docker-compose.yml up -d

💬 確認方法

初期化SQLが再実行されたか確認するには：

docker logs mariadb | grep Entrypoint


この中に：

[Entrypoint]: Initializing database files
[Entrypoint]: Running /docker-entrypoint-initdb.d/01_initialize.sql


が出ていれば ✅ 新しいSQLが実行されています。

/docs/DEVELOPMENT.md
に移動

