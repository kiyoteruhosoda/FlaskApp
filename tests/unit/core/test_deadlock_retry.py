"""``shared.kernel.database.deadlock_retry`` のユニットテスト。

取り込み中に status / logs / selections の並行ポーリングと Celery タスクが
同一 ``picker_session`` 行を更新して InnoDB デッドロック（1213）が発生し、
API が 500（OperationalError / 後続は PendingRollbackError）を返していた
退行の再発防止。デッドロック時はロールバック→再実行で回復すること、
デッドロック以外の例外は再試行せず素通しすることを確認する。
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.exc import OperationalError

from shared.kernel.database.deadlock_retry import (
    MYSQL_DEADLOCK_ERROR_CODE,
    is_deadlock_error,
    run_with_deadlock_retry,
)


def _deadlock_error() -> OperationalError:
    orig = Exception(
        MYSQL_DEADLOCK_ERROR_CODE,
        "Deadlock found when trying to get lock; try restarting transaction",
    )
    return OperationalError("UPDATE picker_session SET ...", {}, orig)


def _other_operational_error() -> OperationalError:
    orig = Exception(2013, "Lost connection to MySQL server during query")
    return OperationalError("SELECT 1", {}, orig)


# ---------------------------------------------------------------------------
# is_deadlock_error
# ---------------------------------------------------------------------------


def test_is_deadlock_error_detects_1213() -> None:
    assert is_deadlock_error(_deadlock_error()) is True


def test_is_deadlock_error_rejects_other_operational_errors() -> None:
    assert is_deadlock_error(_other_operational_error()) is False


def test_is_deadlock_error_rejects_non_operational_errors() -> None:
    assert is_deadlock_error(ValueError("x")) is False


# ---------------------------------------------------------------------------
# run_with_deadlock_retry
# ---------------------------------------------------------------------------


def test_returns_result_without_retry_on_success() -> None:
    session = MagicMock()
    result = run_with_deadlock_retry(lambda: "ok", session=session)
    assert result == "ok"
    session.rollback.assert_not_called()


def test_retries_after_rollback_on_deadlock() -> None:
    session = MagicMock()
    operation = MagicMock(side_effect=[_deadlock_error(), {"status": "imported"}])

    with (
        patch("shared.kernel.database.deadlock_retry.time.sleep") as sleep,
        patch("shared.kernel.database.deadlock_retry.random.uniform", return_value=0.0),
    ):
        result = run_with_deadlock_retry(operation, session=session)

    assert result == {"status": "imported"}
    assert operation.call_count == 2
    # 再試行前に必ず rollback して pending-rollback 状態を解消する
    session.rollback.assert_called_once()
    sleep.assert_called_once_with(pytest.approx(0.1))


def test_backoff_grows_exponentially() -> None:
    session = MagicMock()
    operation = MagicMock(
        side_effect=[_deadlock_error(), _deadlock_error(), "recovered"]
    )

    with (
        patch("shared.kernel.database.deadlock_retry.time.sleep") as sleep,
        patch("shared.kernel.database.deadlock_retry.random.uniform", return_value=0.0),
    ):
        result = run_with_deadlock_retry(operation, session=session)

    assert result == "recovered"
    assert sleep.call_args_list == [
        call(pytest.approx(0.1)),
        call(pytest.approx(0.2)),
    ]
    assert session.rollback.call_count == 2


def test_raises_after_exhausting_attempts_with_rollback() -> None:
    session = MagicMock()
    operation = MagicMock(side_effect=_deadlock_error())

    with (
        patch("shared.kernel.database.deadlock_retry.time.sleep"),
        patch("shared.kernel.database.deadlock_retry.random.uniform", return_value=0.0),
        pytest.raises(OperationalError),
    ):
        run_with_deadlock_retry(operation, session=session, attempts=3)

    assert operation.call_count == 3
    # 最終失敗時もロールバック済みで抜ける（Session を壊れたまま残さない）
    assert session.rollback.call_count == 3


def test_non_deadlock_error_propagates_without_retry() -> None:
    session = MagicMock()
    operation = MagicMock(side_effect=_other_operational_error())

    with pytest.raises(OperationalError):
        run_with_deadlock_retry(operation, session=session)

    assert operation.call_count == 1
    session.rollback.assert_not_called()


def test_non_operational_error_propagates_without_retry() -> None:
    session = MagicMock()
    operation = MagicMock(side_effect=ValueError("boom"))

    with pytest.raises(ValueError):
        run_with_deadlock_retry(operation, session=session)

    assert operation.call_count == 1
    session.rollback.assert_not_called()


# ---------------------------------------------------------------------------
# PickerSessionService.status がデッドロックから回復すること（配線の確認）
# ---------------------------------------------------------------------------


def test_picker_session_status_recovers_from_deadlock() -> None:
    from bounded_contexts.picker_import.application.picker_session_service import (
        PickerSessionService,
    )

    ps = MagicMock()
    expected = {"status": "imported"}

    with (
        patch.object(
            PickerSessionService,
            "_status_impl",
            side_effect=[_deadlock_error(), expected],
        ) as impl,
        patch(
            "bounded_contexts.picker_import.application.picker_session_service.db"
        ) as mock_db,
        patch("shared.kernel.database.deadlock_retry.time.sleep"),
        patch("shared.kernel.database.deadlock_retry.random.uniform", return_value=0.0),
    ):
        result = PickerSessionService.status(ps)

    assert result == expected
    assert impl.call_count == 2
    mock_db.session.rollback.assert_called_once()
