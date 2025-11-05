# Email Sender Infrastructure Layer

メール送信機能の具体的な実装を提供するインフラストラクチャ層です。

## 実装

### SmtpEmailSender

Flask-Mailを使用したSMTP送信実装です。

```python
from infrastructure.email_sender import SmtpEmailSender
from webapp.extensions import mail

sender = SmtpEmailSender(mail=mail, default_sender="sender@example.com")
```

### ConsoleEmailSender

コンソール出力によるメール送信実装です。テスト環境や開発環境で使用します。

```python
from infrastructure.email_sender import ConsoleEmailSender

sender = ConsoleEmailSender()
# メールはコンソールに出力されます
```

### EmailSenderFactory

設定に基づいて適切な実装を生成するファクトリです。

```python
from infrastructure.email_sender import EmailSenderFactory

# 設定から自動的に適切な実装を生成
sender = EmailSenderFactory.create()

# または明示的にプロバイダーを指定
sender = EmailSenderFactory.create(provider="console")
```

## 設定

### SMTP設定

```env
MAIL_PROVIDER=smtp
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@example.com
```

### Console設定（テスト用）

```env
MAIL_PROVIDER=console
```

## 新しい実装の追加

1. `IEmailSender` を実装したクラスを作成
2. `EmailSenderFactory` に新しいプロバイダーを登録
3. 必要な設定を `core/settings.py` に追加

詳細は [docs/email_module_architecture.md](../../docs/email_module_architecture.md) の「拡張方法」を参照してください。
