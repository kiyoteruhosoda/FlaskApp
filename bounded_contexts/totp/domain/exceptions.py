"""TOTP 機能のドメイン例外"""


class TOTPError(Exception):
    """TOTP 関連の基底例外"""


class TOTPNotFoundError(TOTPError):
    """指定された TOTP が存在しない"""


class TOTPValidationError(TOTPError):
    """入力検証エラー"""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


class TOTPConflictError(TOTPError):
    """account + issuer が重複している"""

    def __init__(self, account: str, issuer: str):
        super().__init__(f"Duplicate entry for {account} ({issuer})")
        self.account = account
        self.issuer = issuer
