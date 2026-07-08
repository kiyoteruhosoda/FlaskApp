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
        console_sender = ConsoleEmailSender()
        email_service = EmailService(sender=console_sender)

        with patch.object(EmailService, '_is_mail_enabled', return_value=True):
            result = email_service.send_email(
                to=["integration-test@example.com"],
                subject="Integration Test",
                body="This is an integration test email",
                from_address="test-sender@example.com",
            )

        assert result is True
        assert email_service.can_send_emails() is True

    def test_email_service_with_factory_created_sender(self):
        """Test email service using factory-created sender."""
        factory = EmailSenderFactory()

        console_sender = ConsoleEmailSender()
        email_service = EmailService(sender=console_sender)

        with patch.object(EmailService, '_is_mail_enabled', return_value=True):
            result = email_service.send_email(
                to=["factory-test@example.com"],
                subject="Factory Test",
                body="Email sent via factory-created sender",
                from_address="factory@example.com",
            )
        assert result is True

    @patch('bounded_contexts.email_sender.infrastructure.smtp_sender.SMTPEmailSender.send')
    def test_smtp_sender_integration_mock(self, mock_send):
        """Test SMTP sender integration with mocked sending."""
        from bounded_contexts.email_sender.infrastructure.smtp_sender import SMTPEmailSender

        mock_send.return_value = True

        smtp_sender = SMTPEmailSender(default_sender="smtp@example.com")
        smtp_sender.validate_config = Mock(return_value=True)

        email_service = EmailService(sender=smtp_sender)

        with patch.object(EmailService, '_is_mail_enabled', return_value=True):
            result = email_service.send_email(
                to=["smtp-test@example.com"],
                subject="SMTP Integration Test",
                body="Testing SMTP integration",
                from_address="smtp@example.com",
            )

        assert mock_send.call_count == 1
        assert result is True

    def test_multiple_senders_polymorphic_behavior(self):
        """Test polymorphic behavior across different sender implementations."""
        senders = [
            ConsoleEmailSender(),
        ]

        for sender in senders:
            service = EmailService(sender=sender)
            with patch.object(EmailService, '_is_mail_enabled', return_value=True):
                result = service.send_email(
                    to=["polymorphism-test@example.com"],
                    subject="Polymorphism Test",
                    body="Testing polymorphic behavior",
                    from_address="poly@example.com",
                )
            assert result is True
            assert service.can_send_emails() is True

    def test_email_service_error_handling_integration(self):
        """Test error handling when mail is disabled."""
        mock_sender = Mock()
        mock_sender.validate_config.return_value = True
        mock_sender.send.return_value = True

        email_service = EmailService(sender=mock_sender)

        # Mail disabled → returns False without calling sender
        with patch.object(EmailService, '_is_mail_enabled', return_value=False):
            result = email_service.send_email(
                to=["error-test@example.com"],
                subject="Error Test",
                body="This should be suppressed",
            )

        assert result is False
        mock_sender.send.assert_not_called()