"""Tests for ConsoleEmailSender."""

import logging
import pytest
from bounded_contexts.email_sender.domain.email_message import EmailMessage
from tests.helpers.email_sender import ConsoleEmailSender


class TestConsoleSender:
    """Test ConsoleEmailSender implementation."""

    def test_send_simple_message(self, caplog, capsys):
        """Test sending a simple message to console."""
        caplog.set_level(logging.INFO)
        sender = ConsoleEmailSender()
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        result = sender.send(message)
        
        assert result is True
        # 標準出力またはログに出力されていることを確認
        captured = capsys.readouterr()
        output_text = captured.out + caplog.text
        assert "test@example.com" in output_text
        assert "Test Subject" in output_text

    def test_send_message_with_html(self, caplog, capsys):
        """Test sending a message with HTML body."""
        caplog.set_level(logging.INFO)
        sender = ConsoleEmailSender()
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            html_body="<p>Test HTML Body</p>"
        )
        
        result = sender.send(message)
        
        assert result is True
        captured = capsys.readouterr()
        output_text = captured.out + caplog.text
        assert "<p>Test HTML Body</p>" in output_text

    def test_send_message_with_multiple_recipients(self, caplog, capsys):
        """Test sending a message with multiple recipients."""
        caplog.set_level(logging.INFO)
        sender = ConsoleEmailSender()
        
        message = EmailMessage(
            to=["test1@example.com", "test2@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        result = sender.send(message)
        
        assert result is True
        captured = capsys.readouterr()
        output_text = captured.out + caplog.text
        assert "test1@example.com" in output_text
        assert "test2@example.com" in output_text

    def test_send_message_with_cc_and_bcc(self, caplog, capsys):
        """Test sending a message with CC and BCC."""
        caplog.set_level(logging.INFO)
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
        captured = capsys.readouterr()
        output_text = captured.out + caplog.text
        assert "cc@example.com" in output_text
        assert "bcc@example.com" in output_text

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
        
        formatted = sender.format_message(message)
        
        assert "To: test@example.com" in formatted
        assert "Subject: Test Subject" in formatted
        assert "Test Body" in formatted
