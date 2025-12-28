"""Test-only email sender factory.

このファクトリはテスト専用で、ConsoleEmailSenderをサポートします。
本番環境では使用できません。
"""

import logging
from typing import Optional

from flask_mailman import Mail

from domain.email_sender.sender_interface import IEmailSender
from infrastructure.email_sender import SmtpEmailSender
from infrastructure.email_sender.factory import EmailSenderFactory as ProductionFactory
from .console_sender import ConsoleEmailSender


logger = logging.getLogger(__name__)


class TestEmailSenderFactory(ProductionFactory):
    """テスト用メール送信実装のファクトリクラス.
    
    本番のEmailSenderFactoryを継承し、ConsoleEmailSenderのサポートを追加します。
    テスト環境でのみ使用することを想定しています。
    """

    # テスト専用プロバイダー
    PROVIDER_CONSOLE = "console"

    @staticmethod
    def create(
        provider: Optional[str] = None,
        mail: Optional[Mail] = None,
        default_sender: Optional[str] = None
    ) -> IEmailSender:
        """設定に基づいてメール送信実装を生成する（テスト用拡張版）.
        
        Args:
            provider: メールプロバイダー名（smtp, console）
                     Noneの場合は設定またはデフォルトから取得
            mail: Flask-Mailmanインスタンス（SMTPプロバイダーで必要）
            default_sender: デフォルトの送信者アドレス
            
        Returns:
            IEmailSender: メール送信実装
            
        Raises:
            ValueError: 未対応のプロバイダーが指定された場合
        """
        # プロバイダーの決定
        if provider is None:
            provider = TestEmailSenderFactory._get_provider_from_config()
        
        provider = provider.lower().strip()
        
        # Console プロバイダーの場合はテスト専用実装を返す
        if provider == TestEmailSenderFactory.PROVIDER_CONSOLE:
            logger.info(
                "Creating console email sender (test only)",
                extra={"event": "email.factory.create", "provider": provider}
            )
            return TestEmailSenderFactory._create_console_sender()
        
        # それ以外は本番のファクトリに委譲
        return ProductionFactory.create(provider, mail, default_sender)

    @staticmethod
    def _create_console_sender() -> ConsoleEmailSender:
        """コンソールメール送信実装を生成する（テスト専用）.
        
        Returns:
            ConsoleEmailSender: コンソール送信実装
        """
        return ConsoleEmailSender()
