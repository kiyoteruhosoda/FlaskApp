-- PhotoNest DB baseline (schema + master data)
-- 現行 SQLAlchemy モデルから機械生成。ロール/権限/初期管理者を含む。
-- 再生成: ./scripts/regenerate_db_baseline.sh  (Docker 環境)
-- alembic head: 2a1f9c0b3d4e

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;

DROP TABLE IF EXISTS `alembic_version`;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `alembic_version` (`version_num`) VALUES ('2a1f9c0b3d4e');

DROP TABLE IF EXISTS `celery_task`;
CREATE TABLE `celery_task` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`task_name` VARCHAR(255) NOT NULL, 
	`object_type` VARCHAR(64), 
	`object_id` VARCHAR(255), 
	`celery_task_id` VARCHAR(255), 
	`status` VARCHAR(9) NOT NULL DEFAULT 'queued', 
	`scheduled_for` DATETIME, 
	`started_at` DATETIME, 
	`finished_at` DATETIME, 
	`payload_json` TEXT NOT NULL DEFAULT '{}', 
	`result_json` TEXT, 
	`error_message` TEXT, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	UNIQUE (`celery_task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_celery_task_object` ON `celery_task` (`object_type`, `object_id`);
CREATE INDEX `ix_celery_task_task_name_status` ON `celery_task` (`task_name`, `status`);

DROP TABLE IF EXISTS `certificate_events`;
CREATE TABLE `certificate_events` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`actor` VARCHAR(255) NOT NULL, 
	`action` VARCHAR(64) NOT NULL, 
	`target_kid` VARCHAR(64), 
	`target_group_code` VARCHAR(64), 
	`reason` TEXT, 
	`details` JSON, 
	`occurred_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_certificate_events_occurred_at` ON `certificate_events` (`occurred_at`);
CREATE INDEX `ix_certificate_events_target_group_code` ON `certificate_events` (`target_group_code`);
CREATE INDEX `ix_certificate_events_target_kid` ON `certificate_events` (`target_kid`);

DROP TABLE IF EXISTS `certificate_groups`;
CREATE TABLE `certificate_groups` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`group_code` VARCHAR(64) NOT NULL, 
	`display_name` VARCHAR(128), 
	`auto_rotate` BOOL NOT NULL, 
	`rotation_threshold_days` INTEGER NOT NULL, 
	`key_type` VARCHAR(16) NOT NULL, 
	`key_curve` VARCHAR(32), 
	`key_size` INTEGER, 
	`subject` JSON NOT NULL, 
	`usage_type` VARCHAR(32) NOT NULL, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	UNIQUE (`group_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_certificate_groups_usage_type` ON `certificate_groups` (`usage_type`);

DROP TABLE IF EXISTS `log`;
CREATE TABLE `log` (
	`id` INTEGER NOT NULL AUTO_INCREMENT, 
	`level` VARCHAR(50) NOT NULL, 
	`event` VARCHAR(50) NOT NULL, 
	`message` TEXT NOT NULL, 
	`trace` TEXT, 
	`path` VARCHAR(255), 
	`request_id` VARCHAR(36), 
	`created_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `password_reset_token`;
CREATE TABLE `password_reset_token` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`email` VARCHAR(255) NOT NULL, 
	`token_hash` VARCHAR(255) NOT NULL, 
	`expires_at` DATETIME NOT NULL, 
	`used` BOOL NOT NULL, 
	`created_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	UNIQUE (`token_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_password_reset_token_email` ON `password_reset_token` (`email`);

DROP TABLE IF EXISTS `permission`;
CREATE TABLE `permission` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`code` VARCHAR(120) NOT NULL, 
	`detail` TEXT, 
	PRIMARY KEY (`id`), 
	UNIQUE (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `photo_metadata`;
CREATE TABLE `photo_metadata` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`focal_length` FLOAT, 
	`aperture_f_number` FLOAT, 
	`iso_equivalent` INTEGER, 
	`exposure_time` VARCHAR(32), 
	PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `picker_import_task`;
CREATE TABLE `picker_import_task` (
	`id` INTEGER NOT NULL AUTO_INCREMENT, 
	PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `role`;
CREATE TABLE `role` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`name` VARCHAR(80) NOT NULL, 
	PRIMARY KEY (`id`), 
	UNIQUE (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `system_settings`;
CREATE TABLE `system_settings` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`setting_key` VARCHAR(100) NOT NULL, 
	`setting_json` JSON NOT NULL, 
	`description` TEXT, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	UNIQUE (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `user`;
CREATE TABLE `user` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`email` VARCHAR(255) NOT NULL, 
	`username` VARCHAR(80), 
	`password_hash` VARCHAR(255) NOT NULL, 
	`created_at` DATETIME NOT NULL, 
	`totp_secret` VARCHAR(32), 
	`is_active` BOOL NOT NULL, 
	`refresh_token_hash` VARCHAR(255), 
	`must_change_password` BOOL NOT NULL DEFAULT '0', 
	PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE UNIQUE INDEX `ix_user_email` ON `user` (`email`);

DROP TABLE IF EXISTS `user_group`;
CREATE TABLE `user_group` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`name` VARCHAR(120) NOT NULL, 
	`description` TEXT, 
	`parent_id` BIGINT, 
	PRIMARY KEY (`id`), 
	CONSTRAINT `uq_user_group_name` UNIQUE (`name`), 
	FOREIGN KEY(`parent_id`) REFERENCES `user_group` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `video_metadata`;
CREATE TABLE `video_metadata` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`fps` FLOAT, 
	`processing_status` VARCHAR(11), 
	PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `wiki_category`;
CREATE TABLE `wiki_category` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`name` VARCHAR(100) NOT NULL, 
	`description` TEXT, 
	`slug` VARCHAR(100) NOT NULL, 
	`sort_order` INTEGER NOT NULL, 
	`created_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE UNIQUE INDEX `ix_wiki_category_slug` ON `wiki_category` (`slug`);

DROP TABLE IF EXISTS `worker_log`;
CREATE TABLE `worker_log` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`created_at` DATETIME NOT NULL, 
	`level` VARCHAR(20) NOT NULL, 
	`event` VARCHAR(50) NOT NULL, 
	`logger_name` VARCHAR(120), 
	`task_name` VARCHAR(255), 
	`task_uuid` VARCHAR(36), 
	`file_task_id` VARCHAR(64), 
	`progress_step` INTEGER, 
	`worker_hostname` VARCHAR(255), 
	`queue_name` VARCHAR(120), 
	`status` VARCHAR(40), 
	`message` TEXT NOT NULL, 
	`trace` TEXT, 
	`meta_json` JSON, 
	`extra_json` JSON, 
	PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_worker_log_event` ON `worker_log` (`event`);
CREATE INDEX `ix_worker_log_file_task_id` ON `worker_log` (`file_task_id`);
CREATE INDEX `ix_worker_log_file_task_id_progress_step` ON `worker_log` (`file_task_id`, `progress_step`);

DROP TABLE IF EXISTS `google_account`;
CREATE TABLE `google_account` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`user_id` BIGINT, 
	`email` VARCHAR(255) NOT NULL, 
	`status` VARCHAR(20) NOT NULL, 
	`scopes` TEXT NOT NULL, 
	`last_synced_at` DATETIME, 
	`oauth_token_json` TEXT, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	CONSTRAINT `uq_user_google_email` UNIQUE (`user_id`, `email`), 
	FOREIGN KEY(`user_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `group_roles`;
CREATE TABLE `group_roles` (
	`group_id` BIGINT NOT NULL, 
	`role_id` BIGINT NOT NULL, 
	PRIMARY KEY (`group_id`, `role_id`), 
	CONSTRAINT `uq_group_roles` UNIQUE (`group_id`, `role_id`), 
	FOREIGN KEY(`group_id`) REFERENCES `user_group` (`id`), 
	FOREIGN KEY(`role_id`) REFERENCES `role` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `group_user_membership`;
CREATE TABLE `group_user_membership` (
	`group_id` BIGINT NOT NULL, 
	`user_id` BIGINT NOT NULL, 
	PRIMARY KEY (`group_id`, `user_id`), 
	CONSTRAINT `uq_group_user_membership` UNIQUE (`group_id`, `user_id`), 
	FOREIGN KEY(`group_id`) REFERENCES `user_group` (`id`), 
	FOREIGN KEY(`user_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `impersonation_audit_log`;
CREATE TABLE `impersonation_audit_log` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`impersonator_id` BIGINT, 
	`impersonated_id` BIGINT, 
	`event` VARCHAR(16) NOT NULL, 
	`ip_address` VARCHAR(45), 
	`user_agent` TEXT, 
	`created_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`impersonator_id`) REFERENCES `user` (`id`) ON DELETE SET NULL, 
	FOREIGN KEY(`impersonated_id`) REFERENCES `user` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_impersonation_audit_log_created_at` ON `impersonation_audit_log` (`created_at`);
CREATE INDEX `ix_impersonation_audit_log_impersonated_id` ON `impersonation_audit_log` (`impersonated_id`);
CREATE INDEX `ix_impersonation_audit_log_impersonator_id` ON `impersonation_audit_log` (`impersonator_id`);

DROP TABLE IF EXISTS `issued_certificates`;
CREATE TABLE `issued_certificates` (
	`kid` VARCHAR(64) NOT NULL, 
	`usage_type` VARCHAR(32) NOT NULL, 
	`group_id` BIGINT, 
	`certificate_pem` TEXT NOT NULL, 
	`jwk` JSON NOT NULL, 
	`issued_at` DATETIME NOT NULL, 
	`expires_at` DATETIME, 
	`revoked_at` DATETIME, 
	`revocation_reason` TEXT, 
	`auto_rotated_from_kid` VARCHAR(64), 
	PRIMARY KEY (`kid`), 
	FOREIGN KEY(`group_id`) REFERENCES `certificate_groups` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_issued_certificates_expires_at` ON `issued_certificates` (`expires_at`);
CREATE INDEX `ix_issued_certificates_issued_at` ON `issued_certificates` (`issued_at`);
CREATE INDEX `ix_issued_certificates_usage_type` ON `issued_certificates` (`usage_type`);

DROP TABLE IF EXISTS `media_item`;
CREATE TABLE `media_item` (
	`id` VARCHAR(255) NOT NULL, 
	`type` VARCHAR(16) NOT NULL, 
	`mime_type` VARCHAR(255), 
	`filename` VARCHAR(255), 
	`width` INTEGER, 
	`height` INTEGER, 
	`camera_make` VARCHAR(255), 
	`camera_model` VARCHAR(255), 
	`photo_metadata_id` BIGINT, 
	`video_metadata_id` BIGINT, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`photo_metadata_id`) REFERENCES `photo_metadata` (`id`), 
	FOREIGN KEY(`video_metadata_id`) REFERENCES `video_metadata` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `passkey_credential`;
CREATE TABLE `passkey_credential` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`user_id` BIGINT NOT NULL, 
	`credential_id` VARCHAR(255) NOT NULL, 
	`public_key` TEXT NOT NULL, 
	`sign_count` BIGINT NOT NULL, 
	`transports` JSON, 
	`name` VARCHAR(255), 
	`attestation_format` VARCHAR(64), 
	`aaguid` VARCHAR(64), 
	`backup_eligible` BOOL NOT NULL, 
	`backup_state` BOOL NOT NULL, 
	`last_used_at` DATETIME, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	CONSTRAINT `uq_passkey_credential_id` UNIQUE (`credential_id`), 
	FOREIGN KEY(`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_passkey_credential_user_id` ON `passkey_credential` (`user_id`);

DROP TABLE IF EXISTS `role_permissions`;
CREATE TABLE `role_permissions` (
	`role_id` BIGINT NOT NULL, 
	`perm_id` BIGINT NOT NULL, 
	PRIMARY KEY (`role_id`, `perm_id`), 
	FOREIGN KEY(`role_id`) REFERENCES `role` (`id`), 
	FOREIGN KEY(`perm_id`) REFERENCES `permission` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `service_account`;
CREATE TABLE `service_account` (
	`service_account_id` BIGINT NOT NULL AUTO_INCREMENT, 
	`name` VARCHAR(100) NOT NULL, 
	`description` VARCHAR(255), 
	`certificate_group_code` VARCHAR(64), 
	`scope_names` VARCHAR(1000) NOT NULL, 
	`active_flg` BOOL NOT NULL, 
	`reg_dttm` DATETIME NOT NULL DEFAULT now(), 
	`mod_dttm` DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (`service_account_id`), 
	UNIQUE (`name`), 
	FOREIGN KEY(`certificate_group_code`) REFERENCES `certificate_groups` (`group_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `tag`;
CREATE TABLE `tag` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`name` VARCHAR(255) NOT NULL, 
	`attr` VARCHAR(8) NOT NULL, 
	`created_at` DATETIME NOT NULL, 
	`created_by` BIGINT, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`created_by`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `totp_credential`;
CREATE TABLE `totp_credential` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`user_id` BIGINT NOT NULL, 
	`account` VARCHAR(255) NOT NULL, 
	`issuer` VARCHAR(255) NOT NULL, 
	`secret` VARCHAR(160) NOT NULL, 
	`description` TEXT, 
	`algorithm` VARCHAR(16) NOT NULL, 
	`digits` SMALLINT NOT NULL, 
	`period` SMALLINT NOT NULL, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	CONSTRAINT `uq_totp_user_account_issuer` UNIQUE (`user_id`, `account`, `issuer`), 
	FOREIGN KEY(`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_totp_credential_user_id` ON `totp_credential` (`user_id`);

DROP TABLE IF EXISTS `user_preference`;
CREATE TABLE `user_preference` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`user_id` BIGINT NOT NULL, 
	`key` VARCHAR(120) NOT NULL, 
	`value_json` TEXT NOT NULL, 
	PRIMARY KEY (`id`), 
	CONSTRAINT `uq_user_preference_user_key` UNIQUE (`user_id`, `key`), 
	FOREIGN KEY(`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_user_preference_user_id` ON `user_preference` (`user_id`);

DROP TABLE IF EXISTS `user_roles`;
CREATE TABLE `user_roles` (
	`user_id` BIGINT NOT NULL, 
	`role_id` BIGINT NOT NULL, 
	PRIMARY KEY (`user_id`, `role_id`), 
	FOREIGN KEY(`user_id`) REFERENCES `user` (`id`), 
	FOREIGN KEY(`role_id`) REFERENCES `role` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `wiki_page`;
CREATE TABLE `wiki_page` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`title` VARCHAR(255) NOT NULL, 
	`content` TEXT NOT NULL, 
	`slug` VARCHAR(255) NOT NULL, 
	`is_published` BOOL NOT NULL, 
	`parent_id` BIGINT, 
	`sort_order` INTEGER NOT NULL, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	`created_by_id` BIGINT NOT NULL, 
	`updated_by_id` BIGINT NOT NULL, 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`parent_id`) REFERENCES `wiki_page` (`id`), 
	FOREIGN KEY(`created_by_id`) REFERENCES `user` (`id`), 
	FOREIGN KEY(`updated_by_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE UNIQUE INDEX `ix_wiki_page_slug` ON `wiki_page` (`slug`);

DROP TABLE IF EXISTS `certificate_private_keys`;
CREATE TABLE `certificate_private_keys` (
	`kid` VARCHAR(64) NOT NULL, 
	`group_id` BIGINT, 
	`private_key_pem` TEXT NOT NULL, 
	`created_at` DATETIME NOT NULL, 
	`expires_at` DATETIME, 
	PRIMARY KEY (`kid`), 
	FOREIGN KEY(`kid`) REFERENCES `issued_certificates` (`kid`) ON DELETE CASCADE, 
	FOREIGN KEY(`group_id`) REFERENCES `certificate_groups` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_certificate_private_keys_created_at` ON `certificate_private_keys` (`created_at`);
CREATE INDEX `ix_certificate_private_keys_expires_at` ON `certificate_private_keys` (`expires_at`);

DROP TABLE IF EXISTS `media`;
CREATE TABLE `media` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`source_type` VARCHAR(13) NOT NULL, 
	`google_media_id` VARCHAR(255), 
	`account_id` BIGINT, 
	`local_rel_path` VARCHAR(255), 
	`thumbnail_rel_path` VARCHAR(255), 
	`filename` VARCHAR(255), 
	`hash_sha256` CHAR(64), 
	`phash` VARCHAR(64), 
	`bytes` BIGINT, 
	`mime_type` VARCHAR(255), 
	`width` INTEGER, 
	`height` INTEGER, 
	`duration_ms` INTEGER, 
	`orientation` INTEGER, 
	`is_video` BOOL NOT NULL, 
	`shot_at` DATETIME, 
	`camera_make` VARCHAR(255), 
	`camera_model` VARCHAR(255), 
	`imported_at` DATETIME NOT NULL, 
	`is_deleted` BOOL NOT NULL, 
	`has_playback` BOOL NOT NULL, 
	`live_group_id` BIGINT, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	CONSTRAINT `uq_media_google_media_id` UNIQUE (`google_media_id`), 
	FOREIGN KEY(`account_id`) REFERENCES `google_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `picker_session`;
CREATE TABLE `picker_session` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`account_id` BIGINT, 
	`session_id` VARCHAR(255), 
	`picker_uri` TEXT, 
	`expire_time` DATETIME, 
	`polling_config_json` TEXT, 
	`picking_config_json` TEXT, 
	`media_items_set` BOOL, 
	`trigger` VARCHAR(32) NOT NULL DEFAULT 'unknown', 
	`triggered_by_user_id` BIGINT, 
	`status` VARCHAR(10) NOT NULL DEFAULT 'pending', 
	`selected_count` INTEGER, 
	`stats_json` TEXT, 
	`last_polled_at` DATETIME, 
	`last_progress_at` DATETIME, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`account_id`) REFERENCES `google_account` (`id`), 
	UNIQUE (`session_id`), 
	FOREIGN KEY(`triggered_by_user_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `service_account_api_key`;
CREATE TABLE `service_account_api_key` (
	`api_key_id` BIGINT NOT NULL AUTO_INCREMENT, 
	`service_account_id` BIGINT NOT NULL, 
	`public_id` VARCHAR(32) NOT NULL, 
	`secret_hash` VARCHAR(255) NOT NULL, 
	`scope_names` VARCHAR(2000) NOT NULL, 
	`expires_at` DATETIME, 
	`revoked_at` DATETIME, 
	`created_at` DATETIME NOT NULL DEFAULT now(), 
	`created_by` VARCHAR(255) NOT NULL, 
	PRIMARY KEY (`api_key_id`), 
	FOREIGN KEY(`service_account_id`) REFERENCES `service_account` (`service_account_id`), 
	UNIQUE (`public_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_service_account_api_key_service_account_id` ON `service_account_api_key` (`service_account_id`);

DROP TABLE IF EXISTS `wiki_page_category`;
CREATE TABLE `wiki_page_category` (
	`page_id` BIGINT NOT NULL, 
	`category_id` BIGINT NOT NULL, 
	PRIMARY KEY (`page_id`, `category_id`), 
	FOREIGN KEY(`page_id`) REFERENCES `wiki_page` (`id`), 
	FOREIGN KEY(`category_id`) REFERENCES `wiki_category` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `wiki_revision`;
CREATE TABLE `wiki_revision` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`page_id` BIGINT NOT NULL, 
	`title` VARCHAR(255) NOT NULL, 
	`content` TEXT NOT NULL, 
	`revision_number` INTEGER NOT NULL, 
	`change_summary` VARCHAR(500), 
	`created_at` DATETIME NOT NULL, 
	`created_by_id` BIGINT NOT NULL, 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`page_id`) REFERENCES `wiki_page` (`id`), 
	FOREIGN KEY(`created_by_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `album`;
CREATE TABLE `album` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`name` VARCHAR(255) NOT NULL, 
	`description` TEXT, 
	`cover_media_id` BIGINT, 
	`visibility` VARCHAR(8) NOT NULL, 
	`display_order` INTEGER, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`cover_media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `exif`;
CREATE TABLE `exif` (
	`media_id` BIGINT NOT NULL, 
	`camera_make` VARCHAR(255), 
	`camera_model` VARCHAR(255), 
	`lens` VARCHAR(255), 
	`iso` INTEGER, 
	`shutter` VARCHAR(32), 
	`f_number` NUMERIC(5, 2), 
	`focal_len` NUMERIC(5, 2), 
	`gps_lat` NUMERIC(10, 7), 
	`gps_lng` NUMERIC(10, 7), 
	`raw_json` TEXT, 
	PRIMARY KEY (`media_id`), 
	FOREIGN KEY(`media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `job_sync`;
CREATE TABLE `job_sync` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`target` VARCHAR(50) NOT NULL, 
	`task_name` VARCHAR(255) NOT NULL DEFAULT '', 
	`queue_name` VARCHAR(120), 
	`trigger` VARCHAR(32) NOT NULL DEFAULT 'worker', 
	`account_id` BIGINT, 
	`session_id` BIGINT, 
	`celery_task_id` BIGINT, 
	`started_at` DATETIME NOT NULL, 
	`finished_at` DATETIME, 
	`status` VARCHAR(8) NOT NULL DEFAULT 'queued', 
	`args_json` TEXT NOT NULL DEFAULT '{}', 
	`stats_json` TEXT NOT NULL DEFAULT '{}', 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`session_id`) REFERENCES `picker_session` (`id`), 
	FOREIGN KEY(`celery_task_id`) REFERENCES `celery_task` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `local_import_audit_log`;
CREATE TABLE `local_import_audit_log` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`timestamp` DATETIME NOT NULL, 
	`level` VARCHAR(8) NOT NULL, 
	`category` VARCHAR(16) NOT NULL, 
	`message` TEXT NOT NULL, 
	`session_id` BIGINT, 
	`item_id` VARCHAR(255), 
	`request_id` VARCHAR(255), 
	`task_id` VARCHAR(255), 
	`user_id` VARCHAR(255), 
	`details` JSON, 
	`error_type` VARCHAR(255), 
	`error_message` TEXT, 
	`stack_trace` TEXT, 
	`recommended_actions` JSON, 
	`duration_ms` FLOAT, 
	`from_state` VARCHAR(50), 
	`to_state` VARCHAR(50), 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`session_id`) REFERENCES `picker_session` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `idx_item_timestamp` ON `local_import_audit_log` (`item_id`, `timestamp`);
CREATE INDEX `idx_level_category` ON `local_import_audit_log` (`level`, `category`);
CREATE INDEX `idx_session_timestamp` ON `local_import_audit_log` (`session_id`, `timestamp`);
CREATE INDEX `ix_local_import_audit_log_category` ON `local_import_audit_log` (`category`);
CREATE INDEX `ix_local_import_audit_log_item_id` ON `local_import_audit_log` (`item_id`);
CREATE INDEX `ix_local_import_audit_log_level` ON `local_import_audit_log` (`level`);
CREATE INDEX `ix_local_import_audit_log_request_id` ON `local_import_audit_log` (`request_id`);
CREATE INDEX `ix_local_import_audit_log_session_id` ON `local_import_audit_log` (`session_id`);
CREATE INDEX `ix_local_import_audit_log_task_id` ON `local_import_audit_log` (`task_id`);
CREATE INDEX `ix_local_import_audit_log_timestamp` ON `local_import_audit_log` (`timestamp`);

DROP TABLE IF EXISTS `media_playback`;
CREATE TABLE `media_playback` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`media_id` BIGINT NOT NULL, 
	`preset` VARCHAR(8) NOT NULL, 
	`rel_path` VARCHAR(255), 
	`width` INTEGER, 
	`height` INTEGER, 
	`v_codec` VARCHAR(32), 
	`a_codec` VARCHAR(32), 
	`v_bitrate_kbps` INTEGER, 
	`duration_ms` INTEGER, 
	`poster_rel_path` VARCHAR(255), 
	`hash_sha256` CHAR(64), 
	`status` VARCHAR(10) NOT NULL, 
	`error_msg` TEXT, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `media_sidecar`;
CREATE TABLE `media_sidecar` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`media_id` BIGINT NOT NULL, 
	`type` VARCHAR(8) NOT NULL, 
	`rel_path` VARCHAR(255), 
	`bytes` BIGINT, 
	PRIMARY KEY (`id`), 
	FOREIGN KEY(`media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `media_tag`;
CREATE TABLE `media_tag` (
	`media_id` BIGINT NOT NULL, 
	`tag_id` BIGINT NOT NULL, 
	PRIMARY KEY (`media_id`, `tag_id`), 
	FOREIGN KEY(`media_id`) REFERENCES `media` (`id`), 
	FOREIGN KEY(`tag_id`) REFERENCES `tag` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `picker_selection`;
CREATE TABLE `picker_selection` (
	`id` BIGINT NOT NULL AUTO_INCREMENT, 
	`session_id` BIGINT NOT NULL, 
	`google_media_id` VARCHAR(255), 
	`local_file_path` TEXT, 
	`local_filename` VARCHAR(500), 
	`status` VARCHAR(8) NOT NULL DEFAULT 'pending', 
	`create_time` DATETIME, 
	`enqueued_at` DATETIME, 
	`started_at` DATETIME, 
	`finished_at` DATETIME, 
	`attempts` INTEGER NOT NULL DEFAULT '0', 
	`error_msg` TEXT, 
	`base_url` TEXT, 
	`base_url_fetched_at` DATETIME, 
	`base_url_valid_until` DATETIME, 
	`locked_by` VARCHAR(255), 
	`lock_heartbeat_at` DATETIME, 
	`last_transition_at` DATETIME, 
	`created_at` DATETIME NOT NULL, 
	`updated_at` DATETIME NOT NULL, 
	PRIMARY KEY (`id`), 
	CONSTRAINT `uq_picker_selection_session_media` UNIQUE (`session_id`, `google_media_id`), 
	FOREIGN KEY(`session_id`) REFERENCES `picker_session` (`id`), 
	FOREIGN KEY(`google_media_id`) REFERENCES `media_item` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `idx_picker_selection_session_status` ON `picker_selection` (`session_id`, `status`);
CREATE INDEX `idx_picker_selection_status_lock` ON `picker_selection` (`status`, `lock_heartbeat_at`);

DROP TABLE IF EXISTS `service_account_api_key_log`;
CREATE TABLE `service_account_api_key_log` (
	`log_id` BIGINT NOT NULL AUTO_INCREMENT, 
	`api_key_id` BIGINT NOT NULL, 
	`accessed_at` DATETIME NOT NULL DEFAULT now(), 
	`ip_address` VARCHAR(64), 
	`endpoint` VARCHAR(255), 
	`user_agent` VARCHAR(255), 
	PRIMARY KEY (`log_id`), 
	FOREIGN KEY(`api_key_id`) REFERENCES `service_account_api_key` (`api_key_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `ix_service_account_api_key_log_api_key_id` ON `service_account_api_key_log` (`api_key_id`);

DROP TABLE IF EXISTS `album_item`;
CREATE TABLE `album_item` (
	`album_id` BIGINT NOT NULL, 
	`media_id` BIGINT NOT NULL, 
	`sort_index` BIGINT, 
	PRIMARY KEY (`album_id`, `media_id`), 
	FOREIGN KEY(`album_id`) REFERENCES `album` (`id`), 
	FOREIGN KEY(`media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- master data (roles / permissions / admin)
-- ------------------------------------------------------------------
-- permission
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (1, 'admin:photo-settings', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (2, 'admin:job-settings', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (3, 'admin:system-settings', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (4, 'user:manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (5, 'album:create', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (6, 'album:edit', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (7, 'album:view', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (8, 'media:view', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (9, 'media:session', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (10, 'group:manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (11, 'permission:manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (12, 'role:manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (13, 'system:manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (14, 'wiki:admin', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (15, 'wiki:read', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (16, 'wiki:write', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (17, 'media:tag-manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (18, 'media:metadata-manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (19, 'media:delete', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (20, 'media:recover', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (21, 'totp:view', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (22, 'totp:write', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (23, 'service_account:manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (24, 'certificate:manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (25, 'api_key:manage', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (26, 'certificate:sign', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (27, 'api_key:read', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (28, 'dashboard:view', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (29, 'gui:view', NULL);
INSERT INTO `permission` (`id`, `code`, `detail`) VALUES (30, 'admin:impersonate', NULL);

-- role
INSERT INTO `role` (`id`, `name`) VALUES (1, 'admin');
INSERT INTO `role` (`id`, `name`) VALUES (2, 'manager');
INSERT INTO `role` (`id`, `name`) VALUES (3, 'member');
INSERT INTO `role` (`id`, `name`) VALUES (4, 'guest');

-- user
INSERT INTO `user` (`id`, `email`, `username`, `password_hash`, `created_at`, `totp_secret`, `is_active`, `refresh_token_hash`, `must_change_password`) VALUES (1, 'admin@example.com', 'admin', 'scrypt:32768:8:1$7oTcIUdekNLXGSXC$fd0f3320bde4570c7e1ea9d9d289aeb916db7a50fb62489a7e89d99c6cc576813506fd99f50904101c1eb85ff925f8dc879df5ded781ef2613224d702938c9c8', '2026-07-10 23:09:15', NULL, 1, NULL, 0);

-- role_permissions
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 1);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 2);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 3);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 4);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 5);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 6);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 7);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 8);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 9);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 10);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 11);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 12);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 13);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 14);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 15);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 16);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 17);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 18);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 19);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 20);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 21);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 22);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 23);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 24);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 25);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 26);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 27);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 28);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 29);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (1, 30);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 1);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 5);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 6);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 7);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 8);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 9);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 17);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 18);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 19);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 20);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 28);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (2, 29);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (3, 7);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (3, 8);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (3, 28);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (3, 29);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (4, 28);
INSERT INTO `role_permissions` (`role_id`, `perm_id`) VALUES (4, 29);

-- user_roles
INSERT INTO `user_roles` (`user_id`, `role_id`) VALUES (1, 1);

SET FOREIGN_KEY_CHECKS=1;
