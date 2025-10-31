-- MariaDB dump 10.19  Distrib 10.11.6-MariaDB, for Linux (x86_64)
--
-- Host: localhost    Database: 
-- ------------------------------------------------------
-- Server version	10.11.6-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Current Database: `appdb`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `appdb` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */;

USE `appdb`;

--
-- Table structure for table `album`
--

DROP TABLE IF EXISTS `album`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `album` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `cover_media_id` bigint(20) DEFAULT NULL,
  `visibility` enum('public','private','unlisted') NOT NULL,
  `display_order` int(11) DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `cover_media_id` (`cover_media_id`),
  CONSTRAINT `album_ibfk_1` FOREIGN KEY (`cover_media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `album`
--

LOCK TABLES `album` WRITE;
/*!40000 ALTER TABLE `album` DISABLE KEYS */;
/*!40000 ALTER TABLE `album` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `album_item`
--

DROP TABLE IF EXISTS `album_item`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `album_item` (
  `album_id` bigint(20) NOT NULL,
  `media_id` bigint(20) NOT NULL,
  `sort_index` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`album_id`,`media_id`),
  KEY `media_id` (`media_id`),
  CONSTRAINT `album_item_ibfk_1` FOREIGN KEY (`album_id`) REFERENCES `album` (`id`),
  CONSTRAINT `album_item_ibfk_2` FOREIGN KEY (`media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `album_item`
--

LOCK TABLES `album_item` WRITE;
/*!40000 ALTER TABLE `album_item` DISABLE KEYS */;
/*!40000 ALTER TABLE `album_item` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `celery_task`
--

DROP TABLE IF EXISTS `celery_task`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `celery_task` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `task_name` varchar(255) NOT NULL,
  `object_type` varchar(64) DEFAULT NULL,
  `object_id` varchar(255) DEFAULT NULL,
  `celery_task_id` varchar(255) DEFAULT NULL,
  `status` enum('scheduled','queued','running','success','failed','canceled') NOT NULL DEFAULT 'queued',
  `scheduled_for` datetime DEFAULT NULL,
  `started_at` datetime DEFAULT NULL,
  `finished_at` datetime DEFAULT NULL,
  `payload_json` text NOT NULL DEFAULT '{}',
  `result_json` text DEFAULT NULL,
  `error_message` text DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `celery_task_id` (`celery_task_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `celery_task`
--

LOCK TABLES `celery_task` WRITE;
/*!40000 ALTER TABLE `celery_task` DISABLE KEYS */;
/*!40000 ALTER TABLE `celery_task` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `certificate_events`
--

DROP TABLE IF EXISTS `certificate_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `certificate_events` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `actor` varchar(255) NOT NULL,
  `action` varchar(64) NOT NULL,
  `target_kid` varchar(64) DEFAULT NULL,
  `target_group_code` varchar(64) DEFAULT NULL,
  `reason` text DEFAULT NULL,
  `details` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`details`)),
  `occurred_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `ix_certificate_events_target_kid` (`target_kid`),
  KEY `ix_certificate_events_target_group_code` (`target_group_code`),
  KEY `ix_certificate_events_occurred_at` (`occurred_at`),
  CONSTRAINT `ck_certificate_events_details_json` CHECK (json_valid(`details`))
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `certificate_events`
--

LOCK TABLES `certificate_events` WRITE;
/*!40000 ALTER TABLE `certificate_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `certificate_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `certificate_groups`
--

DROP TABLE IF EXISTS `certificate_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `certificate_groups` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `group_code` varchar(64) NOT NULL,
  `display_name` varchar(128) DEFAULT NULL,
  `auto_rotate` tinyint(1) NOT NULL DEFAULT 1,
  `rotation_threshold_days` int(11) NOT NULL,
  `key_type` varchar(16) NOT NULL,
  `key_curve` varchar(32) DEFAULT NULL,
  `key_size` int(11) DEFAULT NULL,
  `subject` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`subject`)),
  `usage_type` varchar(32) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_certificate_groups_group_code` (`group_code`),
  KEY `ix_certificate_groups_usage_type` (`usage_type`),
  CONSTRAINT `ck_certificate_groups_subject_json` CHECK (json_valid(`subject`))
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `certificate_groups`
--

LOCK TABLES `certificate_groups` WRITE;
/*!40000 ALTER TABLE `certificate_groups` DISABLE KEYS */;
/*!40000 ALTER TABLE `certificate_groups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `certificate_private_keys`
--

DROP TABLE IF EXISTS `certificate_private_keys`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `certificate_private_keys` (
  `kid` varchar(64) NOT NULL,
  `group_id` bigint(20) DEFAULT NULL,
  `private_key_pem` text NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `expires_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`kid`),
  KEY `fk_certificate_private_keys_group_id_certificate_groups` (`group_id`),
  KEY `ix_certificate_private_keys_created_at` (`created_at`),
  KEY `ix_certificate_private_keys_expires_at` (`expires_at`),
  CONSTRAINT `fk_certificate_private_keys_group_id_certificate_groups` FOREIGN KEY (`group_id`) REFERENCES `certificate_groups` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_certificate_private_keys_kid_issued_certificates` FOREIGN KEY (`kid`) REFERENCES `issued_certificates` (`kid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `certificate_private_keys`
--

LOCK TABLES `certificate_private_keys` WRITE;
/*!40000 ALTER TABLE `certificate_private_keys` DISABLE KEYS */;
/*!40000 ALTER TABLE `certificate_private_keys` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `exif`
--

DROP TABLE IF EXISTS `exif`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `exif` (
  `media_id` bigint(20) NOT NULL,
  `camera_make` varchar(255) DEFAULT NULL,
  `camera_model` varchar(255) DEFAULT NULL,
  `lens` varchar(255) DEFAULT NULL,
  `iso` int(11) DEFAULT NULL,
  `shutter` varchar(32) DEFAULT NULL,
  `f_number` decimal(5,2) DEFAULT NULL,
  `focal_len` decimal(5,2) DEFAULT NULL,
  `gps_lat` decimal(10,7) DEFAULT NULL,
  `gps_lng` decimal(10,7) DEFAULT NULL,
  `raw_json` text DEFAULT NULL,
  PRIMARY KEY (`media_id`),
  CONSTRAINT `exif_ibfk_1` FOREIGN KEY (`media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `exif`
--

LOCK TABLES `exif` WRITE;
/*!40000 ALTER TABLE `exif` DISABLE KEYS */;
/*!40000 ALTER TABLE `exif` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `google_account`
--

DROP TABLE IF EXISTS `google_account`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `google_account` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) DEFAULT NULL,
  `email` varchar(255) NOT NULL,
  `status` varchar(20) NOT NULL,
  `scopes` text NOT NULL,
  `last_synced_at` datetime DEFAULT NULL,
  `oauth_token_json` text DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_google_email` (`user_id`,`email`),
  CONSTRAINT `google_account_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `google_account`
--

LOCK TABLES `google_account` WRITE;
/*!40000 ALTER TABLE `google_account` DISABLE KEYS */;
/*!40000 ALTER TABLE `google_account` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `issued_certificates`
--

DROP TABLE IF EXISTS `issued_certificates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `issued_certificates` (
  `kid` varchar(64) NOT NULL,
  `usage_type` varchar(32) NOT NULL,
  `certificate_pem` text NOT NULL,
  `jwk` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`jwk`)),
  `issued_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `revoked_at` datetime(6) DEFAULT NULL,
  `revocation_reason` text DEFAULT NULL,
  `group_id` bigint(20) DEFAULT NULL,
  `expires_at` datetime(6) DEFAULT NULL,
  `auto_rotated_from_kid` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`kid`),
  KEY `ix_issued_certificates_usage_type` (`usage_type`),
  KEY `ix_issued_certificates_issued_at` (`issued_at`),
  KEY `ix_issued_certificates_expires_at` (`expires_at`),
  KEY `fk_issued_certificates_group_id_certificate_groups` (`group_id`),
  CONSTRAINT `fk_issued_certificates_group_id_certificate_groups` FOREIGN KEY (`group_id`) REFERENCES `certificate_groups` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `issued_certificates`
--

LOCK TABLES `issued_certificates` WRITE;
/*!40000 ALTER TABLE `issued_certificates` DISABLE KEYS */;
/*!40000 ALTER TABLE `issued_certificates` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `job_sync`
--

DROP TABLE IF EXISTS `job_sync`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `job_sync` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `target` varchar(50) NOT NULL,
  `account_id` bigint(20) DEFAULT NULL,
  `session_id` bigint(20) DEFAULT NULL,
  `started_at` datetime NOT NULL,
  `finished_at` datetime DEFAULT NULL,
  `status` enum('queued','running','success','partial','failed','canceled') NOT NULL DEFAULT 'queued',
  `stats_json` text NOT NULL DEFAULT '{}',
  `celery_task_id` bigint(20) DEFAULT NULL,
  `task_name` varchar(255) NOT NULL DEFAULT '',
  `queue_name` varchar(120) DEFAULT NULL,
  `trigger` varchar(32) NOT NULL DEFAULT 'worker',
  `args_json` text NOT NULL DEFAULT '{}',
  PRIMARY KEY (`id`),
  KEY `session_id` (`session_id`),
  KEY `job_sync_celery_task_id_fkey` (`celery_task_id`),
  CONSTRAINT `job_sync_celery_task_id_fkey` FOREIGN KEY (`celery_task_id`) REFERENCES `celery_task` (`id`),
  CONSTRAINT `job_sync_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `picker_session` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `job_sync`
--

LOCK TABLES `job_sync` WRITE;
/*!40000 ALTER TABLE `job_sync` DISABLE KEYS */;
/*!40000 ALTER TABLE `job_sync` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `log`
--

DROP TABLE IF EXISTS `log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `log` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `level` varchar(50) NOT NULL,
  `event` varchar(50) NOT NULL,
  `message` text NOT NULL,
  `trace` text DEFAULT NULL,
  `path` varchar(255) DEFAULT NULL,
  `request_id` varchar(36) DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `log`
--

LOCK TABLES `log` WRITE;
/*!40000 ALTER TABLE `log` DISABLE KEYS */;
/*!40000 ALTER TABLE `log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `media`
--

DROP TABLE IF EXISTS `media`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `media` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `source_type` enum('local','google_photos','wiki-media') NOT NULL,
  `google_media_id` varchar(255) DEFAULT NULL,
  `account_id` bigint(20) DEFAULT NULL,
  `local_rel_path` varchar(255) DEFAULT NULL,
  `filename` varchar(255) DEFAULT NULL,
  `hash_sha256` char(64) DEFAULT NULL,
  `bytes` bigint(20) DEFAULT NULL,
  `mime_type` varchar(255) DEFAULT NULL,
  `width` int(11) DEFAULT NULL,
  `height` int(11) DEFAULT NULL,
  `duration_ms` int(11) DEFAULT NULL,
  `orientation` int(11) DEFAULT NULL,
  `is_video` tinyint(1) NOT NULL,
  `shot_at` datetime DEFAULT NULL,
  `camera_make` varchar(255) DEFAULT NULL,
  `camera_model` varchar(255) DEFAULT NULL,
  `imported_at` datetime NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `has_playback` tinyint(1) NOT NULL,
  `live_group_id` bigint(20) DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  `thumbnail_rel_path` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `account_id` (`account_id`),
  CONSTRAINT `media_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `google_account` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `media`
--

LOCK TABLES `media` WRITE;
/*!40000 ALTER TABLE `media` DISABLE KEYS */;
/*!40000 ALTER TABLE `media` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `media_item`
--

DROP TABLE IF EXISTS `media_item`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `media_item` (
  `id` varchar(255) NOT NULL,
  `type` enum('TYPE_UNSPECIFIED','PHOTO','VIDEO') NOT NULL,
  `mime_type` varchar(255) DEFAULT NULL,
  `filename` varchar(255) DEFAULT NULL,
  `width` int(11) DEFAULT NULL,
  `height` int(11) DEFAULT NULL,
  `camera_make` varchar(255) DEFAULT NULL,
  `camera_model` varchar(255) DEFAULT NULL,
  `photo_metadata_id` bigint(20) DEFAULT NULL,
  `video_metadata_id` bigint(20) DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `photo_metadata_id` (`photo_metadata_id`),
  KEY `video_metadata_id` (`video_metadata_id`),
  CONSTRAINT `media_item_ibfk_1` FOREIGN KEY (`photo_metadata_id`) REFERENCES `photo_metadata` (`id`),
  CONSTRAINT `media_item_ibfk_2` FOREIGN KEY (`video_metadata_id`) REFERENCES `video_metadata` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `media_item`
--

LOCK TABLES `media_item` WRITE;
/*!40000 ALTER TABLE `media_item` DISABLE KEYS */;
/*!40000 ALTER TABLE `media_item` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `media_playback`
--

DROP TABLE IF EXISTS `media_playback`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `media_playback` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `media_id` bigint(20) NOT NULL,
  `preset` enum('original','preview','mobile','std1080p') NOT NULL,
  `rel_path` varchar(255) DEFAULT NULL,
  `width` int(11) DEFAULT NULL,
  `height` int(11) DEFAULT NULL,
  `v_codec` varchar(32) DEFAULT NULL,
  `a_codec` varchar(32) DEFAULT NULL,
  `v_bitrate_kbps` int(11) DEFAULT NULL,
  `duration_ms` int(11) DEFAULT NULL,
  `poster_rel_path` varchar(255) DEFAULT NULL,
  `hash_sha256` char(64) DEFAULT NULL,
  `status` enum('pending','processing','done','error') NOT NULL,
  `error_msg` text DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `media_id` (`media_id`),
  CONSTRAINT `media_playback_ibfk_1` FOREIGN KEY (`media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1   DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `media_playback`
--

LOCK TABLES `media_playback` WRITE;
/*!40000 ALTER TABLE `media_playback` DISABLE KEYS */;
/*!40000 ALTER TABLE `media_playback` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `media_sidecar`
--

DROP TABLE IF EXISTS `media_sidecar`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `media_sidecar` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `media_id` bigint(20) NOT NULL,
  `type` enum('video','audio','subtitle') NOT NULL,
  `rel_path` varchar(255) DEFAULT NULL,
  `bytes` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `media_id` (`media_id`),
  CONSTRAINT `media_sidecar_ibfk_1` FOREIGN KEY (`media_id`) REFERENCES `media` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `media_sidecar`
--

LOCK TABLES `media_sidecar` WRITE;
/*!40000 ALTER TABLE `media_sidecar` DISABLE KEYS */;
/*!40000 ALTER TABLE `media_sidecar` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `media_tag`
--

DROP TABLE IF EXISTS `media_tag`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `media_tag` (
  `media_id` bigint(20) NOT NULL,
  `tag_id` bigint(20) NOT NULL,
  PRIMARY KEY (`media_id`,`tag_id`),
  KEY `tag_id` (`tag_id`),
  CONSTRAINT `media_tag_ibfk_1` FOREIGN KEY (`media_id`) REFERENCES `media` (`id`),
  CONSTRAINT `media_tag_ibfk_2` FOREIGN KEY (`tag_id`) REFERENCES `tag` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `media_tag`
--

LOCK TABLES `media_tag` WRITE;
/*!40000 ALTER TABLE `media_tag` DISABLE KEYS */;
/*!40000 ALTER TABLE `media_tag` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `media_thumbnail_retry`
--

DROP TABLE IF EXISTS `media_thumbnail_retry`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `media_thumbnail_retry` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `media_id` bigint(20) NOT NULL,
  `retry_after` datetime NOT NULL,
  `force` tinyint(1) NOT NULL DEFAULT 0,
  `celery_task_id` varchar(255) DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_media_thumbnail_retry_media_id` (`media_id`),
  CONSTRAINT `fk_media_thumbnail_retry_media_id` FOREIGN KEY (`media_id`) REFERENCES `media` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `media_thumbnail_retry`
--

LOCK TABLES `media_thumbnail_retry` WRITE;
/*!40000 ALTER TABLE `media_thumbnail_retry` DISABLE KEYS */;
/*!40000 ALTER TABLE `media_thumbnail_retry` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `permission`
--

DROP TABLE IF EXISTS `permission`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `permission` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `code` varchar(120) NOT NULL,
  `detail` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `permission`
--

LOCK TABLES `permission` WRITE;
/*!40000 ALTER TABLE `permission` DISABLE KEYS */;
INSERT INTO `permission` (`id`,`code`,`detail`) VALUES
(2,'admin:job-settings',NULL),
(1,'admin:photo-settings',NULL),
(4,'album:create',NULL),
(5,'album:edit',NULL),
(6,'album:view',NULL),
(21,'api_key:manage',NULL),
(23,'api_key:read',NULL),
(20,'certificate:manage',NULL),
(22,'certificate:sign',NULL),
(15,'media:delete',NULL),
(16,'media:recover',NULL),
(26,'media:session',NULL),
(14,'media:tag-manage',NULL),
(25,'media:metadata-manage',NULL),
(7,'media:view',NULL),
(8,'permission:manage',NULL),
(9,'role:manage',NULL),
(19,'service_account:manage',NULL),
(10,'system:manage',NULL),
(17,'totp:view',NULL),
(18,'totp:write',NULL),
(3,'user:manage',NULL),
(27,'group:manage',NULL),
(26,'dashboard:view',NULL),
(24,'gui:view',NULL),
(11,'wiki:admin',NULL),
(12,'wiki:read',NULL),
(13,'wiki:write',NULL);
/*!40000 ALTER TABLE `permission` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `photo_metadata`
--

DROP TABLE IF EXISTS `photo_metadata`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `photo_metadata` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `focal_length` float DEFAULT NULL,
  `aperture_f_number` float DEFAULT NULL,
  `iso_equivalent` int(11) DEFAULT NULL,
  `exposure_time` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `photo_metadata`
--

LOCK TABLES `photo_metadata` WRITE;
/*!40000 ALTER TABLE `photo_metadata` DISABLE KEYS */;
/*!40000 ALTER TABLE `photo_metadata` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `picker_import_task`
--

DROP TABLE IF EXISTS `picker_import_task`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `picker_import_task` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `picker_import_task`
--

LOCK TABLES `picker_import_task` WRITE;
/*!40000 ALTER TABLE `picker_import_task` DISABLE KEYS */;
/*!40000 ALTER TABLE `picker_import_task` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `picker_selection`
--

DROP TABLE IF EXISTS `picker_selection`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `picker_selection` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `session_id` bigint(20) NOT NULL,
  `google_media_id` varchar(255) DEFAULT NULL,
  `local_file_path` text DEFAULT NULL,
  `local_filename` varchar(500) DEFAULT NULL,
  `status` enum('pending','enqueued','running','imported','dup','failed','expired','skipped') NOT NULL DEFAULT 'pending',
  `create_time` datetime DEFAULT NULL,
  `enqueued_at` datetime DEFAULT NULL,
  `started_at` datetime DEFAULT NULL,
  `finished_at` datetime DEFAULT NULL,
  `attempts` int(11) NOT NULL DEFAULT 0,
  `error_msg` text DEFAULT NULL,
  `base_url` text DEFAULT NULL,
  `base_url_fetched_at` datetime DEFAULT NULL,
  `base_url_valid_until` datetime DEFAULT NULL,
  `locked_by` varchar(255) DEFAULT NULL,
  `lock_heartbeat_at` datetime DEFAULT NULL,
  `last_transition_at` datetime DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_picker_selection_session_media` (`session_id`,`google_media_id`),
  KEY `google_media_id` (`google_media_id`),
  KEY `idx_picker_selection_session_status` (`session_id`,`status`),
  KEY `idx_picker_selection_status_lock` (`status`,`lock_heartbeat_at`),
  CONSTRAINT `picker_selection_ibfk_1` FOREIGN KEY (`google_media_id`) REFERENCES `media_item` (`id`),
  CONSTRAINT `picker_selection_ibfk_2` FOREIGN KEY (`session_id`) REFERENCES `picker_session` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `picker_selection`
--

LOCK TABLES `picker_selection` WRITE;
/*!40000 ALTER TABLE `picker_selection` DISABLE KEYS */;
/*!40000 ALTER TABLE `picker_selection` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `picker_session`
--

DROP TABLE IF EXISTS `picker_session`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `picker_session` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `account_id` bigint(20) DEFAULT NULL,
  `session_id` varchar(255) DEFAULT NULL,
  `picker_uri` text DEFAULT NULL,
  `expire_time` datetime DEFAULT NULL,
  `polling_config_json` text DEFAULT NULL,
  `picking_config_json` text DEFAULT NULL,
  `media_items_set` tinyint(1) DEFAULT NULL,
  `status` enum('pending','ready','processing','enqueued','importing','imported','canceled','expired','error','failed','expanding') NOT NULL DEFAULT 'pending',
  `selected_count` int(11) DEFAULT NULL,
  `stats_json` text DEFAULT NULL,
  `last_polled_at` datetime DEFAULT NULL,
  `last_progress_at` datetime DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `session_id` (`session_id`),
  KEY `account_id` (`account_id`),
  CONSTRAINT `picker_session_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `google_account` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `picker_session`
--

LOCK TABLES `picker_session` WRITE;
/*!40000 ALTER TABLE `picker_session` DISABLE KEYS */;
/*!40000 ALTER TABLE `picker_session` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role`
--

DROP TABLE IF EXISTS `role`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `role` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(80) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role`
--

LOCK TABLES `role` WRITE;
/*!40000 ALTER TABLE `role` DISABLE KEYS */;
INSERT INTO `role` VALUES
(1,'admin'),
(2,'director'),
(3,'member'),
(4,'guest'),
(5,'sign admin');
/*!40000 ALTER TABLE `role` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_permissions`
--

DROP TABLE IF EXISTS `role_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `role_permissions` (
  `role_id` bigint(20) NOT NULL,
  `perm_id` bigint(20) NOT NULL,
  PRIMARY KEY (`role_id`,`perm_id`),
  KEY `perm_id` (`perm_id`),
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`perm_id`) REFERENCES `permission` (`id`),
  CONSTRAINT `role_permissions_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `role` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_permissions`
--

LOCK TABLES `role_permissions` WRITE;
/*!40000 ALTER TABLE `role_permissions` DISABLE KEYS */;
INSERT INTO `role_permissions` VALUES
(1,1),
(1,2),
(1,3),
(1,4),
(1,5),
(1,6),
(1,7),
(1,8),
(1,9),
(1,27),
(1,10),
(1,11),
(1,12),
(1,13),
(1,14),
(1,25),
(1,15),
(1,16),
(1,17),
(1,18),
(1,19),
(1,20),
(1,21),
(1,22),
(1,23),
(1,24),
(1,25),
(1,26),
(2,4),
(2,5),
(2,6),
(2,7),
(3,6),
(3,7),
(3,26),
(4,26),
(5,20);
/*!40000 ALTER TABLE `role_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_account`
--

DROP TABLE IF EXISTS `service_account`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `service_account` (
  `service_account_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `certificate_group_code` varchar(64) DEFAULT NULL,
  `jtk_endpoint` varchar(500) DEFAULT NULL,
  `scope_names` varchar(1000) NOT NULL DEFAULT '',
  `active_flg` tinyint(1) NOT NULL DEFAULT 1,
  `reg_dttm` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `mod_dttm` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  `jwt_endpoint` varchar(500) DEFAULT NULL,
  PRIMARY KEY (`service_account_id`),
  UNIQUE KEY `name` (`name`),
  KEY `fk_service_account_certificate_group_code` (`certificate_group_code`),
  CONSTRAINT `fk_service_account_certificate_group_code` FOREIGN KEY (`certificate_group_code`) REFERENCES `certificate_groups` (`group_code`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_account`
--

LOCK TABLES `service_account` WRITE;
/*!40000 ALTER TABLE `service_account` DISABLE KEYS */;
/*!40000 ALTER TABLE `service_account` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_account_api_key`
--

DROP TABLE IF EXISTS `service_account_api_key`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `service_account_api_key` (
  `api_key_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `service_account_id` bigint(20) NOT NULL,
  `public_id` varchar(32) NOT NULL,
  `secret_hash` varchar(255) NOT NULL,
  `scope_names` varchar(2000) NOT NULL,
  `expires_at` datetime(6) DEFAULT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `created_by` varchar(255) NOT NULL,
  PRIMARY KEY (`api_key_id`),
  UNIQUE KEY `uq_service_account_api_key_public_id` (`public_id`),
  KEY `ix_service_account_api_key_service_account_id` (`service_account_id`),
  CONSTRAINT `fk_service_account_api_key_service_account` FOREIGN KEY (`service_account_id`) REFERENCES `service_account` (`service_account_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_account_api_key`
--

LOCK TABLES `service_account_api_key` WRITE;
/*!40000 ALTER TABLE `service_account_api_key` DISABLE KEYS */;
/*!40000 ALTER TABLE `service_account_api_key` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_account_api_key_log`
--

DROP TABLE IF EXISTS `service_account_api_key_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `service_account_api_key_log` (
  `log_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `api_key_id` bigint(20) NOT NULL,
  `accessed_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `ip_address` varchar(64) DEFAULT NULL,
  `endpoint` varchar(255) DEFAULT NULL,
  `user_agent` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`log_id`),
  KEY `ix_service_account_api_key_log_api_key_id` (`api_key_id`),
  CONSTRAINT `fk_service_account_api_key_log_api_key` FOREIGN KEY (`api_key_id`) REFERENCES `service_account_api_key` (`api_key_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_account_api_key_log`
--

LOCK TABLES `service_account_api_key_log` WRITE;
/*!40000 ALTER TABLE `service_account_api_key_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `service_account_api_key_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `system_settings`
--

DROP TABLE IF EXISTS `system_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `system_settings` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `setting_key` varchar(100) NOT NULL,
  `setting_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`setting_json`)),
  `description` text DEFAULT NULL,
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `setting_key` (`setting_key`),
  CONSTRAINT `ck_system_settings_json_valid` CHECK (json_valid(`setting_json`))
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `system_settings`
--

LOCK TABLES `system_settings` WRITE;
/*!40000 ALTER TABLE `system_settings` DISABLE KEYS */;
/*!40000 ALTER TABLE `system_settings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tag`
--

DROP TABLE IF EXISTS `tag`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `tag` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `attr` enum('person','place','thing') NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `created_by` bigint(20) DEFAULT NULL,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `created_by` (`created_by`),
  CONSTRAINT `tag_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `user` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tag`
--

LOCK TABLES `tag` WRITE;
/*!40000 ALTER TABLE `tag` DISABLE KEYS */;
/*!40000 ALTER TABLE `tag` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_group`
--

DROP TABLE IF EXISTS `user_group`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `user_group` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(120) NOT NULL,
  `description` text DEFAULT NULL,
  `parent_id` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_group_name` (`name`),
  KEY `ix_user_group_parent_id` (`parent_id`),
  CONSTRAINT `fk_user_group_parent` FOREIGN KEY (`parent_id`) REFERENCES `user_group` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_group`
--

LOCK TABLES `user_group` WRITE;
/*!40000 ALTER TABLE `user_group` DISABLE KEYS */;
/*!40000 ALTER TABLE `user_group` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `totp_credential`
--

DROP TABLE IF EXISTS `totp_credential`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `totp_credential` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) DEFAULT NULL,
  `account` varchar(255) NOT NULL,
  `issuer` varchar(255) NOT NULL,
  `secret` varchar(160) NOT NULL,
  `description` text DEFAULT NULL,
  `algorithm` varchar(16) NOT NULL DEFAULT 'SHA1',
  `digits` smallint(6) NOT NULL DEFAULT 6,
  `period` smallint(6) NOT NULL DEFAULT 30,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_totp_user_account_issuer` (`user_id`,`account`,`issuer`),
  KEY `ix_totp_credential_user_id` (`user_id`),
  CONSTRAINT `fk_totp_credential_user_id_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `totp_credential`
--

LOCK TABLES `totp_credential` WRITE;
/*!40000 ALTER TABLE `totp_credential` DISABLE KEYS */;
/*!40000 ALTER TABLE `totp_credential` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user`
--

DROP TABLE IF EXISTS `user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `user` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `username` varchar(80) DEFAULT NULL,
  `password_hash` varchar(255) NOT NULL,
  `totp_secret` varchar(32) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL,
  `refresh_token_hash` varchar(255) DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_user_email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user`
--

LOCK TABLES `user` WRITE;
/*!40000 ALTER TABLE `user` DISABLE KEYS */;
INSERT INTO `user` VALUES
(-1,'admin@example.com','admin','scrypt:32768:8:1$7oTcIUdekNLXGSXC$fd0f3320bde4570c7e1ea9d9d289aeb916db7a50fb62489a7e89d99c6cc576813506fd99f50904101c1eb85ff925f8dc879df5ded781ef2613224d702938c9c8','2025-09-23 10:17:33',NULL,1,NULL);
/*!40000 ALTER TABLE `user` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `group_user_membership`
--

DROP TABLE IF EXISTS `group_user_membership`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `group_user_membership` (
  `group_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  PRIMARY KEY (`group_id`,`user_id`),
  UNIQUE KEY `uq_group_user_membership` (`group_id`,`user_id`),
  KEY `fk_group_membership_user` (`user_id`),
  CONSTRAINT `fk_group_membership_group` FOREIGN KEY (`group_id`) REFERENCES `user_group` (`id`),
  CONSTRAINT `fk_group_membership_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `group_user_membership`
--

LOCK TABLES `group_user_membership` WRITE;
/*!40000 ALTER TABLE `group_user_membership` DISABLE KEYS */;
/*!40000 ALTER TABLE `group_user_membership` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `user_roles` (
  `user_id` bigint(20) NOT NULL,
  `role_id` bigint(20) NOT NULL,
  PRIMARY KEY (`user_id`,`role_id`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `user_roles_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `role` (`id`),
  CONSTRAINT `user_roles_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_roles`
--

LOCK TABLES `user_roles` WRITE;
/*!40000 ALTER TABLE `user_roles` DISABLE KEYS */;
INSERT INTO `user_roles` VALUES
(-1,1);
/*!40000 ALTER TABLE `user_roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `video_metadata`
--

DROP TABLE IF EXISTS `video_metadata`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `video_metadata` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `fps` float DEFAULT NULL,
  `processing_status` enum('UNSPECIFIED','PROCESSING','READY','FAILED') DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `video_metadata`
--

LOCK TABLES `video_metadata` WRITE;
/*!40000 ALTER TABLE `video_metadata` DISABLE KEYS */;
/*!40000 ALTER TABLE `video_metadata` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `wiki_category`
--

DROP TABLE IF EXISTS `wiki_category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `wiki_category` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `slug` varchar(100) NOT NULL,
  `sort_order` int(11) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_wiki_category_slug` (`slug`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `wiki_category`
--

LOCK TABLES `wiki_category` WRITE;
/*!40000 ALTER TABLE `wiki_category` DISABLE KEYS */;
/*!40000 ALTER TABLE `wiki_category` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `wiki_page`
--

DROP TABLE IF EXISTS `wiki_page`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `wiki_page` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `content` text NOT NULL,
  `slug` varchar(255) NOT NULL,
  `is_published` tinyint(1) NOT NULL,
  `parent_id` bigint(20) DEFAULT NULL,
  `sort_order` int(11) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  `created_by_id` bigint(20) NOT NULL,
  `updated_by_id` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_wiki_page_slug` (`slug`),
  KEY `created_by_id` (`created_by_id`),
  KEY `parent_id` (`parent_id`),
  KEY `updated_by_id` (`updated_by_id`),
  CONSTRAINT `wiki_page_ibfk_1` FOREIGN KEY (`created_by_id`) REFERENCES `user` (`id`),
  CONSTRAINT `wiki_page_ibfk_2` FOREIGN KEY (`parent_id`) REFERENCES `wiki_page` (`id`),
  CONSTRAINT `wiki_page_ibfk_3` FOREIGN KEY (`updated_by_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `wiki_page`
--

LOCK TABLES `wiki_page` WRITE;
/*!40000 ALTER TABLE `wiki_page` DISABLE KEYS */;
/*!40000 ALTER TABLE `wiki_page` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `wiki_page_category`
--

DROP TABLE IF EXISTS `wiki_page_category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `wiki_page_category` (
  `page_id` bigint(20) NOT NULL,
  `category_id` bigint(20) NOT NULL,
  PRIMARY KEY (`page_id`,`category_id`),
  KEY `category_id` (`category_id`),
  CONSTRAINT `wiki_page_category_ibfk_1` FOREIGN KEY (`category_id`) REFERENCES `wiki_category` (`id`),
  CONSTRAINT `wiki_page_category_ibfk_2` FOREIGN KEY (`page_id`) REFERENCES `wiki_page` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `wiki_page_category`
--

LOCK TABLES `wiki_page_category` WRITE;
/*!40000 ALTER TABLE `wiki_page_category` DISABLE KEYS */;
/*!40000 ALTER TABLE `wiki_page_category` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `wiki_revision`
--

DROP TABLE IF EXISTS `wiki_revision`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `wiki_revision` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `page_id` bigint(20) NOT NULL,
  `title` varchar(255) NOT NULL,
  `content` text NOT NULL,
  `revision_number` int(11) NOT NULL,
  `change_summary` varchar(500) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `created_by_id` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `created_by_id` (`created_by_id`),
  KEY `page_id` (`page_id`),
  CONSTRAINT `wiki_revision_ibfk_1` FOREIGN KEY (`created_by_id`) REFERENCES `user` (`id`),
  CONSTRAINT `wiki_revision_ibfk_2` FOREIGN KEY (`page_id`) REFERENCES `wiki_page` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `wiki_revision`
--

LOCK TABLES `wiki_revision` WRITE;
/*!40000 ALTER TABLE `wiki_revision` DISABLE KEYS */;
/*!40000 ALTER TABLE `wiki_revision` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `worker_log`
--

DROP TABLE IF EXISTS `worker_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `worker_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `level` varchar(20) NOT NULL,
  `event` varchar(50) NOT NULL,
  `logger_name` varchar(120) DEFAULT NULL,
  `task_name` varchar(255) DEFAULT NULL,
  `task_uuid` char(36) DEFAULT NULL,
  `worker_hostname` varchar(255) DEFAULT NULL,
  `queue_name` varchar(120) DEFAULT NULL,
  `status` varchar(40) DEFAULT NULL,
  `message` text NOT NULL,
  `trace` text DEFAULT NULL,
  `meta_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`meta_json`)),
  `extra_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`extra_json`)),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `worker_log`
--

LOCK TABLES `worker_log` WRITE;
/*!40000 ALTER TABLE `worker_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `worker_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `passkey_credential`
--

DROP TABLE IF EXISTS `passkey_credential`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `passkey_credential` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `credential_id` VARCHAR(255) NOT NULL,
  `public_key` TEXT NOT NULL,
  `sign_count` BIGINT NOT NULL DEFAULT 0,
  `transports` JSON DEFAULT NULL,
  `name` VARCHAR(255) DEFAULT NULL,
  `attestation_format` VARCHAR(64) DEFAULT NULL,
  `aaguid` VARCHAR(64) DEFAULT NULL,
  `backup_eligible` BOOLEAN NOT NULL DEFAULT FALSE,
  `backup_state` BOOLEAN NOT NULL DEFAULT FALSE,
  `last_used_at` DATETIME(6) DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_passkey_credential_id` (`credential_id`),
  KEY `ix_passkey_credential_user_id` (`user_id`),
  CONSTRAINT `fk_passkey_credential_user_id_user`
    FOREIGN KEY (`user_id`) REFERENCES `user` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `worker_log`
--

LOCK TABLES `passkey_credential` WRITE;
/*!40000 ALTER TABLE `worker_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `worker_log` ENABLE KEYS */;
UNLOCK TABLES;

