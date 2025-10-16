"""JWT トークン管理サービス"""

from __future__ import annotations

import base64
import binascii
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Tuple

import jwt
from flask import current_app

from core.models.user import User
from webapp.extensions import db


class TokenService:
    """JWT アクセストークンとリフレッシュトークンの管理を行うサービス"""

    # トークンの有効期限設定
    ACCESS_TOKEN_EXPIRE_HOURS = 1
    REFRESH_TOKEN_EXPIRE_DAYS = 30

    @staticmethod
    def _normalize_scope(scope: Iterable[str] | None) -> tuple[list[str], str]:
        if scope is None:
            return [], ""

        normalized = {item.strip() for item in scope if item and item.strip()}
        if not normalized:
            return [], ""

        ordered = sorted(normalized)
        return ordered, " ".join(ordered)

    @staticmethod
    def _encode_scope_fragment(scope_str: str) -> str:
        if not scope_str:
            return ""
        encoded = base64.urlsafe_b64encode(scope_str.encode("utf-8")).decode("ascii")
        return encoded.rstrip("=")

    @staticmethod
    def _decode_scope_fragment(fragment: str) -> str:
        if not fragment:
            return ""
        padding = "=" * (-len(fragment) % 4)
        try:
            decoded = base64.urlsafe_b64decode(f"{fragment}{padding}")
        except (ValueError, binascii.Error):
            return ""
        try:
            return decoded.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    @classmethod
    def generate_access_token(
        cls,
        user: User,
        scope: Iterable[str] | None = None,
    ) -> str:
        """アクセストークンを生成する"""

        now = datetime.now(timezone.utc)
        _, scope_str = cls._normalize_scope(scope)

        payload = {
            "sub": str(user.id),  # ユーザーID（文字列）
            "email": user.email,  # デバッグ用
            "exp": now + timedelta(hours=cls.ACCESS_TOKEN_EXPIRE_HOURS),
            "iat": now,
            "jti": secrets.token_urlsafe(8),  # JWT ID
            "type": "access",
            "scope": scope_str,
        }

        return jwt.encode(
            payload,
            current_app.config["JWT_SECRET_KEY"],
            algorithm="HS256",
        )

    @classmethod
    def generate_refresh_token(
        cls,
        user: User,
        scope: Iterable[str] | None = None,
    ) -> str:
        """リフレッシュトークンを生成し、DBに保存する"""

        _, scope_str = cls._normalize_scope(scope)
        refresh_raw = secrets.token_urlsafe(32)
        scope_fragment = cls._encode_scope_fragment(scope_str)
        refresh_token = f"{user.id}:{scope_fragment}:{refresh_raw}"

        # DBに保存
        user.set_refresh_token(refresh_token)
        db.session.commit()

        return refresh_token

    @classmethod
    def generate_token_pair(
        cls,
        user: User,
        scope: Iterable[str] | None = None,
    ) -> Tuple[str, str]:
        """アクセストークンとリフレッシュトークンのペアを生成する"""

        access_token = cls.generate_access_token(user, scope)
        refresh_token = cls.generate_refresh_token(user, scope)

        return access_token, refresh_token

    @classmethod
    def verify_access_token(cls, token: str) -> Optional[tuple[User, set[str]]]:
        """アクセストークンを検証してユーザーと許可スコープを取得する"""

        try:
            payload = jwt.decode(
                token,
                current_app.config["JWT_SECRET_KEY"],
                algorithms=["HS256"],
            )

            user_id = int(payload["sub"])
            user = User.query.get(user_id)

            if not user or not user.is_active:
                return None

            scope_claim = payload.get("scope", "")
            if isinstance(scope_claim, str):
                scope_items = {item for item in scope_claim.split() if item}
            else:
                scope_items = set()

            return user, scope_items

        except jwt.ExpiredSignatureError:
            current_app.logger.debug("JWT token expired")
            return None
        except jwt.InvalidTokenError as exc:
            current_app.logger.debug(f"JWT token invalid: {exc}")
            return None
        except (ValueError, TypeError):
            current_app.logger.debug("JWT token format error")
            return None

    @classmethod
    def verify_refresh_token(cls, refresh_token: str) -> Optional[tuple[User, str]]:
        """リフレッシュトークンを検証してユーザーとスコープを取得する"""

        if not refresh_token:
            return None

        try:
            parts = refresh_token.split(":", 2)
            if len(parts) < 2:
                raise ValueError("invalid_refresh_token_format")
            user_id = int(parts[0])
        except (ValueError, TypeError):
            current_app.logger.debug("Invalid refresh token format")
            return None

        user = User.query.get(user_id)
        if not user:
            current_app.logger.debug("Refresh token verification failed: user not found")
            return None

        if not user.is_active:
            current_app.logger.debug("Refresh token verification failed: user inactive")
            return None

        if not user.check_refresh_token(refresh_token):
            current_app.logger.debug("Refresh token verification failed")
            return None

        scope_fragment = parts[1] if len(parts) > 1 else ""
        scope_str = cls._decode_scope_fragment(scope_fragment)

        return user, scope_str

    @classmethod
    def refresh_tokens(cls, refresh_token: str) -> Optional[Tuple[str, str, str]]:
        """リフレッシュトークンから新しいトークンペアを生成する"""

        verification = cls.verify_refresh_token(refresh_token)
        if not verification:
            return None

        user, scope_str = verification
        scope_items = scope_str.split()

        # 新しいトークンペアを生成（リフレッシュトークンローテーション）
        access_token, new_refresh_token = cls.generate_token_pair(user, scope_items)
        return access_token, new_refresh_token, scope_str

    @classmethod
    def revoke_refresh_token(cls, user: User) -> None:
        """ユーザーのリフレッシュトークンを無効化する"""

        user.set_refresh_token(None)
        db.session.commit()

