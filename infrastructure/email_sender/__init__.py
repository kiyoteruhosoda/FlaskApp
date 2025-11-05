"""Email sender infrastructure layer - Concrete implementations.

このモジュールはメール送信機能の具体的な実装を提供します。
各実装はドメイン層のIEmailSenderインターフェースを実装します。
"""

from .smtp_sender import SmtpEmailSender
from .console_sender import ConsoleEmailSender
from .factory import EmailSenderFactory

__all__ = ["SmtpEmailSender", "ConsoleEmailSender", "EmailSenderFactory"]
