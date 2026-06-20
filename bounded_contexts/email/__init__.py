"""Email bounded context.

メール送信のユースケース（テンプレート整形・各種通知メール）を提供する。
送信そのものは ``email_sender`` 文脈の実装へ委譲する。
"""

from .application.email_service import EmailService

__all__ = ["EmailService"]
