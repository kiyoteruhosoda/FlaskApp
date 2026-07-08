"""SMTP email sender implementation - Infrastructure layer.

Python 標準ライブラリの ``smtplib``・``email`` を使用した SMTP メール送信実装。
Flask-Mailman 依存を排除した Flask 非依存バージョン（T11 Flask 完全撤廃）。
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from bounded_contexts.email_sender.domain.email_message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass
class SMTPEmailSender:
    """Python 標準 smtplib を使用したメール送信実装.

    Note:
        Protocol (EmailSender) の構造的部分型付けに準拠。
        明示的な継承は不要です。
    """

    default_sender: str | None = None
    _logger: logging.Logger = field(default_factory=lambda: logger)

    def send(self, message: EmailMessage) -> bool:
        """SMTP でメールを送信する.

        Args:
            message: 送信するメールメッセージ

        Returns:
            bool: 送信に成功した場合 True
        """
        from shared.kernel.settings.settings import settings

        mail_server = getattr(settings, "mail_server", None) or "localhost"
        mail_port = int(getattr(settings, "mail_port", None) or 25)
        mail_use_tls = bool(getattr(settings, "mail_use_tls", False))
        mail_use_ssl = bool(getattr(settings, "mail_use_ssl", False))
        mail_username = getattr(settings, "mail_username", None)
        mail_password = getattr(settings, "mail_password", None)
        default_sender = self.default_sender or getattr(settings, "mail_default_sender", None) or "noreply@localhost"

        mime_message = self._build_mime_message(message, default_sender)

        try:
            if mail_use_ssl:
                server = smtplib.SMTP_SSL(mail_server, mail_port)
            else:
                server = smtplib.SMTP(mail_server, mail_port)
                if mail_use_tls:
                    server.starttls()

            with server:
                if mail_username and mail_password:
                    server.login(mail_username, mail_password)
                server.sendmail(
                    mime_message["From"],
                    message.to + (message.cc or []) + (message.bcc or []),
                    mime_message.as_string(),
                )

            self._logger.info(
                "Email sent successfully via SMTP",
                extra={
                    "event": "email.smtp.sent",
                    "to": message.to,
                    "subject": message.subject,
                },
            )
            return True

        except Exception as exc:
            self._logger.error(
                "Failed to send email via SMTP: %s",
                exc,
                extra={
                    "event": "email.smtp.error",
                    "to": message.to,
                    "subject": message.subject,
                },
            )
            raise

    def validate_config(self) -> bool:
        """SMTP 設定が有効かどうかを検証する."""
        try:
            from shared.kernel.settings.settings import settings
            mail_server = getattr(settings, "mail_server", None)
            if not mail_server:
                self._logger.warning("MAIL_SERVER is not configured")
                return False
            return True
        except Exception as exc:
            self._logger.error("Failed to validate SMTP config: %s", exc)
            return False

    def _build_mime_message(
        self,
        message: EmailMessage,
        default_sender: str,
    ) -> MIMEMultipart | MIMEText:
        """ドメインメッセージを MIME メッセージに変換."""
        from_address = message.from_address or default_sender

        if message.html_body:
            mime_msg: MIMEMultipart | MIMEText = MIMEMultipart("alternative")
            assert isinstance(mime_msg, MIMEMultipart)
            mime_msg.attach(MIMEText(message.body, "plain", "utf-8"))
            mime_msg.attach(MIMEText(message.html_body, "html", "utf-8"))
        else:
            mime_msg = MIMEText(message.body, "plain", "utf-8")

        mime_msg["Subject"] = message.subject
        mime_msg["From"] = from_address
        mime_msg["To"] = ", ".join(message.to)

        if message.cc:
            mime_msg["Cc"] = ", ".join(message.cc)

        if message.reply_to and (stripped := message.reply_to.strip()):
            mime_msg["Reply-To"] = stripped

        return mime_msg


__all__ = ["SMTPEmailSender"]

