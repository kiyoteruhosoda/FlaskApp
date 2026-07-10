"""verify_totp ユニットテスト。

presentation/fastapi/auth/totp.py の verify_totp 関数が
正しい TOTP コードを受理し、不正なコードを拒否することを検証する。
"""
from __future__ import annotations

import pyotp
import pytest

from presentation.fastapi.auth.totp import verify_totp


class TestVerifyTotp:
    """verify_totp 関数のテスト。"""

    def test_valid_current_token_returns_true(self) -> None:
        secret = pyotp.random_base32()
        token = pyotp.TOTP(secret).now()
        assert verify_totp(secret, token) is True

    def test_invalid_token_returns_false(self) -> None:
        secret = pyotp.random_base32()
        assert verify_totp(secret, "000000") is False

    def test_wrong_secret_returns_false(self) -> None:
        secret_a = pyotp.random_base32()
        secret_b = pyotp.random_base32()
        token_for_a = pyotp.TOTP(secret_a).now()
        assert verify_totp(secret_b, token_for_a) is False

    def test_empty_token_returns_false(self) -> None:
        secret = pyotp.random_base32()
        assert verify_totp(secret, "") is False

    def test_non_numeric_token_returns_false(self) -> None:
        secret = pyotp.random_base32()
        assert verify_totp(secret, "abcdef") is False

    def test_valid_window_accepts_adjacent_step(self) -> None:
        """valid_window=1 のとき前後ステップのコードも受理することを確認する。"""
        import time

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        # 1 ステップ前のコードを生成
        at_time = time.time() - 30
        previous_token = totp.at(at_time)
        assert verify_totp(secret, previous_token, valid_window=1) is True

    def test_zero_window_rejects_previous_step(self) -> None:
        """valid_window=0 のとき厳密に現在ステップのみ受理することを確認する。"""
        import time

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        at_time = time.time() - 60
        old_token = totp.at(at_time)
        # 2 ステップ前のコードは valid_window=1 でも拒否される
        assert verify_totp(secret, old_token, valid_window=0) is False
