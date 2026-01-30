"""Email message value object - Domain layer.

このモジュールはメールメッセージを表す値オブジェクトを提供します。
値オブジェクトは不変（immutable）であり、ビジネスロジックをカプセル化します。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """メールメッセージを表す値オブジェクト.

    このクラスは不変（frozen=True）であり、作成後に変更することはできません。
    メールの送信に必要な全ての情報を保持します。

    Attributes:
        to: 送信先メールアドレスのリスト
        subject: メールの件名
        body: メールの本文（プレーンテキスト）
        html_body: メールのHTML本文（オプション）
        from_address: 送信元メールアドレス（オプション、設定から自動取得される場合がある）
        cc: CCメールアドレスのリスト（オプション）
        bcc: BCCメールアドレスのリスト（オプション）
        reply_to: 返信先メールアドレス（オプション）
    """

    to: list[str]
    subject: str
    body: str
    html_body: str | None = None
    from_address: str | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None
    reply_to: str | None = None

    # バリデーション用の最小メールアドレス長
    _MIN_EMAIL_LENGTH: ClassVar[int] = 3

    def __post_init__(self) -> None:
        """バリデーション実行."""
        self._validate_required_fields()
        self._validate_email_addresses()

    def _validate_required_fields(self) -> None:
        """必須フィールドのバリデーション."""
        if not self.to:
            raise ValueError("受信者が指定されていません")
        if not self.subject:
            raise ValueError("件名が指定されていません")
        if not self.body:
            raise ValueError("本文が指定されていません")

    def _validate_email_addresses(self) -> None:
        """すべてのメールアドレスをバリデーション."""
        for email in self.to:
            if not self._is_valid_email(email):
                raise ValueError(f"無効なメールアドレス: {email}")

        if self.cc:
            for email in self.cc:
                if not self._is_valid_email(email):
                    raise ValueError(f"無効なCCメールアドレス: {email}")

        if self.bcc:
            for email in self.bcc:
                if not self._is_valid_email(email):
                    raise ValueError(f"無効なBCCメールアドレス: {email}")

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """メールアドレスの基本的な検証.

        Args:
            email: 検証するメールアドレス

        Returns:
            bool: 有効な場合True
        """
        if not email or not isinstance(email, str):
            return False
        # 簡易的な検証（@が含まれていることのみ）
        # 本格的な検証が必要な場合は、email-validatorライブラリを使用
        return "@" in email and len(email) > EmailMessage._MIN_EMAIL_LENGTH
