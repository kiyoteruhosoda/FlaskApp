"""Email sender interface - Domain layer contract.

このインターフェースはメール送信機能の契約を定義します。
具体的な実装（SMTP, API, Console等）はInfrastructure層で提供されます。

Python 3.11+ の Protocol を使用し、構造的部分型付けを実現します。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .email_message import EmailMessage


@runtime_checkable
class EmailSender(Protocol):
    """メール送信インターフェース（Protocol）.

    構造的部分型付けにより、メソッドシグネチャが一致すれば
    明示的な継承なしにこのプロトコルを実装したとみなされます。

    Note:
        - 旧名 `IEmailSender` との互換性のためエイリアスを提供
        - @runtime_checkable により isinstance() チェックが可能
    """

    def send(self, message: EmailMessage) -> bool:
        """メールを送信する.

        Args:
            message: 送信するメールメッセージ

        Returns:
            bool: 送信に成功した場合True、失敗した場合False

        Raises:
            Exception: 送信中にエラーが発生した場合
        """
        ...

    def validate_config(self) -> bool:
        """設定が有効かどうかを検証する.

        Returns:
            bool: 設定が有効な場合True、無効な場合False
        """
        ...


# 後方互換性のためのエイリアス
IEmailSender = EmailSender
