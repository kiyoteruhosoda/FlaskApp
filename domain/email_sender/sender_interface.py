"""Email sender interface - Domain layer contract.

このインターフェースはメール送信機能の契約を定義します。
具体的な実装（SMTP, API, Console等）はInfrastructure層で提供されます。
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from .email_message import EmailMessage


class IEmailSender(ABC):
    """メール送信インターフェース.
    
    このインターフェースはStrategy パターンの抽象戦略として機能します。
    異なる実装（SMTP, API, Console）を切り替え可能にします。
    """

    @abstractmethod
    def send(self, message: EmailMessage) -> bool:
        """メールを送信する.
        
        Args:
            message: 送信するメールメッセージ
            
        Returns:
            bool: 送信に成功した場合True、失敗した場合False
            
        Raises:
            Exception: 送信中にエラーが発生した場合
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """設定が有効かどうかを検証する.
        
        Returns:
            bool: 設定が有効な場合True、無効な場合False
        """
        pass
