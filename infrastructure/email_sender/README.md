# Email Sender Infrastructure Layer

メール送信機能の具体的な実装を提供するインフラストラクチャ層です。

## 実装

### SmtpEmailSender

Flask-Mailを使用したSMTP送信実装です。本番環境で使用します。

```python
from infrastructure.email_sender import SmtpEmailSender
from webapp.extensions import mail

sender = SmtpEmailSender(mail=mail, default_sender="sender@example.com")
```

### ConsoleEmailSender（テスト専用）

コンソール出力によるメール送信実装です。**テスト環境専用**です。

この実装は `tests/infrastructure/email_sender/` に移動されました。

```python
# テストでのみ使用可能
from tests.infrastructure.email_sender import ConsoleEmailSender

sender = ConsoleEmailSender()
# メールはコンソールに出力されます（実際には送信されません）
```

### EmailSenderFactory（本番環境用）

設定に基づいて適切な実装を生成するファクトリです。**本番環境ではSMTPのみサポート**します。

```python
from infrastructure.email_sender import EmailSenderFactory

# 設定から自動的にSMTP実装を生成
sender = EmailSenderFactory.create()

# または明示的にプロバイダーを指定（smtpのみ）
sender = EmailSenderFactory.create(provider="smtp")
```

### TestEmailSenderFactory（テスト専用）

テスト環境でConsoleEmailSenderを使用する場合は、テスト専用のファクトリを使用します。

```python
# テストでのみ使用可能
from tests.infrastructure.email_sender import TestEmailSenderFactory

# テスト用のコンソール実装を生成
sender = TestEmailSenderFactory.create(provider="console")
```

## 設定

### SMTP設定（本番環境）

本番環境では `smtp` のみが有効です。

```env
MAIL_PROVIDER=smtp
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@example.com
```

**注意:** `MAIL_PROVIDER=console` は本番環境では使用できません。テスト専用です。

## 新しい実装の追加

1. `IEmailSender` を実装したクラスを作成
2. `EmailSenderFactory` に新しいプロバイダーを登録
3. 必要な設定を `core/settings.py` に追加

詳細は [docs/email_module_architecture.md](../../docs/email_module_architecture.md) の「拡張方法」を参照してください。
