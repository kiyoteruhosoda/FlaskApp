"""Application service for WebAuthn passkey flows."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from core.settings import settings
from shared.infrastructure.passkey_repository import SqlAlchemyPasskeyRepository


class PasskeyServiceError(RuntimeError):
    """Base exception raised when passkey processing fails."""


class PasskeyRegistrationError(PasskeyServiceError):
    """Raised when registration fails to verify."""


class PasskeyAuthenticationError(PasskeyServiceError):
    """Raised when authentication fails to verify."""


@dataclass(slots=True)
class PasskeyService:
    """Coordinate WebAuthn operations and persistence."""

    repository: SqlAlchemyPasskeyRepository

    def generate_registration_options(
        self,
        user,
        *,
        rp_id: str | None = None,
        rp_name: str | None = None,
    ) -> tuple[dict, str]:
        """Return creation options and encoded challenge for *user*."""

        exclude_credentials: list[PublicKeyCredentialDescriptor] = []
        for credential in self.repository.list_for_user(user.id):
            try:
                descriptor = PublicKeyCredentialDescriptor(
                    id=base64url_to_bytes(credential.credential_id),
                    type="public-key",
                )
            except Exception:  # pragma: no cover - defensive
                continue
            exclude_credentials.append(descriptor)

        options = generate_registration_options(
            rp_id=rp_id or settings.webauthn_rp_id,
            rp_name=rp_name or settings.webauthn_rp_name,
            user_id=str(user.id).encode("utf-8"),
            user_name=user.email,
            user_display_name=getattr(user, "display_name", user.email),
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            exclude_credentials=exclude_credentials,
        )
        challenge = bytes_to_base64url(options.challenge)
        options_json = json.loads(options_to_json(options))
        return options_json, challenge

    def register_passkey(
        self,
        *,
        user,
        payload: bytes,
        expected_challenge: str,
        transports: Iterable[str] | None = None,
        name: str | None = None,
        expected_rp_id: str | None = None,
        expected_origin: str | None = None,
    ):
        """Verify a registration response and persist the credential."""

        try:
            credential = RegistrationCredential.parse_raw(payload)
        except Exception as exc:  # pragma: no cover - validation
            raise PasskeyRegistrationError("invalid_payload") from exc

        try:
            verification = verify_registration_response(
                credential=credential,
                expected_challenge=expected_challenge,
                expected_rp_id=expected_rp_id or settings.webauthn_rp_id,
                expected_origin=expected_origin or settings.webauthn_origin,
                require_user_verification=True,
            )
        except Exception as exc:
            raise PasskeyRegistrationError("verification_failed") from exc

        backup_eligible = bool(
            getattr(verification, "credential_device_type", "unknown") == "multi-device"
        )
        backup_state = bool(getattr(verification, "credential_backed_up", False))

        record = self.repository.add(
            user=user,
            credential_id=bytes_to_base64url(verification.credential_id),
            public_key=bytes_to_base64url(verification.credential_public_key),
            sign_count=verification.sign_count,
            transports=transports,
            name=name,
            attestation_format=getattr(verification, "fmt", None),
            aaguid=getattr(verification, "aaguid", None),
            backup_eligible=backup_eligible,
            backup_state=backup_state,
        )
        return record

    def generate_authentication_options(
        self,
        *,
        rp_id: str | None = None,
    ) -> tuple[dict, str]:
        """Return request options and encoded challenge for authentication."""

        options = generate_authentication_options(
            rp_id=rp_id or settings.webauthn_rp_id,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        challenge = bytes_to_base64url(options.challenge)
        options_json = json.loads(options_to_json(options))
        return options_json, challenge

    def authenticate(
        self,
        *,
        payload: bytes,
        expected_challenge: str,
        expected_rp_id: str | None = None,
        expected_origin: str | None = None,
    ):
        """Verify an authentication response and return the bound user model."""

        try:
            credential = AuthenticationCredential.parse_raw(payload)
        except Exception as exc:  # pragma: no cover - validation
            raise PasskeyAuthenticationError("invalid_payload") from exc

        stored = self.repository.find_by_credential_id(credential.id)
        if stored is None:
            raise PasskeyAuthenticationError("credential_not_found")

        try:
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=expected_challenge,
                expected_rp_id=expected_rp_id or settings.webauthn_rp_id,
                expected_origin=expected_origin or settings.webauthn_origin,
                credential_public_key=base64url_to_bytes(stored.public_key),
                credential_current_sign_count=stored.sign_count,
                require_user_verification=True,
            )
        except Exception as exc:
            raise PasskeyAuthenticationError("verification_failed") from exc

        self.repository.touch_usage(stored, verification.new_sign_count)
        return stored.user
