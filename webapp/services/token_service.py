"""JWT トークン管理サービス"""

from __future__ import annotations

import base64
import binascii
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Tuple

import jwt
from flask import current_app

from core.models.user import User
from core.models.service_account import ServiceAccount
from core.settings import settings
from webapp.extensions import db
from webapp.services.access_token_signing import (
    AccessTokenSigningError,
    AccessTokenVerificationError,
    resolve_signing_material,
    resolve_verification_key,
)


class TokenService:
    """JWT アクセストークンとリフレッシュトークンの管理を行うサービス"""

    # トークンの有効期限設定
    ACCESS_TOKEN_EXPIRE_HOURS = 1
    ACCESS_TOKEN_EXPIRE_SECONDS = int(timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS).total_seconds())
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
    def _build_access_token_payload(
        cls,
        *,
        subject: str,
        scope_str: str,
        extra_claims: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": subject,
            "exp": now + timedelta(hours=cls.ACCESS_TOKEN_EXPIRE_HOURS),
            "iat": now,
            "jti": secrets.token_urlsafe(8),
            "type": "access",
            "scope": scope_str,
            "iss": settings.access_token_issuer,
            "aud": settings.access_token_audience,
        }
        if extra_claims:
            payload.update(extra_claims)
        return payload

    @classmethod
    def _encode_access_token(cls, payload: dict) -> str:
        try:
            material = resolve_signing_material()
        except AccessTokenSigningError as exc:
            current_app.logger.error(
                "Failed to resolve signing material for access token: %s",
                exc,
            )
            raise

        headers = material.headers if material.headers else None
        return jwt.encode(
            payload,
            material.key,
            algorithm=material.algorithm,
            headers=headers,
        )

    @classmethod
    def generate_access_token(
        cls,
        user: User,
        scope: Iterable[str] | None = None,
    ) -> str:
        """アクセストークンを生成する"""

        _, scope_str = cls._normalize_scope(scope)
        payload = cls._build_access_token_payload(
            subject=str(user.id),
            scope_str=scope_str,
            extra_claims={
                "email": user.email,
                "subject_type": "individual",
            },
        )
        return cls._encode_access_token(payload)

    @classmethod
    def generate_service_account_access_token(
        cls,
        account: ServiceAccount,
        scope: Iterable[str] | None = None,
    ) -> str:
        """サービスアカウント向けのアクセストークンを生成する"""

        _, scope_str = cls._normalize_scope(scope)
        payload = cls._build_access_token_payload(
            subject=str(account.service_account_id),
            scope_str=scope_str,
            extra_claims={
                "subject_type": "system",
                "service_account": account.name,
                "service_account_id": account.service_account_id,
            },
        )
        return cls._encode_access_token(payload)

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
    def verify_access_token(
        cls, token: str
    ) -> Optional[tuple[User | ServiceAccount, set[str]]]:
        """アクセストークンを検証して主体と許可スコープを取得する"""

        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError:
            current_app.logger.debug("JWT token header invalid")
            return None

        algorithm = header.get("alg") if isinstance(header, dict) else None
        kid = header.get("kid") if isinstance(header, dict) else None
        if not isinstance(algorithm, str) or not algorithm:
            current_app.logger.debug("JWT token missing algorithm header")
            return None

        try:
            key = resolve_verification_key(algorithm, kid if isinstance(kid, str) else None)
        except (AccessTokenVerificationError, AccessTokenSigningError) as exc:
            current_app.logger.debug("JWT token verification key resolution failed: %s", exc)
            return None

        expected_audience = settings.access_token_audience
        expected_issuer = settings.access_token_issuer
        required_claims = ["aud"]
        if expected_issuer:
            required_claims.append("iss")

        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=expected_audience,
                issuer=expected_issuer if expected_issuer else None,
                options={"require": required_claims},
            )
        except jwt.ExpiredSignatureError:
            current_app.logger.debug("JWT token expired")
            return None
        except jwt.InvalidAudienceError:
            current_app.logger.debug("JWT token audience mismatch")
            return None
        except jwt.InvalidIssuerError:
            current_app.logger.debug("JWT token issuer mismatch")
            return None
        except jwt.MissingRequiredClaimError as exc:
            current_app.logger.debug("JWT token missing required claim: %s", exc.claim)
            return None
        except jwt.InvalidTokenError as exc:
            current_app.logger.debug(f"JWT token invalid: {exc}")
            return None
        except (ValueError, TypeError):
            current_app.logger.debug("JWT token format error")
            return None

        subject_type = payload.get("subject_type") or "individual"

        try:
            subject_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            current_app.logger.debug("JWT token missing subject claim")
            return None

        principal: User | ServiceAccount | None = None

        if subject_type == "system":
            account = ServiceAccount.query.get(subject_id)
            if not account or not account.is_active():
                current_app.logger.debug(
                    "JWT token verification failed: service account not found or inactive"
                )
                return None
            principal = account
        else:
            user = User.query.get(subject_id)
            if not user or not user.is_active:
                return None
            principal = user

        scope_claim = payload.get("scope", "")
        if isinstance(scope_claim, str):
            scope_items = {item for item in scope_claim.split() if item}
        else:
            scope_items = set()

        return principal, scope_items

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

