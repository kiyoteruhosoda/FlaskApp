"""Console email sender implementation - Infrastructure layer (Test only).

このモジュールはコンソール出力によるメール送信の実装を提供します。
テスト環境や開発環境で実際にメールを送信せずに動作を確認できます。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from domain.email_sender.email_message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass
class ConsoleEmailSender:
    """コンソール出力によるメール送信実装.

    メールを実際には送信せず、コンソール（ログ）に出力します。
    テスト環境や開発環境で使用することを想定しています。

    Note:
        Protocol (EmailSender) の構造的部分型付けに準拠。
        明示的な継承は不要です。
    """

    log_level: int = logging.INFO
    _logger: logging.Logger = field(default_factory=lambda: logger)

    def send(self, message: EmailMessage) -> bool:
        """メールをコンソールに出力する.

        Args:
            message: 送信するメールメッセージ

        Returns:
            bool: 常にTrue（コンソール出力は常に成功）
        """
        output = self._format_message(message)
        self._logger.log(
            self.log_level,
            output,
            extra={
                "event": "email.console.sent",
                "to": message.to,
                "subject": message.subject,
            },
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
        """
        return True

    @staticmethod
    def _format_message(message: EmailMessage) -> str:
        """メッセージを人間が読みやすい形式にフォーマットする."""
        lines = [
            f"From: {message.from_address or '(default sender)'}",
            f"To: {', '.join(message.to)}",
        ]

        if message.cc:
            lines.append(f"CC: {', '.join(message.cc)}")

        if message.bcc:
            lines.append(f"BCC: {', '.join(message.bcc)}")

        if message.reply_to:
            lines.append(f"Reply-To: {message.reply_to}")

        lines.extend([
            f"Subject: {message.subject}",
            "",
            "--- Plain Text Body ---",
            message.body,
        ])

        if message.html_body:
            lines.extend([
                "",
                "--- HTML Body ---",
                message.html_body,
            ])

        return "\n".join(lines)


__all__ = ["ConsoleEmailSender"]
