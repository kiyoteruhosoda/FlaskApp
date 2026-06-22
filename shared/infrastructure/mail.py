"""共有の Flask-Mailman インスタンス。

メール送信拡張は複数の bounded context（email / email_sender）と presentation 層の
双方から参照されるため、特定の presentation 層ではなく共有 infrastructure 層に置く。
``db`` を ``shared.kernel.database.db`` に集約したのと同じ方針。
"""

from flask_mailman import Mail

# アプリ全体で共有する単一の Mail インスタンス（``mail.init_app(app)`` で初期化）
mail = Mail()

__all__ = ["mail"]
