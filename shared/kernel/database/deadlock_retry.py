"""MariaDB/InnoDB デッドロック（エラー 1213）発生時の再試行。

InnoDB はデッドロックを検出すると片方のトランザクションを強制ロールバックし
``(1213, 'Deadlock found when trying to get lock; try restarting transaction')``
を返す。MySQL/MariaDB の公式な推奨対応は「トランザクションを再実行する」こと
であり、本モジュールはその再実行を共通化する。

再試行前に必ず ``session.rollback()`` を呼ぶ。これを怠ると Session が
pending-rollback 状態のまま残り、同じ Session を共有する後続・並行の
クエリがすべて ``PendingRollbackError`` で失敗する（FastAPI では
``db.session`` がプロセス内で共有されるため被害が連鎖する）。
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

# MySQL/MariaDB: ER_LOCK_DEADLOCK
MYSQL_DEADLOCK_ERROR_CODE = 1213

DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 0.1

_T = TypeVar("_T")


def is_deadlock_error(exc: BaseException) -> bool:
    """例外が MySQL/MariaDB のデッドロック（1213）かどうかを判定する。"""
    if not isinstance(exc, OperationalError):
        return False
    orig_args = getattr(exc.orig, "args", ())
    return bool(orig_args) and orig_args[0] == MYSQL_DEADLOCK_ERROR_CODE


def run_with_deadlock_retry(
    operation: Callable[[], _T],
    *,
    session,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
) -> _T:
    """``operation`` を実行し、デッドロック時はロールバックして再試行する。

    ``operation`` はトランザクション全体（読み取り→更新→commit）を含む
    再実行安全な呼び出しであること。デッドロック以外の例外はそのまま送出する。
    最終試行でも失敗した場合はロールバック済みの状態で例外を送出する
    （Session を pending-rollback のまま残さない）。
    """
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except OperationalError as exc:
            if not is_deadlock_error(exc):
                raise
            # pending-rollback 状態を即座に解消する（並行クエリへの連鎖防止）
            session.rollback()
            if attempt >= attempts:
                logger.error(
                    "deadlock retry exhausted after %d attempts",
                    attempts,
                    extra={"event": "db.deadlock.retryExhausted"},
                )
                raise
            delay = base_delay_seconds * (2 ** (attempt - 1)) + random.uniform(
                0, base_delay_seconds
            )
            logger.warning(
                "deadlock detected (attempt %d/%d); retrying in %.3fs",
                attempt,
                attempts,
                delay,
                extra={"event": "db.deadlock.retry"},
            )
            time.sleep(delay)

    raise AssertionError("unreachable")  # pragma: no cover


__all__ = [
    "MYSQL_DEADLOCK_ERROR_CODE",
    "is_deadlock_error",
    "run_with_deadlock_retry",
]
