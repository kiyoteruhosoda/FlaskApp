"""Email sender factory - Infrastructure layer.

このモジュールは設定に基づいて適切なメール送信実装を生成するファクトリを提供します。
Dependency Injection (DI) パターンを実装しています。
"""

from __future__ import annotations

import logging
from typing import Final

from flask_mailman import Mail

from domain.email_sender import EmailSender
from .smtp_sender import SmtpEmailSender

logger = logging.getLogger(__name__)


class EmailSenderFactory:
    """メール送信実装のファクトリクラス.

    設定に基づいて適切なEmailSender実装を生成します。
    Strategy パターンの具体的な戦略選択を担当します。

    Note:
        本番環境ではSMTPのみをサポートします。
        テスト用のConsoleEmailSenderは tests/infrastructure/email_sender/ にあります。
    """

    PROVIDER_SMTP: Final[str] = "smtp"
    DEFAULT_PROVIDER: Final[str] = PROVIDER_SMTP

    @classmethod
    def create(
        cls,
        provider: str | None = None,
        mail: Mail | None = None,
        default_sender: str | None = None,
    ) -> EmailSender:
        """設定に基づいてメール送信実装を生成する.

        Args:
            provider: メールプロバイダー名（smtp のみサポート）
            mail: Flask-Mailmanインスタンス（SMTPプロバイダーで必要）
            default_sender: デフォルトの送信者アドレス

        Returns:
            EmailSender: メール送信実装

        Raises:
            ValueError: 未対応のプロバイダーが指定された場合
        """
        resolved_provider = (provider or cls._get_provider_from_config()).lower().strip()

        logger.info(
            f"Creating email sender with provider: {resolved_provider}",
            extra={"event": "email.factory.create", "provider": resolved_provider},
        )

        if resolved_provider == cls.PROVIDER_SMTP:
            return cls._create_smtp_sender(mail, default_sender)

        raise ValueError(
            f"Unsupported email provider: {resolved_provider}. "
            f"Supported provider: {cls.PROVIDER_SMTP}. "
            "Note: 'console' provider is only available in tests."
        )

    @classmethod
    def _get_provider_from_config(cls) -> str:
        """設定からメールプロバイダーを取得."""
        try:
            from core.settings import settings

            return str(settings.mail_provider).lower().strip()
        except Exception as e:
            logger.warning(
                f"Failed to get mail provider from config, using default: {e}",
                extra={"event": "email.factory.config_error"},
            )
            return cls.DEFAULT_PROVIDER

    @classmethod
    def _create_smtp_sender(
        cls,
        mail: Mail | None,
        default_sender: str | None,
    ) -> SmtpEmailSender:
        """SMTPメール送信実装を生成."""
        resolved_mail = mail or cls._resolve_mail_instance()
        resolved_sender = default_sender or cls._resolve_default_sender()

        return SmtpEmailSender(mail=resolved_mail, default_sender=resolved_sender)

    @staticmethod
    def _resolve_mail_instance() -> Mail:
        """Flask-Mailmanインスタンスを取得."""
        try:
            from webapp.extensions import mail as app_mail

            logger.info("Using mail instance from webapp.extensions")
            return app_mail
        except Exception as e:
            raise ValueError(
                "Flask-Mailman instance is required for SMTP provider. "
                "Please provide 'mail' parameter or ensure webapp.extensions.mail is initialized."
            ) from e

    @staticmethod
    def _resolve_default_sender() -> str | None:
        """デフォルト送信者を設定から取得."""
        try:
            from core.settings import settings

            return settings.mail_default_sender or settings.mail_username
        except Exception:
            return None


__all__ = ["EmailSenderFactory"]
