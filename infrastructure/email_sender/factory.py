"""Email sender factory - Infrastructure layer.

このモジュールは設定に基づいて適切なメール送信実装を生成するファクトリを提供します。
Dependency Injection (DI) パターンを実装しています。
"""

import logging
from typing import Optional

from flask import Flask, current_app
from flask_mail import Mail

from domain.email_sender.sender_interface import IEmailSender
from .smtp_sender import SmtpEmailSender
from .console_sender import ConsoleEmailSender


logger = logging.getLogger(__name__)


class EmailSenderFactory:
    """メール送信実装のファクトリクラス.
    
    設定に基づいて適切なIEmailSender実装を生成します。
    Strategy パターンの具体的な戦略選択を担当します。
    """

    # サポートされているメールプロバイダー
    PROVIDER_SMTP = "smtp"
    PROVIDER_CONSOLE = "console"
    
    # デフォルトプロバイダー
    DEFAULT_PROVIDER = PROVIDER_SMTP

    @staticmethod
    def create(
        provider: Optional[str] = None,
        mail: Optional[Mail] = None,
        default_sender: Optional[str] = None
    ) -> IEmailSender:
        """設定に基づいてメール送信実装を生成する.
        
        Args:
            provider: メールプロバイダー名（smtp, console）
                     Noneの場合は設定またはデフォルトから取得
            mail: Flask-Mailインスタンス（SMTPプロバイダーで必要）
            default_sender: デフォルトの送信者アドレス
            
        Returns:
            IEmailSender: メール送信実装
            
        Raises:
            ValueError: 未対応のプロバイダーが指定された場合
        """
        # プロバイダーの決定
        if provider is None:
            provider = EmailSenderFactory._get_provider_from_config()
        
        provider = provider.lower().strip()
        
        logger.info(
            f"Creating email sender with provider: {provider}",
            extra={"event": "email.factory.create", "provider": provider}
        )
        
        # プロバイダーに応じた実装を生成
        if provider == EmailSenderFactory.PROVIDER_SMTP:
            return EmailSenderFactory._create_smtp_sender(mail, default_sender)
        
        elif provider == EmailSenderFactory.PROVIDER_CONSOLE:
            return EmailSenderFactory._create_console_sender()
        
        else:
            raise ValueError(
                f"Unsupported email provider: {provider}. "
                f"Supported providers: {EmailSenderFactory.PROVIDER_SMTP}, "
                f"{EmailSenderFactory.PROVIDER_CONSOLE}"
            )

    @staticmethod
    def _get_provider_from_config() -> str:
        """設定からメールプロバイダーを取得する.
        
        Returns:
            str: メールプロバイダー名
        """
        try:
            from core.settings import settings
            provider = settings.get("MAIL_PROVIDER", EmailSenderFactory.DEFAULT_PROVIDER)
            return str(provider).lower().strip()
        except Exception as e:
            logger.warning(
                f"Failed to get mail provider from config, using default: {e}",
                extra={"event": "email.factory.config_error"}
            )
            return EmailSenderFactory.DEFAULT_PROVIDER

    @staticmethod
    def _create_smtp_sender(
        mail: Optional[Mail],
        default_sender: Optional[str]
    ) -> SmtpEmailSender:
        """SMTPメール送信実装を生成する.
        
        Args:
            mail: Flask-Mailインスタンス
            default_sender: デフォルトの送信者アドレス
            
        Returns:
            SmtpEmailSender: SMTP送信実装
            
        Raises:
            ValueError: Flask-Mailインスタンスが提供されていない場合
        """
        if mail is None:
            # Flaskアプリケーションコンテキストから取得を試みる
            try:
                from webapp.extensions import mail as app_mail
                mail = app_mail
                logger.info("Using mail instance from webapp.extensions")
            except Exception as e:
                raise ValueError(
                    "Flask-Mail instance is required for SMTP provider. "
                    "Please provide 'mail' parameter or ensure webapp.extensions.mail is initialized."
                ) from e
        
        if default_sender is None:
            # 設定から取得を試みる
            try:
                from core.settings import settings
                default_sender = settings.mail_default_sender or settings.mail_username
            except Exception:
                pass
        
        return SmtpEmailSender(mail=mail, default_sender=default_sender)

    @staticmethod
    def _create_console_sender() -> ConsoleEmailSender:
        """コンソールメール送信実装を生成する.
        
        Returns:
            ConsoleEmailSender: コンソール送信実装
        """
        return ConsoleEmailSender()
