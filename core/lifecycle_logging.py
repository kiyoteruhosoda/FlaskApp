"""サーバーライフサイクルに関するログ出力を提供するユーティリティ。"""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import socket
from datetime import datetime, timezone
from types import FrameType
from typing import Callable, Optional, cast
from uuid import uuid4

from flask import Flask

from sqlalchemy.engine import make_url

from core.db_log_handler import DBLogHandler
from core.logging_config import ensure_appdb_file_logging
from core.settings import settings


LifecycleHandler = Callable[[int, Optional[FrameType]], None]
PrevSignalHandler = Optional[LifecycleHandler] | int


def _build_lifecycle_payload(
    *,
    app: Flask,
    action: str,
    lifecycle_id: str,
    reason: Optional[str] = None,
) -> str:
    """ライフサイクルイベントのペイロード(JSON文字列)を構築する。"""

    now = datetime.now(timezone.utc)
    payload = {
        "event": "app.lifecycle",
        "action": action,
        "timestamp": now.isoformat(),
        "timezone": "UTC",
        "lifecycle_id": lifecycle_id,
        "app": {
            "name": app.import_name,
            "env": app.config.get("ENV"),
            "debug": app.debug,
        },
        "host": {
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
        },
    }

    if reason:
        payload["reason"] = reason

    return json.dumps(payload, ensure_ascii=False)


def _log_lifecycle_event(app: Flask, action: str, lifecycle_id: str, reason: Optional[str] = None) -> None:
    message = _build_lifecycle_payload(app=app, action=action, lifecycle_id=lifecycle_id, reason=reason)
    extra = {
        "event": "app.lifecycle",
        "action": action,
        "lifecycle_id": lifecycle_id,
    }
    app.logger.info(message, extra=extra)


def register_lifecycle_logging(app: Flask) -> None:
    """サーバー起動・停止イベントのログを登録する。"""

    if getattr(app, "_lifecycle_logging_registered", False):
        return

    # Flask のリロード親プロセスではログを出力しない
    if app.debug and str(settings.werkzeug_run_main or "").lower() != "true":
        return

    lifecycle_id = str(uuid4())

    ext_state = app.extensions.setdefault("lifecycle_logging", {})

    ensure_appdb_file_logging(app.logger)

    should_bind_handlers = True
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    if database_uri:
        try:
            url = make_url(database_uri)
        except Exception:  # pragma: no cover - invalid URI should not block logging
            url = None
        if url is not None and url.get_backend_name() == "sqlite":
            if url.database in (None, "", ":memory:"):
                should_bind_handlers = False

    if should_bind_handlers:
        for handler in app.logger.handlers:
            if isinstance(handler, DBLogHandler):
                handler.bind_to_app(app)


    original_level = app.logger.level
    level_temporarily_lowered = False
    if not app.logger.isEnabledFor(logging.INFO):
        app.logger.setLevel(logging.INFO)
        level_temporarily_lowered = True

    try:
        _log_lifecycle_event(app, "startup", lifecycle_id)
    finally:
        if level_temporarily_lowered:
            app.logger.setLevel(original_level)

    def _atexit_handler() -> None:
        _log_lifecycle_event(app, "shutdown", lifecycle_id, reason="atexit")

    atexit.register(_atexit_handler)
    ext_state["atexit_handler"] = _atexit_handler
    def _make_signal_handler(previous: PrevSignalHandler, signum: int) -> LifecycleHandler:
        def _handler(sig: int, frame: Optional[FrameType]) -> None:
            _log_lifecycle_event(
                app,
                "shutdown",
                lifecycle_id,
                reason=f"signal.{signal.Signals(sig).name}",
            )

            if callable(previous):
                cast(LifecycleHandler, previous)(sig, frame)

        return _handler
        return _handler

    signal_handlers = ext_state.setdefault("signal_handlers", {})

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            previous_handler = signal.getsignal(sig)
            signal.signal(sig, _make_signal_handler(previous_handler, sig))
            signal_handlers[sig] = previous_handler
        except (ValueError, OSError):
            # マルチスレッド環境などで signal 登録が失敗した場合は無視
            app.logger.debug("ライフサイクルログ用のシグナルハンドラ登録に失敗しました", extra={"event": "app.lifecycle"})

    setattr(app, "_lifecycle_logging_registered", True)
    ext_state["lifecycle_id"] = lifecycle_id

