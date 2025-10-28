import base64
import os

import pytest

from core import crypto


def _gen_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def test_validate_encryption_key_valid():
    key = _gen_key()
    ok, msg = crypto.validate_encryption_key(key)
    assert ok is True
    assert msg == "base64(32bytes)"


def test_validate_encryption_key_invalid_length():
    bad_key = base64.urlsafe_b64encode(b'123').decode()
    ok, msg = crypto.validate_encryption_key(bad_key)
    assert ok is False
    assert "invalid base64 length" in msg


def test_encrypt_decrypt_round_trip(monkeypatch):
    key = _gen_key()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    token = crypto.encrypt("secret")
    assert crypto.decrypt(token) == "secret"


def test_encrypt_decrypt_legacy_format(monkeypatch):
    key = _gen_key()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    token = crypto.encrypt("data", envelope=False)
    assert crypto.decrypt(token) == "data"
