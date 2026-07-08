"""Password reset service (FastAPI version - no Flask deps)."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from shared.kernel.i18n.translation import gettext as _
from shared.kernel.settings.settings import settings

from shared.kernel.database.db import db
from shared.infrastructure.models.password_reset_token import PasswordResetToken
from shared.infrastructure.models.user import User
from bounded_contexts.email_sender import EmailService

logger = logging.getLogger(__name__)


class PasswordResetService:
    """パスワードリセット機能を提供するサービス。"""

    TOKEN_LENGTH = 32  # 256 bits
    TOKEN_VALIDITY_MINUTES = 30

    @classmethod
    def generate_reset_token(cls) -> str:
        return secrets.token_urlsafe(cls.TOKEN_LENGTH)

    @classmethod
    def create_reset_request(cls, email: str) -> tuple[bool, Optional[str]]:
        if not settings.mail_enabled:
            logger.warning(
                "Password reset requested but mail is disabled",
                extra={"event": "password_reset.mail_disabled", "email": email},
            )
            return (
                False,
                _(
                    "Failed to send email. A valid mail sender is not configured. Please contact the administrator."
                ),
            )

        user = db.session.query(User).filter_by(email=email).first()

        if user and user.is_active:
            raw_token = cls.generate_reset_token()

            existing_tokens = db.session.query(PasswordResetToken).filter_by(
                email=email,
                used=False,
            ).all()
            for token in existing_tokens:
                token.mark_as_used()

            reset_token = PasswordResetToken.create_token(
                email=email,
                raw_token=raw_token,
                validity_minutes=cls.TOKEN_VALIDITY_MINUTES,
            )
            db.session.add(reset_token)
            db.session.commit()

            try:
                cls._send_reset_email(email, raw_token)
            except Exception as exc:
                logger.error(
                    f"Failed to send password reset email: {exc}",
                    extra={"event": "password_reset.email_failed", "email": email},
                )

        return (True, None)

    @classmethod
    def _send_reset_email(cls, email: str, token: str) -> None:
        if not settings.mail_enabled:
            raise RuntimeError(
                _(
                    "Failed to send email. A valid mail sender is not configured. Please contact the administrator."
                )
            )

        reset_url = settings.app_base_url.rstrip("/") + "/auth/reset-password?token=" + token

        email_service = EmailService()
        success = email_service.send_password_reset_email(
            email=email,
            reset_url=reset_url,
            validity_minutes=cls.TOKEN_VALIDITY_MINUTES,
        )

        if success:
            logger.info(
                "Password reset email sent",
                extra={"event": "password_reset.email_sent", "email": email},
            )
        else:
            raise RuntimeError(
                _(
                    "Failed to send email. A valid mail sender is not configured. Please contact the administrator."
                )
            )

    @classmethod
    def verify_token(cls, token: str) -> Optional[str]:
        now = datetime.now(timezone.utc)
        active_tokens = db.session.query(PasswordResetToken).filter(
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now,
        ).all()

        for reset_token in active_tokens:
            if reset_token.check_token(token):
                if reset_token.is_valid():
                    return reset_token.email

        return None

    @classmethod
    def reset_password(cls, token: str, new_password: str) -> bool:
        email = cls.verify_token(token)
        if not email:
            return False

        user = db.session.query(User).filter_by(email=email).first()
        if not user or not user.is_active:
            return False

        now = datetime.now(timezone.utc)
        matching_token = db.session.query(PasswordResetToken).filter(
            PasswordResetToken.email == email,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now,
        ).first()

        if not matching_token or not matching_token.check_token(token):
            return False

        token_marked = PasswordResetToken.mark_as_used_atomic(matching_token.id, email)

        if not token_marked:
            logger.warning(
                "Token already used (concurrent access detected)",
                extra={
                    "event": "password_reset.token_already_used",
                    "email": email,
                    "token_id": matching_token.id,
                },
            )
            return False

        user.set_password(new_password)
        db.session.commit()

        logger.info(
            "Password reset successful",
            extra={"event": "password_reset.success", "email": email},
        )

        return True
