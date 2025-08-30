-- データベース初期化スクリプト
-- MariaDB用の設定とパフォーマンス最適化

-- 文字セットをUTF8に設定
ALTER DATABASE photonest CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- パフォーマンス最適化のための設定
SET GLOBAL innodb_buffer_pool_size = 268435456; -- 256MB
SET GLOBAL innodb_log_file_size = 67108864; -- 64MB
SET GLOBAL max_connections = 200;
SET GLOBAL query_cache_type = 1;
SET GLOBAL query_cache_size = 33554432; -- 32MB

-- ユーザー権限の設定
GRANT ALL PRIVILEGES ON photonest.* TO 'photonest_user'@'%';
FLUSH PRIVILEGES;
