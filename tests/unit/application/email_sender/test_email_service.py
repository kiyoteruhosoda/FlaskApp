"""Tests for EmailService application layer."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock

from bounded_contexts.email_sender.application.email_service import EmailService, EmailRepository
from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.sender_interface import EmailSender


class TestEmailService:
    """Test EmailService application layer."""

    def test_send_email_success(self):
        """Test successful email sending."""
        # Arrange
        mock_sender = Mock(spec=EmailSender)
        mock_sender.validate_config.return_value = True
        mock_sender.send.return_value = True

        mock_repository = Mock(spec=EmailRepository)
        
        service = EmailService(sender=mock_sender, repository=mock_repository)
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            from_address="sender@example.com"
        )

        # Act
        result = service.send_email(message)

        # Assert
        assert result is True
        mock_sender.validate_config.assert_called_once()
        mock_sender.send.assert_called_once_with(message)
        mock_repository.save_sent_email.assert_called_once_with(message)

    def test_send_email_without_repository(self):
        """Test email sending without repository."""
        # Arrange
        mock_sender = Mock(spec=EmailSender)
        mock_sender.validate_config.return_value = True
        mock_sender.send.return_value = True
        
        service = EmailService(sender=mock_sender)  # No repository
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            from_address="sender@example.com"
        )

        # Act
        result = service.send_email(message)

        # Assert
        assert result is True
        mock_sender.validate_config.assert_called_once()
        mock_sender.send.assert_called_once_with(message)

    def test_send_email_invalid_config(self):
        """Test email sending with invalid configuration."""
        # Arrange
        mock_sender = Mock(spec=EmailSender)
        mock_sender.validate_config.return_value = False
        
        service = EmailService(sender=mock_sender)
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            from_address="sender@example.com"
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Email sender configuration is invalid"):
            service.send_email(message)

        mock_sender.validate_config.assert_called_once()
        mock_sender.send.assert_not_called()

    def test_send_email_failure_no_save(self):
        """Test that failed emails are not saved to repository."""
        # Arrange
        mock_sender = Mock(spec=EmailSender)
        mock_sender.validate_config.return_value = True
        mock_sender.send.return_value = False  # Sending fails

        mock_repository = Mock(spec=EmailRepository)
        
        service = EmailService(sender=mock_sender, repository=mock_repository)
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            from_address="sender@example.com"
        )

        # Act
        result = service.send_email(message)

        # Assert
        assert result is False
        mock_sender.send.assert_called_once_with(message)
        mock_repository.save_sent_email.assert_not_called()  # Should not save failed emails

    def test_can_send_emails(self):
        """Test checking if service can send emails."""
        # Arrange
        mock_sender = Mock(spec=EmailSender)
        mock_sender.validate_config.return_value = True
        
        service = EmailService(sender=mock_sender)

        # Act
        result = service.can_send_emails()

        # Assert
        assert result is True
        mock_sender.validate_config.assert_called_once()

    def test_get_email_history_with_repository(self):
        """Test getting email history with repository."""
        # Arrange
        mock_sender = Mock(spec=EmailSender)
        mock_repository = Mock(spec=EmailRepository)
        
        expected_history = [
            EmailMessage(
                to=["user@example.com"],
                subject="Past Email 1",
                body="Body 1",
                from_address="sender@example.com"
            ),
            EmailMessage(
                to=["user@example.com"],
                subject="Past Email 2", 
                body="Body 2",
                from_address="sender@example.com"
            )
        ]
        mock_repository.get_email_history.return_value = expected_history
        
        service = EmailService(sender=mock_sender, repository=mock_repository)

        # Act
        history = service.get_email_history("user@example.com")

        # Assert
        assert history == expected_history
        mock_repository.get_email_history.assert_called_once_with("user@example.com")

    def test_get_email_history_without_repository(self):
        """Test getting email history without repository."""
        # Arrange
        mock_sender = Mock(spec=EmailSender)
        service = EmailService(sender=mock_sender)  # No repository

        # Act
        history = service.get_email_history("user@example.com")

        # Assert
        assert history == []

    def test_polymorphic_sender_usage(self):
        """Test that service works with different sender implementations."""
        from tests.helpers.email_sender import ConsoleEmailSender
        
        # Test with ConsoleEmailSender
        console_sender = ConsoleEmailSender()
        service = EmailService(sender=console_sender)
        
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            from_address="sender@example.com"
        )
        
        # Should work polymorphically
        can_send = service.can_send_emails()
        assert can_send is True
        
        result = service.send_email(message)
        assert result is True