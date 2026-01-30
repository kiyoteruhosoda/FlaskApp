"""Application Service for email sending."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.sender_interface import EmailSender


@runtime_checkable
class EmailRepository(Protocol):
    """Repository for email-related persistence."""

    def save_sent_email(self, message: EmailMessage) -> None:
        """Save record of sent email."""
        ...

    def get_email_history(self, email: str) -> list[EmailMessage]:
        """Get email history for an address."""
        ...


@dataclass(slots=True)
class EmailService:
    """Application service for email operations."""

    sender: EmailSender
    repository: EmailRepository | None = None

    def send_email(self, message: EmailMessage) -> bool:
        """Send an email and optionally save to repository."""
        # Validate sender configuration
        if not self.sender.validate_config():
            raise ValueError("Email sender configuration is invalid")

        # Send the email
        success = self.sender.send(message)

        # Optionally save to repository if provided
        if success and self.repository:
            self.repository.save_sent_email(message)

        return success

    def can_send_emails(self) -> bool:
        """Check if the service can send emails."""
        return self.sender.validate_config()

    def get_email_history(self, email: str) -> list[EmailMessage]:
        """Get email history if repository is available."""
        if not self.repository:
            return []
        return self.repository.get_email_history(email)