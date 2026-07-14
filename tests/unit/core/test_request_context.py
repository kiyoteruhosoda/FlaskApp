"""requestId コンテキスト（shared/kernel/logging/request_context.py）のテスト。"""
from __future__ import annotations

import logging

from shared.kernel.logging.request_context import (
    RequestIdLogFilter,
    bind_request_id,
    current_request_id,
    reset_request_id,
)


def _make_record() -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=None,
        exc_info=None,
    )


class TestRequestIdContext:
    def test_bind_and_reset(self) -> None:
        assert current_request_id() is None
        token = bind_request_id("req-123")
        try:
            assert current_request_id() == "req-123"
        finally:
            reset_request_id(token)
        assert current_request_id() is None

    def test_filter_injects_request_id_from_context(self) -> None:
        token = bind_request_id("req-456")
        try:
            record = _make_record()
            assert RequestIdLogFilter().filter(record) is True
            assert record.request_id == "req-456"
        finally:
            reset_request_id(token)

    def test_filter_keeps_explicit_request_id(self) -> None:
        token = bind_request_id("req-from-context")
        try:
            record = _make_record()
            record.request_id = "req-explicit"
            RequestIdLogFilter().filter(record)
            assert record.request_id == "req-explicit"
        finally:
            reset_request_id(token)

    def test_filter_without_context_leaves_record_unchanged(self) -> None:
        record = _make_record()
        assert RequestIdLogFilter().filter(record) is True
        assert getattr(record, "request_id", None) is None
