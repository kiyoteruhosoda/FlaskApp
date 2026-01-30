"""Email service - Application layer.

このモジュールは高レベルのメール送信サービスを提供します。
ビジネスロジックとメール送信の詳細を分離します。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from flask import render_template
from flask_babel import gettext as _

from bounded_contexts.email_sender import EmailMessage, EmailSender
from bounded_contexts.email_sender import EmailSenderFactory

logger = logging.getLogger(__name__)


@dataclass
class EmailService:
    """メール送信アプリケーションサービス.

    このクラスは高レベルのメール送信機能を提供します。
    具体的な送信方法（SMTP, Console等）の詳細を隠蔽します。
    """

    sender: EmailSender = field(default_factory=EmailSenderFactory.create)
    _logger: logging.Logger = field(default_factory=lambda: logger)

    def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        *,
        html_body: str | None = None,
        from_address: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        reply_to: str | None = None,
    ) -> bool:
        """メールを送信する.

        Args:
            to: 送信先メールアドレスのリスト
            subject: メールの件名
            body: メールの本文（プレーンテキスト）
            html_body: メールのHTML本文（オプション）
            from_address: 送信元メールアドレス（オプション）
            cc: CCメールアドレスのリスト（オプション）
            bcc: BCCメールアドレスのリスト（オプション）
            reply_to: 返信先メールアドレス（オプション）

        Returns:
            bool: 送信に成功した場合True、失敗した場合False
        """
        try:
            if not self._is_mail_enabled():
                self._logger.warning(
                    "Email sending attempted but mail is disabled",
                    extra={"event": "email.service.disabled", "to": to},
                )
                return False

            message = EmailMessage(
                to=to,
                subject=subject,
                body=body,
                html_body=html_body,
                from_address=from_address,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
            )

            return self.sender.send(message)

        except Exception as e:
            self._logger.error(
                f"Failed to send email: {e}",
                extra={
                    "event": "email.service.error",
                    "to": to,
                    "subject": subject,
                    "error": str(e),
                },
            )
            return False

    def send_password_reset_email(
        self,
        email: str,
        reset_url: str,
        validity_minutes: int = 30,
    ) -> bool:
        """パスワードリセットメールを送信する.

        Args:
            email: 送信先メールアドレス
            reset_url: パスワードリセットURL
            validity_minutes: トークンの有効期限（分）

        Returns:
            bool: 送信に成功した場合True、失敗した場合False
        """
        try:
            subject = _("Password Reset Request")
            body = _(
                "Please reset your password by clicking the link below.\n"
                "This link will expire in %(minutes)d minutes.\n"
                "\n"
                "%(url)s\n"
                "\n"
                "If you did not request this password reset, please ignore this email.",
                minutes=validity_minutes,
                url=reset_url,
            )

            html_body = self._render_password_reset_template(
                reset_url, validity_minutes
            )

            return self.send_email(
                to=[email],
                subject=subject,
                body=body,
                html_body=html_body,
            )

        except Exception as e:
            self._logger.error(
                f"Failed to send password reset email: {e}",
                extra={
                    "event": "email.service.password_reset_error",
                    "email": email,
                    "error": str(e),
                },
            )
            return False

    def validate_sender_config(self) -> bool:
        """メール送信設定が有効かどうかを検証する."""
        return self.sender.validate_config()

    @staticmethod
    def _is_mail_enabled() -> bool:
        """メール機能が有効かチェック."""
        try:
            from core.settings import settings

            return settings.mail_enabled
        except Exception:
            return False

    def _render_password_reset_template(
        self,
        reset_url: str,
        validity_minutes: int,
    ) -> str | None:
        """パスワードリセットHTMLテンプレートをレンダリング."""
        try:
            return render_template(
                "auth/email/password_reset.html",
                reset_url=reset_url,
                validity_minutes=validity_minutes,
            )
        except Exception as e:
            self._logger.warning(
                f"Failed to render HTML template, using plain text only: {e}",
                extra={"event": "email.service.template_error"},
            )
            return None


__all__ = ["EmailService"]
