# /workspace/FlaskApp/db/Dockerfile
FROM mariadb:10.11

# 初期SQLを公式の初期化ディレクトリにコピー
COPY ./init /docker-entrypoint-initdb.d

# タイムゾーンを固定（任意）
ENV TZ=UTC

# MariaDB の内部時刻を UTC に統一
CMD ["mysqld", "--default-time-zone=+00:00"]
