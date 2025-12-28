# バックアップファイル自動クリーンアップ機能

## 概要
nolumiaのバックアップファイル（データベースダンプ、メディアアーカイブ、設定ファイル）を自動的にクリーンアップするCelery Beatタスクです。

## 機能
- 古いバックアップファイルの自動削除（デフォルト: 30日より古い）
- 対象ファイル: `.sql`, `.tar.gz`, `.backup`
- バックアップディレクトリの状況監視
- 削除ログとサイズ統計

## 設定

### 環境変数（.env）
```bash
# バックアップディレクトリ
SYSTEM_BACKUP_DIRECTORY=/app/data/backups

# 保持期間（日数）
BACKUP_RETENTION_DAYS=30
```

### Celery Beat スケジュール
- **タスク名**: `backup_cleanup.cleanup`
- **実行頻度**: 毎日1回（午前2時頃推奨）
- **保持期間**: 30日（設定可能）

## ファイル構成
- `core/tasks/backup_cleanup.py` - メイン処理
- `cli/src/celery/tasks.py` - Celeryタスク定義
- `cli/src/celery/celery_app.py` - Beatスケジュール設定
- `tests/test_backup_cleanup.py` - テストコード

## 使用方法

### 手動実行
```python
from core.tasks.backup_cleanup import cleanup_old_backups, get_backup_status

# クリーンアップ実行
result = cleanup_old_backups(retention_days=30)

# 状況確認
status = get_backup_status()
```

### Celeryタスクとして実行
```bash
# クリーンアップ実行
celery -A cli.src.celery.celery_app call backup_cleanup.cleanup

# 状況確認
celery -A cli.src.celery.celery_app call backup_cleanup.status
```

## ログ例
```
INFO: バックアップクリーンアップ完了: 5個のファイル (1234567 bytes) を削除
INFO: 古いSQLバックアップファイルを削除: old_backup_20240701_120000.sql
INFO: 古いアーカイブバックアップファイルを削除: old_media_20240701_120000.tar.gz
```

## 注意事項
- メディアファイルのバックアップ（.tar.gz）は容量が大きいため、自動実行は慎重に検討してください
- 旧名称 `MEDIA_BACKUP_DIRECTORY` も互換目的で解釈されますが、新規設定では `SYSTEM_BACKUP_DIRECTORY` を使用してください
- Synology環境では `/volume1/docker/photonest/backups` を使用
- 削除されたファイルは復元できません
