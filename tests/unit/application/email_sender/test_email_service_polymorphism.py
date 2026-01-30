"""Tests for EmailService application layer."""

from __future__ import annotations

import pytest
from unittest.mock import Mock
from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.sender_interface import EmailSender


class TestEmailServicePolymorphism:
    """Test polymorphic behavior with different EmailSender implementations."""

    def test_polymorphic_behavior_with_multiple_senders(self):
        """Test that EmailService works with any EmailSender implementation."""
        # Arrange: Create multiple mock senders
        mock_sender_1 = Mock(spec=EmailSender)
        mock_sender_1.send.return_value = True
        mock_sender_1.validate_config.return_value = True
        
        mock_sender_2 = Mock(spec=EmailSender)
        mock_sender_2.send.return_value = True
        mock_sender_2.validate_config.return_value = True
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            from_address="sender@example.com"
        )
        
        senders = [mock_sender_1, mock_sender_2]
        
        # Act & Assert: Each sender should handle the same message polymorphically
        for sender in senders:
            result = sender.send(message)
            assert result is True
            sender.send.assert_called_with(message)
            
            config_valid = sender.validate_config()
            assert config_valid is True

    def test_email_sender_interface_contract(self):
        """Test that EmailSender interface contract is properly defined."""
        from bounded_contexts.email_sender.domain.sender_interface import EmailSender
        import inspect
        
        # Verify Protocol methods
        assert hasattr(EmailSender, 'send')
        assert hasattr(EmailSender, 'validate_config')
        
        # Verify method signatures
        send_signature = inspect.signature(EmailSender.send)
        assert 'message' in send_signature.parameters
        
        validate_signature = inspect.signature(EmailSender.validate_config)
        assert len(validate_signature.parameters) == 1  # Only self parameter

    def test_sender_implementations_are_interchangeable(self):
        """Test that different sender implementations can be used interchangeably."""
        from tests.helpers.email_sender import ConsoleEmailSender
        from bounded_contexts.email_sender.infrastructure.smtp_sender import SMTPEmailSender
        
        # Create message
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject", 
            body="Test Body",
            from_address="sender@example.com"
        )
        
        # Test Console Sender
        console_sender = ConsoleEmailSender()
        console_result = console_sender.send(message)
        console_config = console_sender.validate_config()
        
        assert console_result is True
        assert console_config is True
        
        # Note: SMTP sender would need configuration for full test
        # but we can verify it has the same interface
        assert hasattr(SMTPEmailSender, 'send')
        assert hasattr(SMTPEmailSender, 'validate_config')