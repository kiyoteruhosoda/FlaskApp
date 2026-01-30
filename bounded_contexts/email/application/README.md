# Email Service Application Layer

メール送信機能のアプリケーション層です。高レベルのメール送信サービスを提供します。

## EmailService

### 基本的な使用方法

```python
from application.email_service import EmailService

# デフォルト設定で初期化
email_service = EmailService()

# シンプルなメール送信
success = email_service.send_email(
    to=["user@example.com"],
    subject="Hello",
    body="This is a test email."
)

if success:
    print("Email sent successfully!")
```

### HTML メールの送信

```python
success = email_service.send_email(
    to=["user@example.com"],
    subject="HTML Email",
    body="Plain text version",
    html_body="<h1>HTML Version</h1><p>This is an HTML email.</p>"
)
```

### CC/BCC の使用

```python
success = email_service.send_email(
    to=["user@example.com"],
    subject="Meeting Invitation",
    body="You are invited to a meeting.",
    cc=["manager@example.com"],
    bcc=["admin@example.com"]
)
```

### パスワードリセットメール

```python
success = email_service.send_password_reset_email(
    email="user@example.com",
    reset_url="https://example.com/reset?token=abc123",
    validity_minutes=30
)
```

## カスタム送信実装の注入

テスト時などにカスタム実装を注入できます。

```python
from infrastructure.email_sender import ConsoleEmailSender

# コンソール実装を注入
console_sender = ConsoleEmailSender()
email_service = EmailService(sender=console_sender)

# メールはコンソールに出力されます
email_service.send_email(...)
```

## テスト

```python
from domain.email_sender import IEmailSender, EmailMessage

# Mock実装の作成
class MockEmailSender(IEmailSender):
    def __init__(self):
        self.sent_messages = []
    
    def send(self, message: EmailMessage) -> bool:
        self.sent_messages.append(message)
        return True
    
    def validate_config(self) -> bool:
        return True

# テストで使用
mock_sender = MockEmailSender()
email_service = EmailService(sender=mock_sender)
email_service.send_email(to=["test@example.com"], subject="Test", body="Test")

# 送信されたメッセージを確認
assert len(mock_sender.sent_messages) == 1
assert mock_sender.sent_messages[0].to == ["test@example.com"]
```

## 詳細なドキュメント

詳細は [docs/email_module_architecture.md](../../docs/email_module_architecture.md) を参照してください。
