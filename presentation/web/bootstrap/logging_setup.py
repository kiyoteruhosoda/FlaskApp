"""アプリケーションロギングの構成.

``create_app()`` に定義されていたロギングセットアップを切り出す。責務は、
DB ログハンドラ（``appdb.log``）とファイルログの装着、テスト/インメモリ DB 時の
DB ログ抑止、デバッグモードでのコンソール出力とログレベル制御。
"""

from __future__ import annotations

import logging

from flask import Flask
from sqlalchemy.engine import make_url

from shared.kernel.logging.db_log_handler import DBLogHandler
from shared.kernel.logging.logging_config import ensure_appdb_file_logging


def configure_logging(
    app: Flask,
    *,
    database_uri,
    disable_db_logging: bool,
) -> None:
    """DB/ファイル/コンソールのログハンドラとログレベルを構成する。"""

    if not disable_db_logging:
        if not any(isinstance(h, DBLogHandler) for h in app.logger.handlers):
            db_handler = DBLogHandler(app=app)
            db_handler.setLevel(logging.INFO)
            app.logger.addHandler(db_handler)

        ensure_appdb_file_logging(app.logger)

        should_bind_db_handlers = True
        logging_database_uri = database_uri
        if logging_database_uri:
            try:
                url = make_url(logging_database_uri)
            except Exception:  # pragma: no cover - invalid URI should not block logging
                url = None
            if url is not None and url.get_backend_name() == "sqlite":
                if url.database in (None, "", ":memory:"):
                    should_bind_db_handlers = False

        if should_bind_db_handlers:
            for handler in app.logger.handlers:
                if isinstance(handler, DBLogHandler):
                    handler.bind_to_app(app)
    elif app.logger.level == logging.NOTSET:
        app.logger.setLevel(logging.INFO)

    # デバッグモードでは詳細ログを有効化
    if app.debug:
        app.logger.setLevel(logging.DEBUG)
        # コンソールハンドラーも追加
        import sys
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        app.logger.addHandler(console_handler)
    else:
        app.logger.setLevel(logging.INFO)
