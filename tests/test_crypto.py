import base64
import pytest
from core.crypto import encrypt, decrypt


@pytest.fixture(autouse=True)
def set_key(monkeypatch):
    key = base64.urlsafe_b64encode(b'0' * 32).decode('utf-8')
    monkeypatch.setenv('OAUTH_TOKEN_KEY', key)


def test_encrypt_decrypt_roundtrip():
    plaintext = 'secret data'
    token = encrypt(plaintext)
    assert token != ''
    assert decrypt(token) == plaintext


def test_encrypt_none_returns_empty():
    assert encrypt(None) == ''


def test_decrypt_empty_returns_empty():
    assert decrypt('') == ''
    assert decrypt(None) == ''
