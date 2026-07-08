"""Email sender factory - Infrastructure layer.

設定に基づいて適切なメール送信実装を生成するファクトリ。
Flask-Mailman 非依存版（T11 Flask 完全撤廃）。
"""

from __future__ import annotations

import logging
from typing import Final

from bounded_contexts.email_sender.domain.sender_interface import EmailSender
from .smtp_sender import SMTPEmailSender

logger = logging.getLogger(__name__)


class EmailSenderFactory:
    """メール送信実装のファクトリクラス。"""

    PROVIDER_SMTP: Final[str] = "smtp"
    DEFAULT_PROVIDER: Final[str] = PROVIDER_SMTP

    @classmethod
    def create(
        cls,
        provider: str | None = None,
        default_sender: str | None = None,
    ) -> EmailSender:
        """設定に基づいてメール送信実装を生成する。"""
        resolved_provider = (provider or cls._get_provider_from_config()).lower().strip()

        logger.info(
            "Creating email sender with provider: %s",
            resolved_provider,
            extra={"event": "email.factory.create", "provider": resolved_provider},
        )

        if resolved_provider == cls.PROVIDER_SMTP:
            return cls._create_smtp_sender(default_sender)

        raise ValueError(
            f"Unsupported email provider: {resolved_provider}. "
            f"Supported provider: {cls.PROVIDER_SMTP}. "
            "Note: 'console' provider is only available in tests."
        )

    @classmethod
    def _get_provider_from_config(cls) -> str:
        """設定からメールプロバイダーを取得。"""
        try:
            from shared.kernel.settings.settings import settings
            return str(settings.mail_provider).lower().strip()
        except Exception as exc:
            logger.warning(
                "Failed to get mail provider from config, using default: %s", exc,
                extra={"event": "email.factory.config_error"},
            )
            return cls.DEFAULT_PROVIDER

    @classmethod
    def _create_smtp_sender(cls, default_sender: str | None) -> SMTPEmailSender:
        """SMTP メール送信実装を生成。"""
        resolved_sender = default_sender or cls._resolve_default_sender()
        return SMTPEmailSender(default_sender=resolved_sender)

    @staticmethod
    def _resolve_default_sender() -> str | None:
        """デフォルト送信者を設定から取得。"""
        try:
            from shared.kernel.settings.settings import settings
            return settings.mail_default_sender or settings.mail_username
        except Exception:
            return None


__all__ = ["EmailSenderFactory"]

