import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from typing import Tuple


_KEY_ENV = "OAUTH_TOKEN_KEY"
_KEY_FILE_ENV = "OAUTH_TOKEN_KEY_FILE"


def validate_oauth_key(raw: str) -> Tuple[bool, str]:
    """Validate OAuth encryption key string.

    Accepts either ``"base64:<b64>"`` where decoded length is 32 bytes or an
    arbitrary string of length at least 32 characters.  Returns ``(ok, why)``
    tuple for use by config validators.
    """

    if not raw:
        return False, "未設定"

    if raw.startswith("base64:"):
        b64 = raw.split(":", 1)[1]
        try:
            key = base64.urlsafe_b64decode(b64)
        except Exception as exc:  # pragma: no cover - defensive
            return False, f"base64デコード失敗: {exc}"
        if len(key) == 32:
            return True, "base64(32bytes)"
        return False, f"base64長さが不正: {len(key)} bytes (32必要)"

    if len(raw) >= 32:
        return True, "文字長>=32"

    return False, "32文字未満"

def _load_key() -> bytes:
    """Load 32-byte encryption key from env var or file."""
    key_b64 = os.environ.get(_KEY_ENV)
    if key_b64:
        key = base64.urlsafe_b64decode(key_b64)
    else:
        path = os.environ.get(_KEY_FILE_ENV)
        if not path:
            raise RuntimeError("Encryption key not configured")
        with open(path, "rb") as f:
            key = base64.urlsafe_b64decode(f.read().strip())
    if len(key) != 32:
        raise ValueError("AES-256-GCM key must be 32 bytes")
    return key


def encrypt(plaintext: str) -> str:
    """Encrypt text using AES-256-GCM.

    Returns base64 encoded nonce + ciphertext.
    """
    if plaintext is None:
        return ""
    key = _load_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("utf-8")


def decrypt(token: Optional[str]) -> str:
    """Decrypt base64 encoded nonce + ciphertext."""
    if not token:
        return ""
    key = _load_key()
    raw = base64.urlsafe_b64decode(token.encode("utf-8"))
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")

