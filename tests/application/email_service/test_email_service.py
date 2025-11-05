"""Tests for EmailService."""

import pytest
from unittest.mock import Mock, patch
from domain.email_sender import IEmailSender, EmailMessage
from application.email_service import EmailService


class MockEmailSender(IEmailSender):
    """Mock implementation of IEmailSender for testing."""
    
    def __init__(self):
        self.sent_messages = []
        self.should_succeed = True
    
    def send(self, message: EmailMessage) -> bool:
        self.sent_messages.append(message)
        if not self.should_succeed:
            raise Exception("Mock send failure")
        return True
    
    def validate_config(self) -> bool:
        return True


class TestEmailService:
    """Test EmailService."""

    def test_send_email_success(self):
        """Test sending email successfully."""
        mock_sender = MockEmailSender()
        service = EmailService(sender=mock_sender)
        
        result = service.send_email(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        assert result is True
        assert len(mock_sender.sent_messages) == 1
        
        message = mock_sender.sent_messages[0]
        assert message.to == ["test@example.com"]
        assert message.subject == "Test Subject"
        assert message.body == "Test Body"

    def test_send_email_with_html(self):
        """Test sending email with HTML body."""
        mock_sender = MockEmailSender()
        service = EmailService(sender=mock_sender)
        
        result = service.send_email(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            html_body="<p>Test HTML</p>"
        )
        
        assert result is True
        message = mock_sender.sent_messages[0]
        assert message.html_body == "<p>Test HTML</p>"

    def test_send_email_with_multiple_recipients(self):
        """Test sending email to multiple recipients."""
        mock_sender = MockEmailSender()
        service = EmailService(sender=mock_sender)
        
        result = service.send_email(
            to=["test1@example.com", "test2@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        assert result is True
        message = mock_sender.sent_messages[0]
        assert len(message.to) == 2

    def test_send_email_with_cc_and_bcc(self):
        """Test sending email with CC and BCC."""
        mock_sender = MockEmailSender()
        service = EmailService(sender=mock_sender)
        
        result = service.send_email(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"]
        )
        
        assert result is True
        message = mock_sender.sent_messages[0]
        assert message.cc == ["cc@example.com"]
        assert message.bcc == ["bcc@example.com"]

    def test_send_email_failure(self):
        """Test handling email send failure."""
        mock_sender = MockEmailSender()
        mock_sender.should_succeed = False
        service = EmailService(sender=mock_sender)
        
        result = service.send_email(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        # Service should catch exception and return False
        assert result is False

    def test_send_password_reset_email(self):
        """Test sending password reset email."""
        mock_sender = MockEmailSender()
        service = EmailService(sender=mock_sender)
        
        result = service.send_password_reset_email(
            email="test@example.com",
            reset_url="https://example.com/reset?token=abc123",
            validity_minutes=30
        )
        
        assert result is True
        assert len(mock_sender.sent_messages) == 1
        
        message = mock_sender.sent_messages[0]
        assert message.to == ["test@example.com"]
        # Default language is English
        assert message.subject == "Password Reset Request"
        assert "https://example.com/reset?token=abc123" in message.body
        assert "30 minutes" in message.body

    def test_validate_sender_config(self):
        """Test validating sender configuration."""
        mock_sender = MockEmailSender()
        service = EmailService(sender=mock_sender)
        
        result = service.validate_sender_config()
        assert result is True

    def test_send_email_with_invalid_data(self):
        """Test sending email with invalid data."""
        mock_sender = MockEmailSender()
        service = EmailService(sender=mock_sender)
        
        # Empty recipients should fail
        result = service.send_email(
            to=[],
            subject="Test Subject",
            body="Test Body"
        )
        
        assert result is False
