"""Email sender bounded context.

このパッケージはメール送信機能に関する境界文脈を提供します。
"""

# Re-export key domain interfaces and the infrastructure factory for convenience.
# ``IEmailSender`` は旧名の後方互換エイリアス。``EmailSenderFactory`` は
# 上位（email 文脈）から ``from bounded_contexts.email_sender import EmailSenderFactory``
# で参照されるため、ここで再エクスポートする。
from .domain.email_message import EmailMessage
from .domain.sender_interface import EmailSender, IEmailSender
from .infrastructure.factory import EmailSenderFactory

__all__ = ["EmailMessage", "EmailSender", "IEmailSender", "EmailSenderFactory"]