"""JWK向けのエンコード関連ユーティリティ"""
from __future__ import annotations

import base64


def to_base64url(data: bytes) -> str:
    """Base64URL形式にエンコード"""

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
