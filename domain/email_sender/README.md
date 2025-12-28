# Email Sender Domain Layer

メール送信機能のドメイン層です。このレイヤーは具体的な実装に依存せず、契約（インターフェース）のみを定義します。

## コンポーネント

### IEmailSender (インターフェース)

メール送信の抽象化されたインターフェースです。

```python
from domain.email_sender import IEmailSender

class MyEmailSender(IEmailSender):
    def send(self, message: EmailMessage) -> bool:
        # 実装
        pass

    def validate_config(self) -> bool:
        # 実装
        pass
```

### EmailMessage (値オブジェクト)

メールメッセージを表す不変の値オブジェクトです。

```python
from domain.email_sender import EmailMessage

message = EmailMessage(
    to=["user@example.com"],
    subject="Test Subject",
    body="Test Body",
    html_body="<p>Test Body</p>",  # オプション
    from_address="sender@example.com",  # オプション
    cc=["cc@example.com"],  # オプション
    bcc=["bcc@example.com"],  # オプション
    reply_to="reply@example.com"  # オプション
)
```

## 設計原則

* **不変性**: EmailMessage は `frozen=True` で定義され、作成後に変更できません
* **バリデーション**: EmailMessage はコンストラクタでバリデーションを実行します
* **依存性逆転**: Infrastructure層はこのDomain層に依存します（逆ではありません）

## 詳細なドキュメント

詳細は [docs/email_module_architecture.md](../../docs/email_module_architecture.md) を参照してください。
