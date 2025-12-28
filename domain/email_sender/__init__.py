"""Email sender domain layer - DDD architecture.

このモジュールはメール送信機能のドメイン層を提供します。
ドメイン層は具体的な実装に依存せず、契約（インターフェース）のみを定義します。
"""

from .sender_interface import IEmailSender
from .email_message import EmailMessage

__all__ = ["IEmailSender", "EmailMessage"]
