"""Console Email Sender for testing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.sender_interface import EmailSender


@dataclass(slots=True)
class ConsoleEmailSender:
    """Email sender that prints to console for testing."""

    logger: logging.Logger | None = None

    def __post_init__(self) -> None:
        """Initialize logger if not provided."""
        if self.logger is None:
            self.logger = logging.getLogger(__name__)

    def send(self, message: EmailMessage) -> bool:
        """Print email message to console."""
        self.logger.info("=== Email Message ===")
        self.logger.info("To: %s", ", ".join(message.to))
        if message.cc:
            self.logger.info("CC: %s", ", ".join(message.cc))
        if message.bcc:
            self.logger.info("BCC: %s", ", ".join(message.bcc))
        self.logger.info("Subject: %s", message.subject)
        self.logger.info("Body: %s", message.body)
        if message.html_body:
            self.logger.info("HTML Body: %s", message.html_body)
        self.logger.info("==================")
        return True

    def validate_config(self) -> bool:
        """Always returns True for console sender."""
        return True

    def format_message(self, message: EmailMessage) -> str:
        """Format message as string for testing."""
        lines = [
            "=== Email Message ===",
            f"To: {', '.join(message.to)}",
        ]
        
        if message.cc:
            lines.append(f"CC: {', '.join(message.cc)}")
        if message.bcc:
            lines.append(f"BCC: {', '.join(message.bcc)}")
            
        lines.extend([
            f"Subject: {message.subject}",
            f"Body: {message.body}",
        ])
        
        if message.html_body:
            lines.append(f"HTML Body: {message.html_body}")
            
        lines.append("==================")
        return "\n".join(lines)