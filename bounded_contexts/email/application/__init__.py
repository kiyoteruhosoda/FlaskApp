"""Email service application layer - Use cases and services.

このモジュールはメール送信機能のアプリケーション層を提供します。
アプリケーション層はユースケースを実装し、ドメイン層とインフラ層を橋渡しします。
"""

from .email_service import EmailService

__all__ = ["EmailService"]
