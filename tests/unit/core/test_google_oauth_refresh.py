"""Google OAuth トークン更新（shared/infrastructure/google_oauth.py）のテスト。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shared.infrastructure.google_oauth import RefreshTokenError, refresh_google_token


class TestRefreshGoogleToken:
    def test_decrypt_failure_raises_refresh_token_error(self) -> None:
        """復号失敗は汎用例外ではなく RefreshTokenError(500) になる。

        以前は暗号鍵不一致などの復号エラーが呼び出し元の
        RefreshTokenError ハンドリングを素通りし、API が原因不明の
        汎用 500（An unexpected error occurred.）を返していた。
        """
        account = SimpleNamespace(id=1, oauth_token_json="broken-ciphertext")

        with patch(
            "shared.infrastructure.google_oauth.decrypt",
            side_effect=ValueError("invalid base64 length: 5 bytes (32 required)"),
        ):
            with pytest.raises(RefreshTokenError) as exc_info:
                refresh_google_token(account)

        assert exc_info.value.status_code == 500
        assert "token_decrypt_failed" in str(exc_info.value)

    def test_missing_refresh_token_raises_400(self) -> None:
        account = SimpleNamespace(id=1, oauth_token_json="encrypted")

        with patch("shared.infrastructure.google_oauth.decrypt", return_value="{}"):
            with pytest.raises(RefreshTokenError) as exc_info:
                refresh_google_token(account)

        assert exc_info.value.status_code == 400
        assert str(exc_info.value) == "no_refresh_token"
