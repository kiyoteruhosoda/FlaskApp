"""トランザクション管理サービス."""
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, Protocol, TypeVar
from contextlib import contextmanager


T = TypeVar('T')


class DatabaseSession(Protocol):
    """データベースセッションのプロトコル."""
    
    def commit(self) -> None:
        """トランザクションをコミット."""
        ...
    
    def rollback(self) -> None:
        """トランザクションをロールバック."""
        ...
    
    def flush(self) -> None:
        """変更をフラッシュ."""
        ...


class Logger(Protocol):
    """ロガーのプロトコル."""
    
    def error(
        self,
        event: str,
        message: str,
        *,
        exc_info: bool = False,
        **details: Any,
    ) -> None:
        """エラーログを記録."""
        ...


class TransactionManager:
    """トランザクション境界を管理するアプリケーションサービス.
    
    責務：
    - トランザクションの開始・コミット・ロールバック
    - エラー時のロールバックと詳細ログ記録
    """
    
    def __init__(self, session: DatabaseSession, logger: Logger) -> None:
        self._session = session
        self._logger = logger
    
    @contextmanager
    def transaction(
        self,
        *,
        event: str,
        description: str,
        **context: Any,
    ):
        """トランザクションコンテキストマネージャ.
        
        Args:
            event: イベント名（ログ用）
            description: 説明（ログ用）
            **context: コンテキスト情報（ログ用）
            
        Yields:
            DatabaseSession
            
        Raises:
            例外が発生した場合はロールバック後に再送出
        """
        try:
            yield self._session
            self._session.commit()
        except Exception as exc:
            self._session.rollback()
            self._logger.error(
                event,
                f"{description}中にエラーが発生: {str(exc)}",
                exc_info=True,
                error_type=type(exc).__name__,
                error_message=str(exc),
                **context,
            )
            raise
    
    def commit_with_logging(
        self,
        *,
        event: str,
        description: str,
        **context: Any,
    ) -> bool:
        """コミットを試行し、失敗時は詳細ログを記録.
        
        Args:
            event: イベント名（ログ用）
            description: 説明（ログ用）
            **context: コンテキスト情報（ログ用）
            
        Returns:
            成功時True、失敗時False
        """
        try:
            self._session.commit()
            return True
        except Exception as exc:
            self._session.rollback()
            self._logger.error(
                event,
                f"{description}中にエラーが発生: {str(exc)}",
                exc_info=True,
                error_type=type(exc).__name__,
                error_message=str(exc),
                **context,
            )
            return False
