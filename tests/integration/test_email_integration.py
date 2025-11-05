"""Integration tests for email module.

このテストは、EmailServiceとPasswordResetServiceの統合をテストします。
"""

import pytest
from unittest.mock import patch

from application.email_service import EmailService
from domain.email_sender import EmailMessage
from infrastructure.email_sender import ConsoleEmailSender, EmailSenderFactory


class TestEmailIntegration:
    """Email module integration tests."""

    def test_email_service_with_console_sender(self):
        """Test EmailService with ConsoleEmailSender."""
        # ConsoleEmailSenderを使用
        sender = ConsoleEmailSender()
        service = EmailService(sender=sender)
        
        # メール送信
        result = service.send_email(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        assert result is True

    def test_email_service_with_factory(self):
        """Test EmailService with factory-created sender."""
        # ファクトリを使用してコンソール送信者を明示的に作成
        sender = EmailSenderFactory.create(provider="console")
        
        assert isinstance(sender, ConsoleEmailSender)
        
        # EmailServiceで使用
        service = EmailService(sender=sender)
        result = service.send_email(
            to=["test@example.com"],
            subject="Integration Test",
            body="This is an integration test"
        )
        
        assert result is True

    def test_email_service_password_reset(self):
        """Test password reset email sending."""
        # コンソール送信者を使用
        sender = ConsoleEmailSender()
        service = EmailService(sender=sender)
        
        # パスワードリセットメール送信
        result = service.send_password_reset_email(
            email="user@example.com",
            reset_url="https://example.com/reset?token=test123",
            validity_minutes=30
        )
        
        assert result is True

    def test_email_service_validates_config(self):
        """Test email service config validation."""
        sender = ConsoleEmailSender()
        service = EmailService(sender=sender)
        
        # ConsoleEmailSenderは常に有効な設定を持つ
        assert service.validate_sender_config() is True

    def test_email_message_validation(self):
        """Test EmailMessage validation."""
        # 有効なメッセージ
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test",
            body="Test body"
        )
        assert message.to == ["test@example.com"]
        
        # 無効なメッセージ（空の受信者）
        with pytest.raises(ValueError):
            EmailMessage(
                to=[],
                subject="Test",
                body="Test body"
            )

    def test_factory_smtp_requires_mail_instance(self):
        """Test that SMTP factory requires Flask-Mail instance."""
        # SMTPを作成しようとするが、Flask-Mailが利用できないのでエラーになる
        # これは正常な動作（テスト環境では完全なFlaskアプリがない）
        with pytest.raises(ValueError, match="Flask-Mail instance is required"):
            EmailSenderFactory.create(provider="smtp")

    def test_email_service_with_html(self):
        """Test sending email with HTML body."""
        sender = ConsoleEmailSender()
        service = EmailService(sender=sender)
        
        result = service.send_email(
            to=["test@example.com"],
            subject="HTML Email",
            body="Plain text version",
            html_body="<h1>HTML Version</h1>"
        )
        
        assert result is True

    def test_email_service_with_cc_bcc(self):
        """Test sending email with CC and BCC."""
        sender = ConsoleEmailSender()
        service = EmailService(sender=sender)
        
        result = service.send_email(
            to=["test@example.com"],
            subject="Test with CC/BCC",
            body="Test body",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"]
        )
        
        assert result is True
