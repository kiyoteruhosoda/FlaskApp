"""JWT トークン管理サービス"""

from __future__ import annotations

import base64
import binascii
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Tuple, Any

from sqlalchemy import inspect

import jwt
from flask import current_app

from core.models.user import User
from core.models.service_account import ServiceAccount
from core.settings import settings
from shared.application.authenticated_principal import AuthenticatedPrincipal
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
            subject=f"i+{user.id}",
            scope_str=scope_str,
            extra_claims={
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
            subject=f"s+{account.service_account_id}",
            scope_str=scope_str,
            extra_claims={
                "subject_type": "system",
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
    ) -> Optional[AuthenticatedPrincipal]:
        """アクセストークンを検証して主体情報を取得する"""

        return cls.create_principal_from_token(token)

    @classmethod
    def _decode_access_token_payload(cls, token: str) -> Optional[dict[str, Any]]:
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

        return payload

    @classmethod
    def _build_principal_from_payload(
        cls, payload: dict[str, Any]
    ) -> Optional[AuthenticatedPrincipal]:
        try:
            subject_type, subject_id, identifier = cls._extract_subject(payload)
        except ValueError:
            current_app.logger.debug("JWT token subject claim invalid")
            return None

        scope_items = cls._extract_scope_items(payload)

        if subject_type == "system":
            account = ServiceAccount.query.get(subject_id)
            if not account or not account.is_active():
                current_app.logger.debug("JWT token service account inactive or missing")
                return None

            return AuthenticatedPrincipal(
                subject_type="system",
                subject_id=account.service_account_id,
                identifier=identifier,
                scope=frozenset(scope_items),
                display_name=account.name,
            )

        user = User.query.get(subject_id)
        if not user or not user.is_active:
            return None

        display_name = getattr(user, "username", None) or getattr(user, "email", None)
        role_objects = tuple(user.roles or [])

        return AuthenticatedPrincipal(
            subject_type="individual",
            subject_id=user.id,
            identifier=identifier,
            scope=frozenset(scope_items),
            display_name=display_name,
            roles=role_objects,
            email=getattr(user, "email", None),
            _totp_secret=getattr(user, "totp_secret", None),
            _permissions=frozenset(scope_items),
        )

    @classmethod
    def create_principal_from_token(
        cls, token: str
    ) -> Optional[AuthenticatedPrincipal]:
        """
        Validates the access token and reconstructs an AuthenticatedPrincipal from it.

        Returns:
            AuthenticatedPrincipal: If the token is valid and not expired.
            None: If the token is invalid or expired.
        """
        payload = cls._decode_access_token_payload(token)
        if payload is None:
            return None

        return cls._build_principal_from_payload(payload)

    @classmethod
    def create_principal_for_user(
        cls,
        user: User,
        scope: Iterable[str] | None = None,
        active_role_id: int | None = None,
    ) -> AuthenticatedPrincipal:
        """Build an AuthenticatedPrincipal for an ORM user model."""

        if user is None:
            raise ValueError("user must not be None")

        if not getattr(user, "is_active", True):
            raise ValueError("inactive_user")

        user_id = getattr(user, "id", None)
        if user_id is None:
            raise ValueError("user_id_missing")

        state = inspect(user)
        if state.session is None:
            user = db.session.merge(user, load=True)
            state = inspect(user)

        if scope is None:
            scope_items: set[str] = set()
            all_roles = list(getattr(user, "roles", []) or [])
            
            # Security: Only grant permissions when active_role_id is explicitly specified
            # If active_role_id is None, grant NO permissions (secure by default)
            if active_role_id is not None:
                roles_to_use = [role for role in all_roles if role.id == active_role_id]
                
                for role in roles_to_use:
                    for permission in getattr(role, "permissions", []) or []:
                        code = getattr(permission, "code", None)
                        if isinstance(code, str) and code.strip():
                            scope_items.add(code.strip())
        else:
            normalized_scope, _ = cls._normalize_scope(scope)
            scope_items = set(normalized_scope)

        display_name = getattr(user, "username", None) or getattr(user, "email", None)
        role_objects = tuple(getattr(user, "roles", []) or [])

        return AuthenticatedPrincipal(
            subject_type="individual",
            subject_id=user_id,
            identifier=f"i+{user_id}",
            scope=frozenset(scope_items),
            display_name=display_name,
            roles=role_objects,
            email=getattr(user, "email", None),
            _totp_secret=getattr(user, "totp_secret", None),
            _permissions=frozenset(scope_items),
        )

    @staticmethod
    def _extract_subject(payload: dict[str, Any]) -> tuple[str, int, str]:
        subject_type = payload.get("subject_type") or "individual"
        if subject_type not in {"individual", "system"}:
            raise ValueError("unsupported_subject_type")

        subject = payload.get("sub")
        if isinstance(subject, int):
            subject_id = subject
        elif isinstance(subject, str) and subject:
            prefix = "i+" if subject_type == "individual" else "s+"
            if subject.startswith(prefix):
                subject = subject[len(prefix) :]
            try:
                subject_id = int(subject)
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                raise ValueError("invalid_subject") from exc
        else:
            raise ValueError("invalid_subject")

        identifier = f"{'i' if subject_type == 'individual' else 's'}+{subject_id}"
        return subject_type, subject_id, identifier

    @staticmethod
    def _extract_scope_items(payload: dict[str, Any]) -> set[str]:
        scope_claim = payload.get("scope", "")
        if isinstance(scope_claim, str):
            return {item for item in scope_claim.split() if item}
        if isinstance(scope_claim, (list, tuple, set, frozenset)):
            return {str(item).strip() for item in scope_claim if str(item).strip()}
        return set()

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
    def revoke_refresh_token(cls, subject: User | AuthenticatedPrincipal) -> None:
        """ユーザーのリフレッシュトークンを無効化する"""

        if isinstance(subject, AuthenticatedPrincipal):
            if not subject.is_individual:
                current_app.logger.debug(
                    "Refresh token revoke skipped: subject is not an individual",
                )
                return

            target_user = User.query.get(subject.id)
            if target_user is None:
                current_app.logger.debug(
                    "Refresh token revoke skipped: user not found (id=%s)",
                    subject.id,
                )
                return
        elif isinstance(subject, User):
            target_user = subject
        else:  # pragma: no cover - defensive branch
            current_app.logger.debug(
                "Refresh token revoke skipped: unsupported type %s",
                type(subject).__name__,
            )
            return

        target_user.set_refresh_token(None)
        db.session.commit()

