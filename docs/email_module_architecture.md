# メール送信モジュール設計・実装ドキュメント

**方式：DDD + OOP + Strategy + DI**  
**目的：メール送信手段の切替（SMTP / Console（テスト用））を実現**

---

## 📋 概要

本モジュールは、メール送信機能をドメイン駆動設計（DDD）に基づき分離し、**実装を差し替え可能な戦略パターン**として構築しています。

### ✨ 特徴

* メール送信をサービスとして統一抽象化
* SMTP / Console（テスト用） の複数実装
* 設定値により送信方式を切替
* ドメイン層はインターフェースのみ保持
* Infrastructure層に具体実装
* DI (Dependency Injection) 適用

---

## 🏗 アーキテクチャ構成

### レイヤー構成（DDD）

| Layer          | 役割            | コンポーネント                                    |
| -------------- | ------------- | ------------------------------------------ |
| Presentation   | UI・Controller | webapp.services.PasswordResetService       |
| Application    | ユースケース        | application.email_service.EmailService     |
| Domain         | 契約・抽象         | domain.email_sender.IEmailSender           |
| Infrastructure | 具象実装          | infrastructure.email_sender.SmtpEmailSender, ConsoleEmailSender |

### ディレクトリ構造

```
domain/email_sender/
  ├── __init__.py
  ├── sender_interface.py      # IEmailSender インターフェース
  └── email_message.py          # EmailMessage 値オブジェクト

infrastructure/email_sender/
  ├── __init__.py
  ├── smtp_sender.py            # SMTP実装
  ├── console_sender.py         # コンソール実装（テスト用）
  └── factory.py                # EmailSenderFactory (DI)

application/email_service/
  ├── __init__.py
  └── email_service.py          # EmailService アプリケーションサービス

tests/
  ├── domain/email_sender/
  │   └── test_email_message.py
  ├── infrastructure/email_sender/
  │   └── test_console_sender.py
  └── application/email_service/
      └── test_email_service.py
```

---

## 🧩 コンポーネント詳細

### 1. Domain層

#### IEmailSender（インターフェース）

メール送信の契約を定義します。すべての実装はこのインターフェースを満たす必要があります。

```python
class IEmailSender(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> bool:
        """メールを送信する"""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """設定が有効かどうかを検証する"""
        pass
```

#### EmailMessage（値オブジェクト）

メールメッセージを表す不変の値オブジェクトです。

```python
@dataclass(frozen=True)
class EmailMessage:
    to: List[str]
    subject: str
    body: str
    html_body: Optional[str] = None
    from_address: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    reply_to: Optional[str] = None
```

### 2. Infrastructure層

#### SmtpEmailSender（SMTP実装）

Flask-Mailを使用してSMTPプロトコル経由でメールを送信します。

```python
class SmtpEmailSender(IEmailSender):
    def __init__(self, mail: Mail, default_sender: Optional[str] = None):
        self.mail = mail
        self.default_sender = default_sender

    def send(self, message: EmailMessage) -> bool:
        # Flask-Mail経由でSMTP送信
        ...
```

#### ConsoleEmailSender（コンソール実装）

メールをコンソールに出力します。テスト環境や開発環境で使用します。

```python
class ConsoleEmailSender(IEmailSender):
    def send(self, message: EmailMessage) -> bool:
        # コンソールにメール内容を出力
        print(f"To: {message.to}")
        print(f"Subject: {message.subject}")
        ...
        return True
```

#### EmailSenderFactory（ファクトリ）

設定に基づいて適切な実装を生成します。

```python
class EmailSenderFactory:
    PROVIDER_SMTP = "smtp"
    PROVIDER_CONSOLE = "console"

    @staticmethod
    def create(provider: Optional[str] = None) -> IEmailSender:
        # 設定からプロバイダーを決定し、適切な実装を生成
        ...
```

### 3. Application層

#### EmailService（アプリケーションサービス）

高レベルのメール送信機能を提供します。

```python
class EmailService:
    def __init__(self, sender: Optional[IEmailSender] = None):
        if sender is None:
            sender = EmailSenderFactory.create()
        self.sender = sender

    def send_email(self, to: List[str], subject: str, body: str, ...) -> bool:
        message = EmailMessage(to=to, subject=subject, body=body, ...)
        return self.sender.send(message)

    def send_password_reset_email(self, email: str, reset_url: str, ...) -> bool:
        # パスワードリセット用の特化メソッド
        ...
```

---

## ⚙️ 設定

### 環境変数

`.env` または環境変数で設定します。

```env
# メールプロバイダー（smtp または console）
MAIL_PROVIDER=smtp

# SMTP設定（MAIL_PROVIDER=smtp の場合）
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@example.com
```

### core/settings.py

```python
@property
def mail_provider(self) -> str:
    """メールプロバイダーを取得（smtp, console）"""
    value = self._get("MAIL_PROVIDER", "smtp")
    return str(value).lower().strip()
```

---

## 🔄 使用方法

### 基本的な使い方

```python
from application.email_service import EmailService

# デフォルト設定で初期化（ファクトリが自動で適切な実装を選択）
email_service = EmailService()

# メール送信
success = email_service.send_email(
    to=["user@example.com"],
    subject="件名",
    body="本文",
    html_body="<p>HTML本文</p>"
)
```

### カスタム実装の注入

```python
from infrastructure.email_sender import ConsoleEmailSender

# テスト用にコンソール実装を直接注入
console_sender = ConsoleEmailSender()
email_service = EmailService(sender=console_sender)

# メール送信（コンソールに出力される）
email_service.send_email(...)
```

### パスワードリセットメール送信

```python
email_service = EmailService()

success = email_service.send_password_reset_email(
    email="user@example.com",
    reset_url="https://example.com/reset?token=abc123",
    validity_minutes=30
)
```

---

## 🧪 テスト

### テスト実行

```bash
# ドメイン層のテスト
python3 -m pytest tests/domain/email_sender/ --noconftest -v

# インフラ層のテスト
python3 -m pytest tests/infrastructure/email_sender/ --noconftest -v

# アプリケーション層のテスト
python3 -m pytest tests/application/email_service/ --noconftest -v
```

### テスト環境での設定

テスト環境では `MAIL_PROVIDER=console` を設定することで、実際にメールを送信せずにテストできます。

```python
# conftest.py または テスト内で
app.config['MAIL_PROVIDER'] = 'console'
```

---

## 🔌 既存コードとの統合

### PasswordResetService の移行

既存の `PasswordResetService` は新しい `EmailService` を使用するように更新されました。

**変更前:**
```python
from flask_mail import Message
from webapp.extensions import mail

msg = Message(subject=subject, recipients=[email], body=body)
mail.send(msg)
```

**変更後:**
```python
from application.email_service import EmailService

email_service = EmailService()
email_service.send_password_reset_email(
    email=email,
    reset_url=reset_url,
    validity_minutes=validity_minutes
)
```

---

## 📚 設計原則

本モジュールは以下の設計原則に従っています：

* **DIP (Dependency Inversion Principle)**: 依存性逆転の原則
  - 上位レイヤーは抽象（インターフェース）に依存
  - 具体実装は下位レイヤー（Infrastructure）に配置

* **ISP (Interface Segregation Principle)**: インターフェース分離原則
  - IEmailSender は最小限のメソッドのみを定義

* **DI (Dependency Injection)**: 依存性注入
  - EmailSenderFactory でインスタンス生成を一元管理
  - テスト時に mock 実装を注入可能

* **Strategy Pattern**: 戦略パターン
  - IEmailSender を抽象戦略として、複数の具体戦略（SMTP, Console）を切替可能

* **Value Object Pattern**: 値オブジェクトパターン
  - EmailMessage は不変オブジェクトとして実装

---

## 🚀 拡張方法

### 新しいメール送信実装の追加

例: APIベースのメール送信サービス（SendGrid, AWS SES等）を追加する場合

1. **Infrastructure層に実装を追加**

```python
# infrastructure/email_sender/api_sender.py
class ApiEmailSender(IEmailSender):
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    def send(self, message: EmailMessage) -> bool:
        # API経由でメール送信
        ...

    def validate_config(self) -> bool:
        return bool(self.api_key and self.base_url)
```

2. **Factoryに登録**

```python
# infrastructure/email_sender/factory.py
class EmailSenderFactory:
    PROVIDER_API = "api"

    @staticmethod
    def create(provider: Optional[str] = None) -> IEmailSender:
        # ...
        elif provider == EmailSenderFactory.PROVIDER_API:
            return EmailSenderFactory._create_api_sender()
        # ...

    @staticmethod
    def _create_api_sender() -> ApiEmailSender:
        from core.settings import settings
        api_key = settings.get("MAIL_API_KEY")
        base_url = settings.get("MAIL_API_BASE_URL")
        return ApiEmailSender(api_key=api_key, base_url=base_url)
```

3. **設定を追加**

```env
MAIL_PROVIDER=api
MAIL_API_KEY=your-api-key
MAIL_API_BASE_URL=https://api.example.com
```

---

## 📝 まとめ

| 項目     | 内容                        |
| ------ | ------------------------- |
| 特徴     | 柔軟なメール送信戦略切替              |
| 利点     | テスト容易、拡張性、環境別切替           |
| 実装パターン | DDD + Strategy + DI       |
| 対応プロバイダー | SMTP / Console（テスト用）      |
| テスト   | 19個のテストケース（すべて成功）        |

---

## 🔗 関連ファイル

* `domain/email_sender/` - ドメイン層
* `infrastructure/email_sender/` - インフラ層
* `application/email_service/` - アプリケーション層
* `webapp/services/password_reset_service.py` - 既存サービスとの統合例
* `tests/domain/email_sender/` - ドメイン層テスト
* `tests/infrastructure/email_sender/` - インフラ層テスト
* `tests/application/email_service/` - アプリケーション層テスト
* `core/settings.py` - 設定管理
