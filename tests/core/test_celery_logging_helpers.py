"""Celery ログ設定の補助関数に関するテスト。"""

from __future__ import annotations

from typing import Any

import pytest
from flask import has_app_context

from cli.src.celery import celery_app


@pytest.fixture(autouse=True)
def _restore_setup_celery_logging(monkeypatch: pytest.MonkeyPatch):
    """テスト終了後に setup_celery_logging を元に戻す。"""

    original = celery_app.setup_celery_logging
    yield
    monkeypatch.setattr(celery_app, "setup_celery_logging", original)


def test_ensure_worker_logging_runs_inside_app_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """_ensure_worker_logging がアプリケーションコンテキスト内で実行されること。"""

    called = False

    def _fake_setup() -> None:
        nonlocal called
        assert has_app_context(), "setup_celery_logging はアプリケーションコンテキスト内で呼び出されるべき"
        called = True

    monkeypatch.setattr(celery_app, "setup_celery_logging", _fake_setup)

    celery_app._ensure_worker_logging()

    assert called, "setup_celery_logging が呼ばれていない"


@pytest.mark.parametrize(
    "handler",
    [
        celery_app._configure_worker_process_logging,
        celery_app._configure_beat_logging,
    ],
)
def test_signal_handlers_invoke_helper(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    """Celery のシグナルハンドラが _ensure_worker_logging を呼び出すこと。"""

    called = False

    def _fake_ensure_worker_logging() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(celery_app, "_ensure_worker_logging", _fake_ensure_worker_logging)

    handler()

    assert called, "シグナルハンドラが _ensure_worker_logging を呼び出していない"
