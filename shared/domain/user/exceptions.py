"""ユーザードメインに関する例外定義。"""


class EmailAlreadyRegisteredError(Exception):
    """既に有効なユーザーが存在する場合に発生する例外。"""

    def __init__(self, email: str):
        super().__init__("Email already exists")
        self.email = email
