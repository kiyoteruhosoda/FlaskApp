import base64
import json
import pytest
from core.crypto import encrypt, decrypt
from fpv.google import parse_oauth_payload


@pytest.fixture(autouse=True)
def set_key(monkeypatch):
    key = base64.b64encode(b'0' * 32).decode('utf-8')
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


def test_encrypt_decrypt_with_fpv_key_file(monkeypatch, tmp_path):
    key = base64.b64encode(b'0' * 32).decode('utf-8')
    key_file = tmp_path / 'keyfile'
    key_file.write_text(key)
    monkeypatch.delenv('OAUTH_TOKEN_KEY', raising=False)
    monkeypatch.setenv('FPV_OAUTH_TOKEN_KEY_FILE', str(key_file))
    token = encrypt('hello')
    assert decrypt(token) == 'hello'


def test_decrypt_legacy_format():
    plaintext = 'legacy data'
    token = encrypt(plaintext, envelope=False)
    assert decrypt(token) == plaintext


def test_cli_parse_encrypted_payload():
    payload = {'refresh_token': 'r0'}
    token = encrypt(json.dumps(payload))
    key = base64.b64encode(b'0' * 32).decode('utf-8')
    parsed = parse_oauth_payload(token, f'base64:{key}')
    assert parsed['refresh_token'] == 'r0'
