"""Email service - Application layer.

このモジュールは高レベルのメール送信サービスを提供します。
ビジネスロジックとメール送信の詳細を分離します。
"""

import logging
from typing import Optional, List

from flask import current_app, render_template
from flask_babel import gettext as _

from domain.email_sender import IEmailSender, EmailMessage
from infrastructure.email_sender import EmailSenderFactory


logger = logging.getLogger(__name__)


class EmailService:
    """メール送信アプリケーションサービス.
    
    このクラスは高レベルのメール送信機能を提供します。
    具体的な送信方法（SMTP, Console等）の詳細を隠蔽します。
    
    Attributes:
        sender: メール送信実装（IEmailSender）
    """

    def __init__(self, sender: Optional[IEmailSender] = None):
        """初期化.
        
        Args:
            sender: メール送信実装（省略時はファクトリから自動生成）
        """
        if sender is None:
            # ファクトリから自動生成
            sender = EmailSenderFactory.create()
        
        self.sender = sender

    def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_address: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None
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
            # EmailMessage値オブジェクトを作成
            message = EmailMessage(
                to=to,
                subject=subject,
                body=body,
                html_body=html_body,
                from_address=from_address,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to
            )
            
            # 送信実行
            return self.sender.send(message)
            
        except Exception as e:
            logger.error(
                f"Failed to send email: {e}",
                extra={
                    "event": "email.service.error",
                    "to": to,
                    "subject": subject,
                    "error": str(e)
                }
            )
            return False

    def send_password_reset_email(
        self,
        email: str,
        reset_url: str,
        validity_minutes: int = 30
    ) -> bool:
        """パスワードリセットメールを送信する.
        
        既存のPasswordResetServiceとの互換性を保つためのヘルパーメソッド。
        
        Args:
            email: 送信先メールアドレス
            reset_url: パスワードリセットURL
            validity_minutes: トークンの有効期限（分）
            
        Returns:
            bool: 送信に成功した場合True、失敗した場合False
        """
        try:
            # メール本文の生成（英語がデフォルト、翻訳ファイルで日本語化）
            subject = _("Password Reset Request")
            
            body = _(
                "Please reset your password by clicking the link below.\n"
                "This link will expire in %(minutes)d minutes.\n"
                "\n"
                "%(url)s\n"
                "\n"
                "If you did not request this password reset, please ignore this email.",
                minutes=validity_minutes,
                url=reset_url
            )
            
            # HTMLテンプレートの使用を試みる
            html_body = None
            try:
                html_body = render_template(
                    'auth/email/password_reset.html',
                    reset_url=reset_url,
                    validity_minutes=validity_minutes
                )
            except Exception as template_error:
                logger.warning(
                    f"Failed to render HTML template, using plain text only: {template_error}",
                    extra={"event": "email.service.template_error"}
                )
            
            # メール送信
            return self.send_email(
                to=[email],
                subject=subject,
                body=body,
                html_body=html_body
            )
            
        except Exception as e:
            logger.error(
                f"Failed to send password reset email: {e}",
                extra={
                    "event": "email.service.password_reset_error",
                    "email": email,
                    "error": str(e)
                }
            )
            return False

    def validate_sender_config(self) -> bool:
        """メール送信設定が有効かどうかを検証する.
        
        Returns:
            bool: 設定が有効な場合True、無効な場合False
        """
        return self.sender.validate_config()
