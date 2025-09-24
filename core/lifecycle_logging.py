"""サーバーライフサイクルに関するログ出力を提供するユーティリティ。"""

from __future__ import annotations

import atexit
import json
import os
import signal
import socket
from datetime import datetime, timezone
from types import FrameType
from typing import Callable, Optional
from uuid import uuid4

from flask import Flask


LifecycleHandler = Callable[[int, Optional[FrameType]], None]


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
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    lifecycle_id = str(uuid4())

    ext_state = app.extensions.setdefault("lifecycle_logging", {})

    _log_lifecycle_event(app, "startup", lifecycle_id)

    def _atexit_handler() -> None:
        _log_lifecycle_event(app, "shutdown", lifecycle_id, reason="atexit")

    atexit.register(_atexit_handler)
    ext_state["atexit_handler"] = _atexit_handler

    def _make_signal_handler(previous: Optional[LifecycleHandler], signum: int) -> LifecycleHandler:
        def _handler(sig: int, frame: Optional[FrameType]) -> None:
            _log_lifecycle_event(
                app,
                "shutdown",
                lifecycle_id,
                reason=f"signal.{signal.Signals(sig).name}",
            )

            if previous is None or previous in (signal.SIG_DFL, signal.SIG_IGN):
                return

            previous(sig, frame)

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

