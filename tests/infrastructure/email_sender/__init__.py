"""Test utilities for email sender infrastructure.

このモジュールはテスト専用のメール送信実装を提供します。
本番環境では使用できません。
"""

from .console_sender import ConsoleEmailSender
from .factory import TestEmailSenderFactory

__all__ = ["ConsoleEmailSender", "TestEmailSenderFactory"]
