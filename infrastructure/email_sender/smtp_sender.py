"""SMTP email sender implementation - Infrastructure layer.

このモジュールはSMTPプロトコルを使用したメール送信の実装を提供します。
Flask-Mailを使用して、既存の設定との互換性を保ちます。
"""

import logging
from typing import Optional

from flask import current_app
from flask_mail import Message, Mail

from domain.email_sender.sender_interface import IEmailSender
from domain.email_sender.email_message import EmailMessage as DomainEmailMessage


logger = logging.getLogger(__name__)


class SmtpEmailSender(IEmailSender):
    """SMTPを使用したメール送信実装.
    
    Flask-Mailを使用してSMTP経由でメールを送信します。
    既存のMAIL_*設定との互換性を保ちます。
    
    Attributes:
        mail: Flask-Mailインスタンス
        default_sender: デフォルトの送信者アドレス
    """

    def __init__(self, mail: Mail, default_sender: Optional[str] = None):
        """初期化.
        
        Args:
            mail: Flask-Mailインスタンス
            default_sender: デフォルトの送信者アドレス
        """
        self.mail = mail
        self.default_sender = default_sender

    def send(self, message: DomainEmailMessage) -> bool:
        """SMTPでメールを送信する.
        
        Args:
            message: 送信するメールメッセージ
            
        Returns:
            bool: 送信に成功した場合True、失敗した場合False
            
        Raises:
            Exception: 送信中にエラーが発生した場合
        """
        try:
            # DomainEmailMessage から Flask-Mail の Message に変換
            mail_message = self._convert_to_flask_message(message)
            
            # メール送信
            self.mail.send(mail_message)
            
            logger.info(
                "Email sent successfully via SMTP",
                extra={
                    "event": "email.smtp.sent",
                    "to": message.to,
                    "subject": message.subject
                }
            )
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to send email via SMTP: {e}",
                extra={
                    "event": "email.smtp.error",
                    "to": message.to,
                    "subject": message.subject,
                    "error": str(e)
                }
            )
            raise

    def validate_config(self) -> bool:
        """SMTP設定が有効かどうかを検証する.
        
        Returns:
            bool: 設定が有効な場合True、無効な場合False
        """
        try:
            # Flask-Mailの設定が存在するか確認
            if not hasattr(current_app, 'config'):
                return False
            
            config = current_app.config
            
            # 必須設定項目の確認
            mail_server = config.get('MAIL_SERVER')
            if not mail_server:
                logger.warning("MAIL_SERVER is not configured")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate SMTP config: {e}")
            return False

    def _convert_to_flask_message(self, message: DomainEmailMessage) -> Message:
        """ドメインメッセージをFlask-Mailメッセージに変換する.
        
        Args:
            message: ドメインメッセージ
            
        Returns:
            Message: Flask-Mailメッセージ
        """
        # 送信者アドレスの決定
        sender = message.from_address or self.default_sender
        
        # Flask-Mail Message の作成
        mail_message = Message(
            subject=message.subject,
            recipients=message.to,
            body=message.body,
            html=message.html_body,
            sender=sender,
            cc=message.cc,
            bcc=message.bcc,
            reply_to=message.reply_to
        )
        
        return mail_message
