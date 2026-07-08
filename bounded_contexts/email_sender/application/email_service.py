"""Application Service for email sending."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from flask import render_template
from flask_babel import gettext as _

from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.sender_interface import EmailSender

logger = logging.getLogger(__name__)


@runtime_checkable
class EmailRepository(Protocol):
    """Repository for email-related persistence."""

    def save_sent_email(self, message: EmailMessage) -> None:
        """Save record of sent email."""
        ...

    def get_email_history(self, email: str) -> list[EmailMessage]:
        """Get email history for an address."""
        ...


@dataclass
class EmailService:
    """メール送信アプリケーションサービス.

    高レベルのメール送信機能を提供する。具体的な送信方法（SMTP 等）の
    詳細を隠蔽し、ビジネスロジック（パスワードリセットメール等）を集約する。
    """

    sender: EmailSender = field(
        default_factory=lambda: _create_default_sender()
    )
    repository: EmailRepository | None = None
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

            success = self.sender.send(message)

            if success and self.repository:
                self.repository.save_sent_email(message)

            return success

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

            html_body = self._render_password_reset_template(reset_url, validity_minutes)

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

    def can_send_emails(self) -> bool:
        """メール送信が可能かチェックする."""
        return self.sender.validate_config()

    def get_email_history(self, email: str) -> list[EmailMessage]:
        """リポジトリが利用可能な場合、メール送信履歴を返す."""
        if not self.repository:
            return []
        return self.repository.get_email_history(email)

    @staticmethod
    def _is_mail_enabled() -> bool:
        """メール機能が有効かチェック."""
        try:
            from shared.kernel.settings.settings import settings

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


def _create_default_sender() -> EmailSender:
    """デフォルトのメール送信実装を生成する（遅延インポート）."""
    from bounded_contexts.email_sender.infrastructure.factory import EmailSenderFactory

    return EmailSenderFactory.create()


__all__ = ["EmailService", "EmailRepository"]