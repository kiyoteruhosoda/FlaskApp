import base64
import json
import os
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_KEY_ENV = "OAUTH_TOKEN_KEY"
_KEY_FILE_ENV = "OAUTH_TOKEN_KEY_FILE"
_FPV_KEY_FILE_ENV = "FPV_OAUTH_TOKEN_KEY_FILE"


def _decode_key(raw: str) -> bytes:
    """Decode a key string into 32 bytes.

    Supports values prefixed with ``"base64:"`` as well as plain base64
    strings.  Raises :class:`ValueError` if the key is invalid or the decoded
    length is not 32 bytes.
    """

    if raw.startswith("base64:"):
        raw = raw.split(":", 1)[1]
    try:
        key = base64.urlsafe_b64decode(raw)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"base64 decode failed: {exc}") from exc
    if len(key) != 32:
        raise ValueError(f"invalid base64 length: {len(key)} bytes (32 required)")
    return key


def validate_oauth_key(raw: str) -> Tuple[bool, str]:
    """Validate OAuth encryption key string using ``_load_key`` logic."""

    if not raw:
        return False, "not set"
    try:
        _load_key(raw)  # will raise on error
        return True, "base64(32bytes)"
    except Exception as exc:  # pragma: no cover - defensive
        return False, str(exc)

def _load_key(raw: Optional[str] = None) -> bytes:
    """Load 32-byte encryption key from a string, env var, or file."""

    if raw is not None:
        return _decode_key(raw)

    key_str = os.environ.get(_KEY_ENV)
    if key_str:
        return _decode_key(key_str)

    path = os.environ.get(_KEY_FILE_ENV) or os.environ.get(_FPV_KEY_FILE_ENV)
    if path:
        with open(path, "r") as f:
            return _decode_key(f.read().strip())

    raise RuntimeError("Encryption key not configured")


def encrypt(plaintext: str, *, envelope: bool = True) -> str:
    """Encrypt text using AES-256-GCM.

    When ``envelope`` is ``True`` (default), returns a JSON envelope that
    matches the format expected by the CLI.  If ``False`` it returns the
    legacy ``nonce+ciphertext`` base64 string for backwards compatibility.
    """
    if plaintext is None:
        return ""
    key = _load_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    if envelope:
        env = {
            "alg": "AES-256-GCM",
            "nonce": base64.b64encode(nonce).decode("utf-8"),
            "ct": base64.b64encode(ct).decode("utf-8"),
        }
        return json.dumps(env)
    return base64.urlsafe_b64encode(nonce + ct).decode("utf-8")


def decrypt(token: Optional[str]) -> str:
    """Decrypt a token produced by :func:`encrypt`.

    Supports both the JSON envelope format and the legacy ``nonce+ciphertext``
    base64 format.
    """
    if not token:
        return ""
    key = _load_key()
    try:
        env = json.loads(token)
        if isinstance(env, dict) and env.get("alg") == "AES-256-GCM":
            nonce = base64.b64decode(env["nonce"])
            ct = base64.b64decode(env["ct"])
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    raw = base64.urlsafe_b64decode(token.encode("utf-8"))
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")

