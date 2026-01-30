"""Email sender bounded context.

このパッケージはメール送信機能に関する境界文脈を提供します。
"""

# Re-export key domain interfaces for convenience
from .domain.email_message import EmailMessage
from .domain.sender_interface import EmailSender

__all__ = ["EmailMessage", "EmailSender"]