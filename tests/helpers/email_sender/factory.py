"""Test-only email sender factory.

このファクトリはテスト専用で、ConsoleEmailSenderをサポートします。
本番環境では使用できません。
"""

from __future__ import annotations

import logging
from typing import Final

from flask_mailman import Mail

from domain.email_sender import EmailSender
from infrastructure.email_sender.factory import EmailSenderFactory as ProductionFactory
from .console_sender import ConsoleEmailSender

logger = logging.getLogger(__name__)


class TestEmailSenderFactory(ProductionFactory):
    """テスト用メール送信実装のファクトリクラス.

    本番のEmailSenderFactoryを継承し、ConsoleEmailSenderのサポートを追加します。
    テスト環境でのみ使用することを想定しています。
    """

    PROVIDER_CONSOLE: Final[str] = "console"

    @classmethod
    def create(
        cls,
        provider: str | None = None,
        mail: Mail | None = None,
        default_sender: str | None = None,
    ) -> EmailSender:
        """設定に基づいてメール送信実装を生成する（テスト用拡張版）.

        Args:
            provider: メールプロバイダー名（smtp, console）
            mail: Flask-Mailmanインスタンス（SMTPプロバイダーで必要）
            default_sender: デフォルトの送信者アドレス

        Returns:
            EmailSender: メール送信実装

        Raises:
            ValueError: 未対応のプロバイダーが指定された場合
        """
        resolved_provider = (
            provider or cls._get_provider_from_config()
        ).lower().strip()

        if resolved_provider == cls.PROVIDER_CONSOLE:
            logger.info(
                "Creating console email sender (test only)",
                extra={"event": "email.factory.create", "provider": resolved_provider},
            )
            return ConsoleEmailSender()

        # それ以外は本番のファクトリに委譲
        return ProductionFactory.create(resolved_provider, mail, default_sender)


__all__ = ["TestEmailSenderFactory"]
