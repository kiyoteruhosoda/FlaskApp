"""メール送信インフラストラクチャ（Flask 非依存）。

Flask-Mailman を廃止し、SMTP メール送信を EmailSenderFactory 経由で提供する
互換レイヤー。既存の ``from shared.infrastructure.mail import mail`` を維持する。
"""
from __future__ import annotations


class _MailCompat:
    """Flask-Mailman の ``mail`` オブジェクト互換シム。

    ``mail.send(message)`` の呼び出しを SMTPEmailSender へ委譲する。
    ``mail.init_app(app)`` は no-op として受け付ける（Flask 互換）。
    """

    def init_app(self, app: object) -> None:
        """Flask アプリへの登録（no-op）。"""

    def send(self, message: object) -> None:
        """メール送信（EmailSenderFactory へ委譲）。"""
        from bounded_contexts.email_sender.infrastructure.factory import EmailSenderFactory

        sender = EmailSenderFactory.create()
        sender.send(message)  # type: ignore[arg-type]


mail = _MailCompat()

__all__ = ["mail"]

