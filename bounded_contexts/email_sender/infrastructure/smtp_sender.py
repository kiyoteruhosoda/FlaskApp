"""SMTP email sender implementation - Infrastructure layer.

このモジュールはSMTPプロトコルを使用したメール送信の実装を提供します。
Flask-Mailmanを使用して、既存の設定との互換性を保ちます。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from flask import current_app
from flask_mailman import EmailMessage as FlaskEmailMessage
from flask_mailman import EmailMultiAlternatives, Mail

from bounded_contexts.email_sender.domain.email_message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass
class SMTPEmailSender:
    """SMTPを使用したメール送信実装.

    Flask-Mailmanを使用してSMTP経由でメールを送信します。
    既存のMAIL_*設定との互換性を保ちます。

    Note:
        Protocol (EmailSender) の構造的部分型付けに準拠。
        明示的な継承は不要です。
    """

    mail: Mail
    default_sender: str | None = None
    _logger: logging.Logger = field(default_factory=lambda: logger)

    def send(self, message: EmailMessage) -> bool:
        """SMTPでメールを送信する.

        Args:
            message: 送信するメールメッセージ

        Returns:
            bool: 送信に成功した場合True

        Raises:
            Exception: 送信中にエラーが発生した場合
        """
        mail_message = self._to_flask_message(message)
        self.mail.send(mail_message)

        self._logger.info(
            "Email sent successfully via SMTP",
            extra={
                "event": "email.smtp.sent",
                "to": message.to,
                "subject": message.subject,
            },
        )
        return True

    def validate_config(self) -> bool:
        """SMTP設定が有効かどうかを検証する.

        Returns:
            bool: 設定が有効な場合True、無効な場合False
        """
        try:
            config = current_app.config
            mail_server = config.get("MAIL_SERVER")
            if not mail_server:
                self._logger.warning("MAIL_SERVER is not configured")
                return False
            return True
        except Exception as e:
            self._logger.error(f"Failed to validate SMTP config: {e}")
            return False

    def _to_flask_message(
        self,
        message: EmailMessage,
    ) -> FlaskEmailMessage | EmailMultiAlternatives:
        """ドメインメッセージをFlask-Mailmanメッセージに変換."""
        reply_to_list = self._normalize_reply_to(message.reply_to)

        params = {
            "subject": message.subject,
            "body": message.body,
            "from_email": message.from_address or self.default_sender,
            "to": message.to,
            "cc": message.cc or [],
            "bcc": message.bcc or [],
            "reply_to": reply_to_list,
        }

        if message.html_body:
            mail_msg = EmailMultiAlternatives(**params)
            mail_msg.attach_alternative(message.html_body, "text/html")
            return mail_msg

        return FlaskEmailMessage(**params)

    @staticmethod
    def _normalize_reply_to(reply_to: str | None) -> list[str]:
        """reply_to をリスト形式に正規化."""
        if reply_to and (stripped := reply_to.strip()):
            return [stripped]
        return []


__all__ = ["SMTPEmailSender"]
