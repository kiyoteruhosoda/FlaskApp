"""バックアップファイルの自動クリーンアップタスク"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from core.logging_config import setup_task_logging, log_task_error, log_task_info

logger = setup_task_logging(__name__)


def cleanup_old_backups(backup_dir: str = None, retention_days: int = 30) -> dict:
    """
    指定されたディレクトリ内の古いバックアップファイルを削除する
    
    Args:
        backup_dir: バックアップディレクトリのパス（指定がない場合は環境変数から取得）
        retention_days: 保持日数（デフォルト30日）
    
    Returns:
        dict: 実行結果の詳細
    """
    try:
        # バックアップディレクトリの決定
        if backup_dir is None:
            # 環境変数から取得、またはデフォルトパス
            backup_dir = os.environ.get('BACKUP_DIR', '/app/data/backups')
        
        backup_path = Path(backup_dir)
        
        # ディレクトリが存在しない場合は作成
        if not backup_path.exists():
            backup_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"バックアップディレクトリを作成しました: {backup_path}")
            return {"ok": True, "message": "バックアップディレクトリを作成しました", "deleted_files": []}
        
        # 現在時刻から保持日数を引いた日時
        cutoff_time = datetime.now() - timedelta(days=retention_days)
        
        deleted_files = []
        total_deleted_size = 0
        
        # .sqlファイルのクリーンアップ
        sql_files = list(backup_path.glob("*.sql"))
        for sql_file in sql_files:
            file_mtime = datetime.fromtimestamp(sql_file.stat().st_mtime)
            if file_mtime < cutoff_time:
                file_size = sql_file.stat().st_size
                sql_file.unlink()
                deleted_files.append({
                    "file": str(sql_file.name),
                    "size": file_size,
                    "modified": file_mtime.isoformat()
                })
                total_deleted_size += file_size
                logger.info(f"古いSQLバックアップファイルを削除: {sql_file.name}")
        
        # .tar.gzファイルのクリーンアップ
        archive_files = list(backup_path.glob("*.tar.gz"))
        for archive_file in archive_files:
            file_mtime = datetime.fromtimestamp(archive_file.stat().st_mtime)
            if file_mtime < cutoff_time:
                file_size = archive_file.stat().st_size
                archive_file.unlink()
                deleted_files.append({
                    "file": str(archive_file.name),
                    "size": file_size,
                    "modified": file_mtime.isoformat()
                })
                total_deleted_size += file_size
                logger.info(f"古いアーカイブバックアップファイルを削除: {archive_file.name}")
        
        # .backupファイルのクリーンアップ（設定ファイルバックアップ）
        backup_files = list(backup_path.glob("*.backup"))
        for backup_file in backup_files:
            file_mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
            if file_mtime < cutoff_time:
                file_size = backup_file.stat().st_size
                backup_file.unlink()
                deleted_files.append({
                    "file": str(backup_file.name),
                    "size": file_size,
                    "modified": file_mtime.isoformat()
                })
                total_deleted_size += file_size
                logger.info(f"古い設定バックアップファイルを削除: {backup_file.name}")
        
        result = {
            "ok": True,
            "backup_dir": str(backup_path),
            "retention_days": retention_days,
            "deleted_files_count": len(deleted_files),
            "total_deleted_size": total_deleted_size,
            "deleted_files": deleted_files,
            "timestamp": datetime.now().isoformat()
        }
        
        if deleted_files:
            logger.info(f"バックアップクリーンアップ完了: {len(deleted_files)}個のファイル ({total_deleted_size} bytes) を削除")
        else:
            logger.info("削除対象のバックアップファイルはありませんでした")
        
        return result
        
    except Exception as e:
        error_msg = f"バックアップクリーンアップ中にエラーが発生: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "ok": False,
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }


def get_backup_status(backup_dir: str = None) -> dict:
    """
    バックアップディレクトリの状況を取得する
    
    Args:
        backup_dir: バックアップディレクトリのパス
    
    Returns:
        dict: バックアップ状況の詳細
    """
    try:
        if backup_dir is None:
            backup_dir = os.environ.get('BACKUP_DIR', '/app/data/backups')
        
        backup_path = Path(backup_dir)
        
        if not backup_path.exists():
            return {
                "ok": True,
                "backup_dir": str(backup_path),
                "exists": False,
                "message": "バックアップディレクトリが存在しません"
            }
        
        # ファイル種別ごとの統計
        sql_files = list(backup_path.glob("*.sql"))
        archive_files = list(backup_path.glob("*.tar.gz"))
        backup_files = list(backup_path.glob("*.backup"))
        
        total_size = sum(f.stat().st_size for f in sql_files + archive_files + backup_files)
        
        # 最新ファイルの情報
        all_files = sql_files + archive_files + backup_files
        if all_files:
            latest_file = max(all_files, key=lambda f: f.stat().st_mtime)
            latest_mtime = datetime.fromtimestamp(latest_file.stat().st_mtime)
        else:
            latest_file = None
            latest_mtime = None
        
        return {
            "ok": True,
            "backup_dir": str(backup_path),
            "exists": True,
            "sql_files": len(sql_files),
            "archive_files": len(archive_files),
            "config_backup_files": len(backup_files),
            "total_files": len(all_files),
            "total_size": total_size,
            "latest_file": str(latest_file.name) if latest_file else None,
            "latest_modified": latest_mtime.isoformat() if latest_mtime else None,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        error_msg = f"バックアップ状況取得中にエラーが発生: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "ok": False,
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }
