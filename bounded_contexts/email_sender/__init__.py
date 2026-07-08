"""Email sender bounded context.

このパッケージはメール送信機能に関する境界文脈を提供します。
高レベルのメール送信サービス（EmailService）と、ドメインインターフェース・
インフラ実装をまとめて提供します。
"""

from .application.email_service import EmailService, EmailRepository
from .domain.email_message import EmailMessage
from .domain.sender_interface import EmailSender, IEmailSender
from .infrastructure.factory import EmailSenderFactory

__all__ = [
    "EmailService",
    "EmailRepository",
    "EmailMessage",
    "EmailSender",
    "IEmailSender",
    "EmailSenderFactory",
]