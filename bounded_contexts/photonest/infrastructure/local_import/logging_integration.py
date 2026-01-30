"""Local Import Phase 1統合: ログシステム追加

既存のImportLogEmitterに加えて、構造化ログを並行して記録します。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.db import db
from bounded_contexts.photonest.infrastructure.local_import.audit_logger import (
    AuditLogger,
    LogCategory,
    StructuredLogger,
)
from bounded_contexts.photonest.infrastructure.local_import.audit_log_repository import (
    AuditLogRepository,
)

logger = logging.getLogger(__name__)

# グローバルな構造化ログインスタンス（初期化は init_audit_logger で実施）
_global_audit_logger: Optional[AuditLogger] = None
_global_structured_logger: Optional[StructuredLogger] = None


def init_audit_logger() -> None:
    """監査ロガーを初期化
    
    アプリケーション起動時またはタスク開始時に呼び出す。
    """
    global _global_audit_logger, _global_structured_logger
    
    try:
        audit_log_repo = AuditLogRepository(db.session)
        _global_audit_logger = AuditLogger(audit_log_repo)
        _global_structured_logger = StructuredLogger(_global_audit_logger)
        
        logger.info("監査ロガーを初期化しました")
    except Exception as e:
        logger.warning(f"監査ロガーの初期化に失敗（フォールバック動作）: {e}")
        # フォールバックとして何もしない


def get_audit_logger() -> Optional[AuditLogger]:
    """監査ロガーを取得"""
    return _global_audit_logger


def get_structured_logger(
    session_id: Optional[int] = None,
    item_id: Optional[str] = None,
) -> Optional[StructuredLogger]:
    """構造化ロガーを取得
    
    Args:
        session_id: セッションID
        item_id: アイテムID
        
    Returns:
        StructuredLogger or None: ロガーが初期化されていない場合はNone
    """
    if not _global_audit_logger:
        return None
    
    if session_id or item_id:
        return StructuredLogger(_global_audit_logger, session_id, item_id)
    
    return _global_structured_logger


def log_with_audit(
    message: str,
    level: str = "info",
    category: str = "file_operation",
    session_id: Optional[int] = None,
    item_id: Optional[str] = None,
    **details: Any,
) -> None:
    """監査ログ付きでログを記録
    
    既存のログシステムに加えて、構造化ログも記録します。
    
    Args:
        message: ログメッセージ
        level: ログレベル (info, warning, error)
        category: カテゴリ
        session_id: セッションID
        item_id: アイテムID
        **details: 詳細情報
    """
    structured_logger = get_structured_logger(session_id, item_id)
    
    if not structured_logger:
        # フォールバック: 標準ロガーのみ
        return
    
    try:
        # カテゴリを変換
        log_category = LogCategory(category)
        
        # レベルに応じてログ記録
        if level == "warning":
            structured_logger.warning(message, category=log_category, **details)
        elif level == "error":
            structured_logger.error(message, category=log_category, **details)
        else:
            structured_logger.info(message, category=log_category, **details)
    except Exception as e:
        logger.warning(f"構造化ログの記録に失敗: {e}")


def log_file_operation(
    message: str,
    file_path: str,
    operation: str,
    session_id: Optional[int] = None,
    item_id: Optional[str] = None,
    **details: Any,
) -> None:
    """ファイル操作ログを記録
    
    Args:
        message: メッセージ
        file_path: ファイルパス
        operation: 操作名（move, copy, delete等）
        session_id: セッションID
        item_id: アイテムID
        **details: 追加詳細
    """
    log_with_audit(
        message,
        level="info",
        category="file_operation",
        session_id=session_id,
        item_id=item_id,
        file_path=file_path,
        operation=operation,
        **details,
    )


def log_duplicate_check(
    message: str,
    file_hash: str,
    match_type: str,
    session_id: Optional[int] = None,
    item_id: Optional[str] = None,
    **details: Any,
) -> None:
    """重複チェックログを記録
    
    Args:
        message: メッセージ
        file_hash: ファイルハッシュ
        match_type: マッチタイプ（exact, perceptual, cryptographic等）
        session_id: セッションID
        item_id: アイテムID
        **details: 追加詳細
    """
    log_with_audit(
        message,
        level="info",
        category="duplicate_check",
        session_id=session_id,
        item_id=item_id,
        file_hash=file_hash,
        match_type=match_type,
        **details,
    )


def log_error_with_actions(
    message: str,
    error: Exception,
    recommended_actions: list[str],
    session_id: Optional[int] = None,
    item_id: Optional[str] = None,
    **details: Any,
) -> None:
    """エラーと推奨アクションをログ記録
    
    Args:
        message: エラーメッセージ
        error: 例外オブジェクト
        recommended_actions: 推奨アクション
        session_id: セッションID
        item_id: アイテムID
        **details: 追加詳細
    """
    structured_logger = get_structured_logger(session_id, item_id)
    
    if not structured_logger:
        return
    
    try:
        structured_logger.error(
            message,
            exception=error,
            recommended_actions=recommended_actions,
            **details,
        )
    except Exception as e:
        logger.warning(f"エラーログの記録に失敗: {e}")


def log_performance(
    operation_name: str,
    duration_ms: float,
    session_id: Optional[int] = None,
    item_id: Optional[str] = None,
    file_size_bytes: Optional[int] = None,
    **details: Any,
) -> None:
    """パフォーマンスログを記録
    
    Args:
        operation_name: 操作名
        duration_ms: 処理時間（ミリ秒）
        session_id: セッションID
        item_id: アイテムID
        file_size_bytes: ファイルサイズ（バイト）
        **details: 追加詳細
    """
    structured_logger = get_structured_logger(session_id, item_id)
    
    if not structured_logger:
        return
    
    try:
        structured_logger.performance(
            operation_name=operation_name,
            duration_ms=duration_ms,
            file_size_bytes=file_size_bytes,
            **details,
        )
    except Exception as e:
        logger.warning(f"パフォーマンスログの記録に失敗: {e}")
