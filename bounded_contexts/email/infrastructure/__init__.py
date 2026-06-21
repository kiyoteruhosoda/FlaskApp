"""Email sender infrastructure layer - Concrete implementations.

このモジュールはメール送信機能の具体的な実装を提供します。
各実装はドメイン層のIEmailSenderインターフェースを実装します。

Note:
    ConsoleEmailSenderはテスト専用のため、tests/infrastructure/email_sender/ に移動しました。
"""

from .smtp_sender import SmtpEmailSender
from .factory import EmailSenderFactory

__all__ = ["SmtpEmailSender", "EmailSenderFactory"]
