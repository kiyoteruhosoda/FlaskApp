"""Session recovery tasks for cleaning up stale processing sessions."""

import json
from datetime import datetime, timedelta
from core.models.picker_session import PickerSession
from core.db import db
from core.logging_config import setup_task_logging, log_task_error, log_task_info
import logging

logger = setup_task_logging(__name__)


def cleanup_stale_sessions():
    """
    古い処理中セッションを厳密にクリーンアップする定期タスク。
    
    以下の条件をすべて満たすセッションをエラー状態に変更：
    1. ステータスが 'processing'
    2. 最終更新から一定時間経過（セッションタイプに応じて調整）
    3. Celeryワーカーで実際のタスクが実行されていない
    
    タイムアウト時間:
    - ローカルインポート: 2時間（大量ファイル・動画変換考慮）
    - その他: 1時間
    
    Returns:
        dict: {"ok": bool, "updated_count": int, "message": str, "details": list}
    """
    try:
        from cli.src.celery.celery_app import celery
        
        # Celeryで現在実行中のタスクを取得
        inspect = celery.control.inspect()
        active_tasks = inspect.active()
        active_session_ids = set()
        active_task_details = []

        if active_tasks:
            for worker_name, tasks in active_tasks.items():
                for task in tasks:
                    # タスクの引数からsession_idを抽出
                    session_id = None
                    if task.get('args') and len(task['args']) > 0:
                        try:
                            # local_import_task_celery(session_id) の場合
                            session_id = task['args'][0]
                            if isinstance(session_id, str):
                                active_session_ids.add(session_id)
                        except (IndexError, TypeError):
                            session_id = None

                    task_summary = {
                        'worker': worker_name,
                        'task_name': task.get('name'),
                        'task_id': task.get('id'),
                        'session_id': session_id,
                        'args': task.get('args', []),
                    }
                    active_task_details.append(task_summary)
        logger.info(
            json.dumps(
                {
                    'message': 'Active Celery tasks snapshot',
                    'active_task_count': len(active_task_details),
                    'active_session_ids': sorted(active_session_ids),
                    'tasks': active_task_details,
                },
                ensure_ascii=False,
                default=str,
            ),
            extra={'event': 'session_recovery'},
        )
        
        # 各タイプのタイムアウト時間を定義
        timeout_configs = {
            'local_import': timedelta(hours=2),    # ローカルインポート: 2時間
            'picker_import': timedelta(hours=1),   # Picker インポート: 1時間  
            'default': timedelta(hours=1)          # その他: 1時間
        }
        
        updated_sessions = []
        total_updated = 0
        
        for session_type, timeout_delta in timeout_configs.items():
            cutoff_time = datetime.now() - timeout_delta
            
            # セッションタイプに応じたクエリ条件
            if session_type == 'local_import':
                query_filter = PickerSession.session_id.like('local-import-%')
            elif session_type == 'picker_import':
                query_filter = PickerSession.session_id.like('picker-%')
            else:
                # デフォルト: 上記以外のすべて
                query_filter = ~(
                    PickerSession.session_id.like('local-import-%') |
                    PickerSession.session_id.like('picker-%')
                )
            
            stale_sessions = PickerSession.query.filter(
                PickerSession.status == 'processing',
                query_filter,
                PickerSession.updated_at < cutoff_time  # created_at ではなく updated_at で判定
            ).all()
            
            for session in stale_sessions:
                # Celeryで実際に実行中の場合はスキップ
                if session.session_id in active_session_ids:
                    logger.info(
                        json.dumps(
                            {
                                'message': 'Session still active in Celery, skipping cleanup',
                                'session_id': session.session_id,
                                'session_type': session_type,
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                        extra={'event': 'session_recovery'},
                    )
                    continue

                logger.warning(
                    json.dumps(
                        {
                            'message': 'Cleaning up stale session',
                            'session_id': session.session_id,
                            'session_type': session_type,
                            'last_updated': session.updated_at,
                            'timeout_seconds': int(timeout_delta.total_seconds()),
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                    extra={'event': 'session_recovery'},
                )
                
                session.status = 'error'
                session.error_message = (
                    f'セッションがタイムアウトしました（{session_type}タイプ、'
                    f'タイムアウト時間: {timeout_delta}）。'
                    'Celeryワーカーの停止またはタスクの異常終了により処理が中断された可能性があります。'
                    f' (自動リカバリ実行時刻: {datetime.now()})'
                )
                session.updated_at = datetime.now()
                
                updated_sessions.append({
                    'session_id': session.session_id,
                    'type': session_type,
                    'last_updated': session.updated_at,
                    'timeout_used': str(timeout_delta)
                })
                total_updated += 1
        
        if total_updated > 0:
            db.session.commit()
            logger.warning(
                json.dumps(
                    {
                        'message': 'Session recovery updated stale sessions to error state',
                        'updated_count': total_updated,
                        'sessions': updated_sessions,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                extra={'event': 'session_recovery'},
            )
            return {
                "ok": True,
                "updated_count": total_updated,
                "message": f"{total_updated}個の古いセッションをエラー状態に更新しました",
                "details": updated_sessions
            }
        else:
            logger.debug(
                json.dumps(
                    {
                        'message': 'Session recovery found no stale sessions',
                        'active_session_ids': sorted(active_session_ids),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                extra={'event': 'session_recovery'},
            )
            return {
                "ok": True,
                "updated_count": 0,
                "message": "クリーンアップが必要なセッションはありませんでした",
                "details": []
            }

    except Exception as e:
        logger.error(
            json.dumps(
                {
                    'message': 'Session recovery failed',
                    'error': str(e),
                },
                ensure_ascii=False,
            ),
            extra={'event': 'session_recovery'},
        )
        db.session.rollback()
        return {
            "ok": False,
            "updated_count": 0,
            "message": f"セッションリカバリでエラーが発生しました: {str(e)}",
            "details": []
        }


def get_session_status_report():
    """
    現在のセッション状況とCeleryタスクの詳細レポートを生成する（デバッグ用）。
    
    Returns:
        dict: 詳細なステータス情報
    """
    try:
        from cli.src.celery.celery_app import celery
        
        # Celeryタスクの状況取得
        inspect = celery.control.inspect()
        active_tasks = inspect.active() or {}
        scheduled_tasks = inspect.scheduled() or {}
        
        # データベースのセッション状況
        processing_sessions = PickerSession.query.filter(
            PickerSession.status == 'processing'
        ).all()
        
        # 実行中セッションIDの抽出
        active_session_ids = set()
        active_task_details = []
        
        for worker_name, tasks in active_tasks.items():
            for task in tasks:
                task_info = {
                    'worker': worker_name,
                    'task_name': task.get('name'),
                    'task_id': task.get('id'),
                    'args': task.get('args', [])
                }
                active_task_details.append(task_info)
                
                # session_idの抽出
                if task.get('args') and len(task['args']) > 0:
                    try:
                        session_id = task['args'][0]
                        if isinstance(session_id, str):
                            active_session_ids.add(session_id)
                    except (IndexError, TypeError):
                        pass
        
        # セッション分析
        session_analysis = []
        for session in processing_sessions:
            age_since_created = datetime.now() - session.created_at
            age_since_updated = datetime.now() - session.updated_at
            is_active_in_celery = session.session_id in active_session_ids
            
            # セッションタイプ判定
            if session.session_id.startswith('local-import-'):
                session_type = 'local_import'
                timeout_threshold = timedelta(hours=2)
            elif session.session_id.startswith('picker-'):
                session_type = 'picker_import'
                timeout_threshold = timedelta(hours=1)
            else:
                session_type = 'other'
                timeout_threshold = timedelta(hours=1)
            
            is_stale = age_since_updated > timeout_threshold and not is_active_in_celery
            
            session_analysis.append({
                'session_id': session.session_id,
                'status': session.status,
                'type': session_type,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'age_since_created_minutes': int(age_since_created.total_seconds() / 60),
                'age_since_updated_minutes': int(age_since_updated.total_seconds() / 60),
                'timeout_threshold_minutes': int(timeout_threshold.total_seconds() / 60),
                'is_active_in_celery': is_active_in_celery,
                'is_stale': is_stale,
                'would_be_cleaned': is_stale
            })
        
        return {
            'timestamp': datetime.now().isoformat(),
            'celery_workers_count': len(active_tasks.keys()),
            'active_tasks_count': sum(len(tasks) for tasks in active_tasks.values()),
            'scheduled_tasks_count': sum(len(tasks) for tasks in scheduled_tasks.values()),
            'processing_sessions_count': len(processing_sessions),
            'active_session_ids': list(active_session_ids),
            'active_task_details': active_task_details,
            'session_analysis': session_analysis,
            'stale_sessions_count': sum(1 for s in session_analysis if s['is_stale'])
        }
        
    except Exception as e:
        logger.error(f"Failed to generate session status report: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


def force_cleanup_all_processing_sessions():
    """
    全ての処理中セッションを強制的にエラー状態にする（緊急時用）。
    
    Returns:
        dict: {"ok": bool, "updated_count": int, "message": str}
    """
    try:
        processing_sessions = PickerSession.query.filter(
            PickerSession.status == 'processing'
        ).all()
        
        updated_count = 0
        for session in processing_sessions:
            logger.warning(
                json.dumps(
                    {
                        'message': 'Force cleaning session',
                        'session_db_id': session.id,
                        'session_id': session.session_id,
                        'status_before': session.status,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                extra={'event': 'session_recovery'},
            )
            session.status = 'error'
            session.error_message = (
                '強制クリーンアップによりセッションが終了されました。'
                f' (実行時刻: {datetime.now()})'
            )
            session.updated_at = datetime.now()
            updated_count += 1

        if updated_count > 0:
            db.session.commit()
            logger.warning(
                json.dumps(
                    {
                        'message': 'Force cleanup completed',
                        'updated_count': updated_count,
                    },
                    ensure_ascii=False,
                ),
                extra={'event': 'session_recovery'},
            )

        return {
            "ok": True,
            "updated_count": updated_count,
            "message": f"{updated_count}個のセッションを強制的にクリーンアップしました"
        }

    except Exception as e:
        logger.error(
            json.dumps(
                {
                    'message': 'Force cleanup failed',
                    'error': str(e),
                },
                ensure_ascii=False,
            ),
            extra={'event': 'session_recovery'},
        )
        db.session.rollback()
        return {
            "ok": False,
            "updated_count": 0,
            "message": f"強制クリーンアップでエラーが発生しました: {str(e)}"
        }
