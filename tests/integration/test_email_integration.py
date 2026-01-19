"""Integration tests for email module.

このテストは、EmailServiceとPasswordResetServiceの統合をテストします。
"""

import pytest
from unittest.mock import patch

pytestmark = pytest.mark.integration

from application.email_service import EmailService
from domain.email_sender import EmailMessage
from infrastructure.email_sender import EmailSenderFactory
from tests.infrastructure.email_sender.console_sender import ConsoleEmailSender
from tests.infrastructure.email_sender.factory import TestEmailSenderFactory


class TestEmailIntegration:
    """Email module integration tests."""

    @patch('core.settings.settings')
    def test_email_service_with_console_sender(self, mock_settings):
        """Test EmailService with ConsoleEmailSender."""
        mock_settings.mail_enabled = True
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

    @patch('core.settings.settings')
    def test_email_service_with_factory(self, mock_settings):
        """Test EmailService with factory-created sender."""
        mock_settings.mail_enabled = True
        # テスト用ファクトリを使用してコンソール送信者を明示的に作成
        sender = TestEmailSenderFactory.create(provider="console")
        
        assert isinstance(sender, ConsoleEmailSender)
        
        # EmailServiceで使用
        service = EmailService(sender=sender)
        result = service.send_email(
            to=["test@example.com"],
            subject="Integration Test",
            body="This is an integration test"
        )
        
        assert result is True

    @patch('core.settings.settings')
    def test_email_service_password_reset(self, mock_settings):
        """Test password reset email sending."""
        mock_settings.mail_enabled = True
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

    @pytest.mark.skip(reason="webapp.extensions.mail is available in test environment, cannot test failure case")
    def test_factory_smtp_requires_mail_instance(self):
        """Test that SMTP factory requires Flask-Mailman instance."""
        # Note: webapp.extensions.mail exists in test environment, so this test is skipped
        pass

    def test_production_factory_rejects_console(self):
        """Test that production factory rejects console provider."""
        # 本番環境のファクトリはconsoleプロバイダーを受け付けない
        with pytest.raises(ValueError, match="Unsupported email provider.*console.*only available in tests"):
            EmailSenderFactory.create(provider="console")

    @patch('core.settings.settings')
    def test_email_service_with_html(self, mock_settings):
        """Test sending email with HTML body."""
        mock_settings.mail_enabled = True
        sender = ConsoleEmailSender()
        service = EmailService(sender=sender)
        
        result = service.send_email(
            to=["test@example.com"],
            subject="HTML Email",
            body="Plain text version",
            html_body="<h1>HTML Version</h1>"
        )
        
        assert result is True

    @patch('core.settings.settings')
    def test_email_service_with_cc_bcc(self, mock_settings):
        """Test sending email with CC and BCC."""
        mock_settings.mail_enabled = True
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
