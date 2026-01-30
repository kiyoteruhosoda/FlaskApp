"""ライフサイクルログのユニットテスト。"""

import atexit
import importlib
import json
import sys
import signal
from pathlib import Path

import pytest

from core.lifecycle_logging import register_lifecycle_logging
from core.models.log import Log


@pytest.fixture
def lifecycle_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "lifecycle.sqlite"

    env_vars = {
        "DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-secret-key",
        "JWT_SECRET_KEY": "test-jwt-secret",
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    import webapp.config as config_module
    import webapp as webapp_module

    importlib.reload(config_module)
    importlib.reload(webapp_module)

    from webapp import create_app
    from webapp.extensions import db

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()

    try:
        yield app
    finally:
        lifecycle_state = app.extensions.get("lifecycle_logging", {})
        handler = lifecycle_state.get("atexit_handler")
        if handler is not None:
            atexit.unregister(handler)

        for sig, previous in lifecycle_state.get("signal_handlers", {}).items():
            try:
                signal.signal(sig, previous)
            except (ValueError, OSError):
                pass

        with app.app_context():
            db.session.remove()
            db.drop_all()

        for module_name in ("webapp.config", "webapp"):
            if module_name in sys.modules:
                del sys.modules[module_name]


def test_lifecycle_logging_records_startup(lifecycle_app):
    app = lifecycle_app

    register_lifecycle_logging(app)
    register_lifecycle_logging(app)

    with app.app_context():
        logs = Log.query.order_by(Log.id).all()
        assert len(logs) == 1

        log = logs[0]
        assert log.event == "app.lifecycle"

        payload = json.loads(log.message)
        assert payload["event"] == "app.lifecycle"
        assert payload["action"] == "startup"
        assert payload["timezone"] == "UTC"
        assert payload["_meta"]["level"] == "INFO"
        assert payload["_extra"]["action"] == "startup"

        lifecycle_id = payload["_extra"]["lifecycle_id"]
        assert lifecycle_id
        assert app.extensions["lifecycle_logging"]["lifecycle_id"] == lifecycle_id
