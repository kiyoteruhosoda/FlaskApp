"""Tests for ConsoleEmailSender."""

import pytest
from domain.email_sender.email_message import EmailMessage
from infrastructure.email_sender.console_sender import ConsoleEmailSender


class TestConsoleSender:
    """Test ConsoleEmailSender implementation."""

    def test_send_simple_message(self, caplog):
        """Test sending a simple message to console."""
        sender = ConsoleEmailSender()
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        result = sender.send(message)
        
        assert result is True
        assert "test@example.com" in caplog.text
        assert "Test Subject" in caplog.text

    def test_send_message_with_html(self, caplog):
        """Test sending a message with HTML body."""
        sender = ConsoleEmailSender()
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            html_body="<p>Test HTML Body</p>"
        )
        
        result = sender.send(message)
        
        assert result is True
        assert "<p>Test HTML Body</p>" in caplog.text

    def test_send_message_with_multiple_recipients(self, caplog):
        """Test sending a message with multiple recipients."""
        sender = ConsoleEmailSender()
        
        message = EmailMessage(
            to=["test1@example.com", "test2@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        result = sender.send(message)
        
        assert result is True
        assert "test1@example.com" in caplog.text
        assert "test2@example.com" in caplog.text

    def test_send_message_with_cc_and_bcc(self, caplog):
        """Test sending a message with CC and BCC."""
        sender = ConsoleEmailSender()
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"]
        )
        
        result = sender.send(message)
        
        assert result is True
        assert "cc@example.com" in caplog.text
        assert "bcc@example.com" in caplog.text

    def test_validate_config_always_returns_true(self):
        """Test that validate_config always returns True."""
        sender = ConsoleEmailSender()
        assert sender.validate_config() is True

    def test_format_message(self):
        """Test message formatting."""
        sender = ConsoleEmailSender()
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            from_address="sender@example.com"
        )
        
        formatted = sender._format_message(message)
        
        assert "From: sender@example.com" in formatted
        assert "To: test@example.com" in formatted
        assert "Subject: Test Subject" in formatted
        assert "Test Body" in formatted
