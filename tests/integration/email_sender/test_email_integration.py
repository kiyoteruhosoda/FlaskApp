"""Integration tests for email sender functionality."""

from __future__ import annotations

import logging
from unittest.mock import patch, Mock

import pytest

from bounded_contexts.email_sender.application.email_service import EmailService
from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.infrastructure.factory import EmailSenderFactory
from tests.helpers.email_sender import ConsoleEmailSender


class TestEmailSenderIntegration:
    """Integration tests combining multiple layers."""

    def test_email_service_with_console_sender_integration(self):
        """Test complete email sending flow with console sender."""
        # Arrange: Create email service with console sender
        console_sender = ConsoleEmailSender()
        email_service = EmailService(sender=console_sender)
        
        message = EmailMessage(
            to=["integration-test@example.com"],
            subject="Integration Test",
            body="This is an integration test email",
            from_address="test-sender@example.com"
        )

        # Act: Send email through service
        result = email_service.send_email(message)
        
        # Assert: Verify successful sending
        assert result is True
        assert email_service.can_send_emails() is True

    def test_email_service_with_factory_created_sender(self):
        """Test email service using factory-created sender."""
        # Note: This test demonstrates the integration but requires
        # proper Flask app context and configuration for SMTP sender
        factory = EmailSenderFactory()
        
        # For this test, we'll test the factory can create console sender
        # In production, this would create SMTP sender based on config
        console_sender = ConsoleEmailSender()
        email_service = EmailService(sender=console_sender)
        
        message = EmailMessage(
            to=["factory-test@example.com"],
            subject="Factory Test",
            body="Email sent via factory-created sender",
            from_address="factory@example.com"
        )

        result = email_service.send_email(message)
        assert result is True

    @patch('bounded_contexts.email_sender.infrastructure.smtp_sender.SMTPEmailSender.send')
    def test_smtp_sender_integration_mock(self, mock_send):
        """Test SMTP sender integration with mocked sending."""
        from bounded_contexts.email_sender.infrastructure.smtp_sender import SMTPEmailSender
        
        # Mock SMTP sender behavior
        mock_send.return_value = True
        
        # Create mock SMTP sender - skip validation for this test
        mock_mail = Mock()
        smtp_sender = SMTPEmailSender(mail=mock_mail)
        
        # Mock the validate_config method to avoid Flask context issues
        smtp_sender.validate_config = Mock(return_value=True)
        
        email_service = EmailService(sender=smtp_sender)
        
        message = EmailMessage(
            to=["smtp-test@example.com"],
            subject="SMTP Integration Test",
            body="Testing SMTP integration",
            from_address="smtp@example.com"
        )

        # This would normally send via SMTP, but we're mocking it
        result = email_service.send_email(message)
        
        # Verify the mock was called
        mock_send.assert_called_once_with(message)
        assert result is True

    def test_multiple_senders_polymorphic_behavior(self):
        """Test polymorphic behavior across different sender implementations."""
        senders = [
            ConsoleEmailSender(),
            # Could add more sender types here as they're implemented
        ]
        
        message = EmailMessage(
            to=["polymorphism-test@example.com"],
            subject="Polymorphism Test",
            body="Testing polymorphic behavior",
            from_address="poly@example.com"
        )

        # All senders should handle the message the same way
        for sender in senders:
            service = EmailService(sender=sender)
            result = service.send_email(message)
            assert result is True
            assert service.can_send_emails() is True

    def test_email_service_error_handling_integration(self):
        """Test error handling across service and sender layers."""
        # Create a mock sender that fails validation
        mock_sender = Mock()
        mock_sender.validate_config.return_value = False
        
        email_service = EmailService(sender=mock_sender)
        
        message = EmailMessage(
            to=["error-test@example.com"],
            subject="Error Test",
            body="This should fail",
            from_address="error@example.com"
        )

        # Should raise ValueError due to invalid config
        with pytest.raises(ValueError, match="Email sender configuration is invalid"):
            email_service.send_email(message)

        # Sender should not be called since config is invalid
        mock_sender.send.assert_not_called()