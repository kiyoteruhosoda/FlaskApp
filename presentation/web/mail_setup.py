"""メール送信（Flask-Mailman）の初期設定.

``create_app()`` 内のメール初期化を切り出す。メール機能が有効な場合のみ設定値を
``app.config`` へ反映し、拡張を初期化する。無効時は何もしない。
"""

from __future__ import annotations

from flask import Flask

from core.settings import settings

from .extensions import mail


def configure_mail(app: Flask) -> None:
    """設定が有効ならメール拡張を初期化する。"""

    if not settings.mail_enabled:
        return

    app.config['MAIL_SERVER'] = settings.mail_server
    app.config['MAIL_PORT'] = settings.mail_port
    app.config['MAIL_USE_TLS'] = settings.mail_use_tls
    app.config['MAIL_USE_SSL'] = settings.mail_use_ssl
    app.config['MAIL_USERNAME'] = settings.mail_username
    app.config['MAIL_PASSWORD'] = settings.mail_password
    app.config['MAIL_DEFAULT_SENDER'] = settings.mail_default_sender or settings.mail_username

    mail_state = mail.init_app(app)
    mail.state = mail_state
    mail.app = app
