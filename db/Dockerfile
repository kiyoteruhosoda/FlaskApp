# /workspace/FlaskApp/db/Dockerfile
FROM mariadb:10.11

# スキーマ・マスタデータは焼き込まず、web コンテナ起動時の
# `alembic upgrade head`（entrypoint.sh）で構築する。この DB イメージは
# タイムゾーンを UTC に固定した素の MariaDB。

# タイムゾーンを固定（任意）
ENV TZ=UTC

# MariaDB の内部時刻を UTC に統一
CMD ["mysqld", "--default-time-zone=+00:00"]
