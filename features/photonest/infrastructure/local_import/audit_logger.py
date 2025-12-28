"""Local Import監査ログシステム

状態遷移、エラー、パフォーマンスを構造化してDB保存します。
トラブルシューティングと分析のための完全なトレーサビリティを提供します。
"""

from __future__ import annotations

import json
import logging
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LogLevel(str, Enum):
    """ログレベル"""
    
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogCategory(str, Enum):
    """ログカテゴリ"""
    
    STATE_TRANSITION = "state_transition"  # 状態遷移
    FILE_OPERATION = "file_operation"      # ファイル操作
    DB_OPERATION = "db_operation"          # DB操作
    VALIDATION = "validation"              # バリデーション
    DUPLICATE_CHECK = "duplicate_check"    # 重複チェック
    ERROR = "error"                        # エラー
    PERFORMANCE = "performance"            # パフォーマンス
    CONSISTENCY = "consistency"            # 整合性チェック


@dataclass
class AuditLogEntry:
    """監査ログエントリ
    
    すべてのログはこの構造でDB保存されます。
    """
    
    # 基本情報
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    level: LogLevel = LogLevel.INFO
    category: LogCategory = LogCategory.FILE_OPERATION
    message: str = ""
    
    # コンテキスト
    session_id: Optional[int] = None
    item_id: Optional[str] = None
    request_id: Optional[str] = None
    task_id: Optional[str] = None
    user_id: Optional[str] = None
    
    # 詳細データ
    details: dict[str, Any] = field(default_factory=dict)
    
    # エラー情報
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    
    # 推奨アクション
    recommended_actions: list[str] = field(default_factory=list)
    
    # パフォーマンス情報
    duration_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        """辞書に変換"""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["level"] = self.level.value
        data["category"] = self.category.value
        return data
    
    def to_json(self) -> str:
        """JSON文字列に変換"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class StateTransitionLog(AuditLogEntry):
    """状態遷移ログ"""
    
    category: LogCategory = field(default=LogCategory.STATE_TRANSITION, init=False)
    
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    reason: Optional[str] = None
    
    def __post_init__(self):
        if not self.message:
            self.message = f"状態遷移: {self.from_state} -> {self.to_state}"


@dataclass
class ErrorLog(AuditLogEntry):
    """エラーログ"""
    
    level: LogLevel = field(default=LogLevel.ERROR, init=False)
    category: LogCategory = field(default=LogCategory.ERROR, init=False)
    
    error_code: Optional[str] = None
    is_retryable: bool = False
    retry_count: int = 0
    
    def __post_init__(self):
        if self.is_retryable:
            self.recommended_actions.append(
                f"リトライ可能（現在{self.retry_count}回目）"
            )


@dataclass
class PerformanceLog(AuditLogEntry):
    """パフォーマンスログ"""
    
    level: LogLevel = field(default=LogLevel.INFO, init=False)
    category: LogCategory = field(default=LogCategory.PERFORMANCE, init=False)
    
    operation_name: Optional[str] = None
    file_size_bytes: Optional[int] = None
    throughput_mbps: Optional[float] = None
    
    def __post_init__(self):
        if not self.message and self.operation_name:
            self.message = f"{self.operation_name}完了"


@dataclass
class ConsistencyLog(AuditLogEntry):
    """整合性チェックログ"""
    
    category: LogCategory = field(default=LogCategory.CONSISTENCY, init=False)
    
    is_consistent: bool = True
    issues: list[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.is_consistent:
            self.level = LogLevel.ERROR
            self.message = f"整合性エラー検出: {len(self.issues)}件"


class AuditLogger:
    """監査ログ記録器
    
    構造化されたログをDB保存します。
    大量データ対策としてJSONサイズを制限します。
    """
    
    # 定数: JSON最大サイズ（MariaDBの制約を考慮）
    MAX_DETAILS_SIZE_BYTES = 900_000  # 900KB（余裕を持って1MB未満）
    MAX_ACTIONS_COUNT = 50            # 推奨アクション最大50件
    MAX_ARRAY_ITEMS = 10              # 配列の最大要素数（切り詰め対象）
    
    def __init__(self, log_repository):
        """
        Args:
            log_repository: ログリポジトリ（DB保存を担当）
        """
        self._repo = log_repository
    
    def log(self, entry: AuditLogEntry) -> None:
        """ログを記録（サイズ制限付き）
        
        Args:
            entry: ログエントリ
        """
        # 1. detailsのサイズチェックと切り詰め
        entry.details = self._truncate_details(entry.details)
        
        # 2. recommended_actionsの件数制限
        if len(entry.recommended_actions) > self.MAX_ACTIONS_COUNT:
            original_count = len(entry.recommended_actions)
            entry.recommended_actions = entry.recommended_actions[:self.MAX_ACTIONS_COUNT]
            entry.recommended_actions.append(
                f"（残り{original_count - self.MAX_ACTIONS_COUNT}件省略）"
            )
        
        # DBに保存
        try:
            self._repo.save(entry)
        except Exception as e:
            logger.error(
                f"ログのDB保存に失敗: {e}",
                exc_info=True,
                extra={"log_entry": entry.to_dict()},
            )
        
        # 標準ロガーにも出力
        log_method = getattr(logger, entry.level.value)
        log_method(
            entry.message,
            extra={
                "category": entry.category.value,
                "session_id": entry.session_id,
                "item_id": entry.item_id,
                "details": entry.details,
            },
        )
        def _truncate_details(self, details: dict) -> dict:
        """detailsを切り詰め（大量データ対策）
        
        Args:
            details: 元の詳細データ
            
        Returns:
            dict: 切り詰めたデータ（900KB以内）
        """
        if not details:
            return details
        
        # JSON文字列に変換してサイズ確認
        json_str = json.dumps(details, ensure_ascii=False)
        size_bytes = len(json_str.encode('utf-8'))
        
        if size_bytes <= self.MAX_DETAILS_SIZE_BYTES:
            return details  # サイズOK
        
        # サイズ超過: 配列を切り詰め
        truncated = {}
        for key, value in details.items():
            if isinstance(value, list) and len(value) > self.MAX_ARRAY_ITEMS:
                # 配列は最初の5件と最後の5件のみ保存
                truncated[key] = {
                    "_truncated": True,
                    "_original_count": len(value),
                    "first_items": value[:5],
                    "last_items": value[-5:],
                }
            elif isinstance(value, dict):
                # ネストした辞書は再帰的に処理
                truncated[key] = self._truncate_details(value)
            else:
                truncated[key] = value
        
        # 再度サイズチェック
        json_str = json.dumps(truncated, ensure_ascii=False)
        size_bytes = len(json_str.encode('utf-8'))
        
        if size_bytes > self.MAX_DETAILS_SIZE_BYTES:
            # それでも超過する場合はサマリーのみ
            return {
                "_truncated": True,
                "_reason": "サイズ超過により詳細を省略",
                "_original_size_bytes": size_bytes,
                "keys": list(details.keys()),
                "summary": "大量データのためサマリーのみ表示",
            }
        
        return truncated
        def log_state_transition(
        self,
        from_state: str,
        to_state: str,
        reason: str,
        session_id: Optional[int] = None,
        item_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """状態遷移を記録"""
        entry = StateTransitionLog(
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            session_id=session_id,
            item_id=item_id,
            details=metadata or {},
        )
        self.log(entry)
    
    def log_error(
        self,
        message: str,
        exception: Optional[Exception] = None,
        session_id: Optional[int] = None,
        item_id: Optional[str] = None,
        error_code: Optional[str] = None,
        is_retryable: bool = False,
        recommended_actions: Optional[list[str]] = None,
    ) -> None:
        """エラーを記録"""
        entry = ErrorLog(
            message=message,
            session_id=session_id,
            item_id=item_id,
            error_code=error_code,
            is_retryable=is_retryable,
            recommended_actions=recommended_actions or [],
        )
        
        if exception:
            entry.error_type = type(exception).__name__
            entry.error_message = str(exception)
            entry.stack_trace = traceback.format_exc()
        
        self.log(entry)
    
    def log_performance(
        self,
        operation_name: str,
        duration_ms: float,
        session_id: Optional[int] = None,
        item_id: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """パフォーマンスを記録"""
        throughput = None
        if file_size_bytes and duration_ms > 0:
            # スループットをMB/sで計算
            throughput = (file_size_bytes / (1024 * 1024)) / (duration_ms / 1000)
        
        entry = PerformanceLog(
            operation_name=operation_name,
            duration_ms=duration_ms,
            session_id=session_id,
            item_id=item_id,
            file_size_bytes=file_size_bytes,
            throughput_mbps=throughput,
            details=metadata or {},
        )
        self.log(entry)
    
    def log_consistency_check(
        self,
        session_id: int,
        is_consistent: bool,
        issues: list[str],
        recommendations: list[str],
    ) -> None:
        """整合性チェック結果を記録"""
        entry = ConsistencyLog(
            session_id=session_id,
            is_consistent=is_consistent,
            issues=issues,
            recommended_actions=recommendations,
            details={
                "issue_count": len(issues),
                "recommendation_count": len(recommendations),
            },
        )
        self.log(entry)


class StructuredLogger:
    """構造化ログユーティリティ
    
    コンテキスト情報を保持しながらログを出力します。
    """
    
    def __init__(
        self,
        audit_logger: AuditLogger,
        session_id: Optional[int] = None,
        item_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        self._audit_logger = audit_logger
        self._session_id = session_id
        self._item_id = item_id
        self._request_id = request_id
    
    def with_context(
        self,
        session_id: Optional[int] = None,
        item_id: Optional[str] = None,
    ) -> StructuredLogger:
        """コンテキストを追加した新しいロガーを作成"""
        return StructuredLogger(
            self._audit_logger,
            session_id=session_id or self._session_id,
            item_id=item_id or self._item_id,
            request_id=self._request_id,
        )
    
    def info(
        self,
        message: str,
        category: LogCategory = LogCategory.FILE_OPERATION,
        **details,
    ) -> None:
        """情報ログ"""
        entry = AuditLogEntry(
            level=LogLevel.INFO,
            category=category,
            message=message,
            session_id=self._session_id,
            item_id=self._item_id,
            request_id=self._request_id,
            details=details,
        )
        self._audit_logger.log(entry)
    
    def warning(
        self,
        message: str,
        category: LogCategory = LogCategory.FILE_OPERATION,
        recommended_actions: Optional[list[str]] = None,
        **details,
    ) -> None:
        """警告ログ"""
        entry = AuditLogEntry(
            level=LogLevel.WARNING,
            category=category,
            message=message,
            session_id=self._session_id,
            item_id=self._item_id,
            request_id=self._request_id,
            recommended_actions=recommended_actions or [],
            details=details,
        )
        self._audit_logger.log(entry)
    
    def error(
        self,
        message: str,
        exception: Optional[Exception] = None,
        category: LogCategory = LogCategory.ERROR,
        error_code: Optional[str] = None,
        is_retryable: bool = False,
        recommended_actions: Optional[list[str]] = None,
        **details,
    ) -> None:
        """エラーログ"""
        self._audit_logger.log_error(
            message=message,
            exception=exception,
            session_id=self._session_id,
            item_id=self._item_id,
            error_code=error_code,
            is_retryable=is_retryable,
            recommended_actions=recommended_actions,
        )
    
    def state_transition(
        self,
        from_state: str,
        to_state: str,
        reason: str,
        **metadata,
    ) -> None:
        """状態遷移ログ"""
        self._audit_logger.log_state_transition(
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            session_id=self._session_id,
            item_id=self._item_id,
            metadata=metadata,
        )
    
    def performance(
        self,
        operation_name: str,
        duration_ms: float,
        file_size_bytes: Optional[int] = None,
        **metadata,
    ) -> None:
        """パフォーマンスログ"""
        self._audit_logger.log_performance(
            operation_name=operation_name,
            duration_ms=duration_ms,
            session_id=self._session_id,
            item_id=self._item_id,
            file_size_bytes=file_size_bytes,
            metadata=metadata,
        )


def create_error_log_with_actions(
    message: str,
    error: Exception,
    context: dict,
) -> dict:
    """エラーログと推奨アクションを生成
    
    エラーの種類に応じて適切な推奨アクションを自動生成します。
    
    Args:
        message: エラーメッセージ
        error: 例外オブジェクト
        context: コンテキスト情報
        
    Returns:
        dict: ログデータ
    """
    error_type = type(error).__name__
    recommended_actions = []
    
    # エラータイプ別の推奨アクション
    if error_type == "FileNotFoundError":
        recommended_actions = [
            "ファイルパスを確認してください",
            "ファイルが移動または削除されていないか確認してください",
            "ディレクトリのアクセス権限を確認してください",
        ]
    elif error_type in ("PermissionError", "OSError"):
        recommended_actions = [
            "ファイル/ディレクトリのアクセス権限を確認してください",
            "他のプロセスがファイルを使用していないか確認してください",
            "ディスク容量を確認してください",
        ]
    elif error_type == "ValueError":
        recommended_actions = [
            "入力データの形式を確認してください",
            "必須パラメータが不足していないか確認してください",
        ]
    elif error_type in ("ConnectionError", "TimeoutError"):
        recommended_actions = [
            "ネットワーク接続を確認してください",
            "しばらく待ってからリトライしてください",
            "外部サービスの状態を確認してください",
        ]
    elif error_type == "IntegrityError":
        recommended_actions = [
            "データベースの整合性を確認してください",
            "重複するデータがないか確認してください",
            "外部キー制約違反がないか確認してください",
        ]
    else:
        recommended_actions = [
            f"エラーの詳細を確認してください: {error}",
            "ログファイルで前後の処理を確認してください",
            "必要に応じてサポートに連絡してください",
        ]
    
    return {
        "message": message,
        "error_type": error_type,
        "error_message": str(error),
        "stack_trace": traceback.format_exc(),
        "recommended_actions": recommended_actions,
        "context": context,
    }
