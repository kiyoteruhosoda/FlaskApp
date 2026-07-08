"""後方互換シム的なユーティリティ集約モジュール。

OAuth トークン更新（``refresh_google_token`` / ``RefreshTokenError``）と外向き
HTTP ロギング（``log_requests_and_send`` 等）は共有層へ移動した。既存の
``from ..auth.utils import ...`` を壊さないよう同名を再公開する。新規コードは
``shared.infrastructure.google_oauth`` / ``shared.infrastructure.http_logging``
を直接 import すること。
"""

# 外向き HTTP ロギングユーティリティ（shared/infrastructure へ移動済み）
from shared.infrastructure.http_logging import (  # noqa: F401
    MASKED_VALUE,
    SENSITIVE_BODY_KEYS,
    SENSITIVE_HEADER_KEYS,
    _mask_sensitive_values,
    log_requests_and_send,
)

# Google OAuth トークン更新（shared/infrastructure へ移動済み）
from shared.infrastructure.google_oauth import (  # noqa: F401
    RefreshTokenError,
    refresh_google_token,
)
