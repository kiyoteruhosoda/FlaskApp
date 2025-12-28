"""Console email sender implementation - Infrastructure layer.

このモジュールはコンソール出力によるメール送信の実装を提供します。
テスト環境や開発環境で実際にメールを送信せずに動作を確認できます。
"""

import logging
from typing import Optional

from domain.email_sender.sender_interface import IEmailSender
from domain.email_sender.email_message import EmailMessage


logger = logging.getLogger(__name__)


class ConsoleEmailSender(IEmailSender):
    """コンソール出力によるメール送信実装.
    
    メールを実際には送信せず、コンソール（ログ）に出力します。
    テスト環境や開発環境で使用することを想定しています。
    
    Attributes:
        log_level: ログレベル（デフォルト: INFO）
    """

    def __init__(self, log_level: int = logging.INFO):
        """初期化.
        
        Args:
            log_level: ログレベル（デフォルト: INFO）
        """
        self.log_level = log_level

    def send(self, message: EmailMessage) -> bool:
        """メールをコンソールに出力する.
        
        Args:
            message: 送信するメールメッセージ
            
        Returns:
            bool: 常にTrue（コンソール出力は常に成功）
        """
        # メール内容をコンソールに出力
        output = self._format_message(message)
        logger.log(
            self.log_level,
            output,
            extra={
                "event": "email.console.sent",
                "to": message.to,
                "subject": message.subject
            }
        )
        
        # コンソールにも直接出力（開発時の視認性向上）
        print("\n" + "=" * 80)
        print("📧 EMAIL (Console Mock)")
        print("=" * 80)
        print(output)
        print("=" * 80 + "\n")
        
        return True

    def validate_config(self) -> bool:
        """設定が有効かどうかを検証する.
        
        コンソール送信は設定不要のため、常にTrueを返します。
        
        Returns:
            bool: 常にTrue
        """
        return True

    def _format_message(self, message: EmailMessage) -> str:
        """メッセージを人間が読みやすい形式にフォーマットする.
        
        Args:
            message: メールメッセージ
            
        Returns:
            str: フォーマットされたメッセージ
        """
        lines = []
        
        # ヘッダー情報
        lines.append(f"From: {message.from_address or '(default sender)'}")
        lines.append(f"To: {', '.join(message.to)}")
        
        if message.cc:
            lines.append(f"CC: {', '.join(message.cc)}")
        
        if message.bcc:
            lines.append(f"BCC: {', '.join(message.bcc)}")
        
        if message.reply_to:
            lines.append(f"Reply-To: {message.reply_to}")
        
        lines.append(f"Subject: {message.subject}")
        lines.append("")
        
        # 本文
        lines.append("--- Plain Text Body ---")
        lines.append(message.body)
        
        # HTML本文（存在する場合）
        if message.html_body:
            lines.append("")
            lines.append("--- HTML Body ---")
            lines.append(message.html_body)
        
        return "\n".join(lines)
