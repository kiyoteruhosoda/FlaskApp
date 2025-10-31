"""Application service for WebAuthn passkey flows."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Type

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticationCredential,
    AuthenticatorAssertionResponse,
    AuthenticatorAttachment,
    AuthenticatorAttestationResponse,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from core.settings import settings
from shared.infrastructure.passkey_repository import (
    DuplicatePasskeyCredentialError,
    SqlAlchemyPasskeyRepository,
)


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
                    type=PublicKeyCredentialType.PUBLIC_KEY,
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

        credential_dict = self._coerce_credential_payload(payload, PasskeyRegistrationError)
        credential = self._build_registration_credential(
            credential_dict, PasskeyRegistrationError
        )
        expected_challenge_bytes = self._decode_expected_challenge(
            expected_challenge, PasskeyRegistrationError
        )

        try:
            verification = verify_registration_response(
                credential=credential,
                expected_challenge=expected_challenge_bytes,
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

        try:
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
        except DuplicatePasskeyCredentialError as exc:
            raise PasskeyRegistrationError("already_registered") from exc
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

        credential_dict = self._coerce_credential_payload(
            payload, PasskeyAuthenticationError
        )
        credential = self._build_authentication_credential(
            credential_dict, PasskeyAuthenticationError
        )

        stored = self.repository.find_by_credential_id(credential.id)
        if stored is None:
            raise PasskeyAuthenticationError("credential_not_found")

        expected_challenge_bytes = self._decode_expected_challenge(
            expected_challenge, PasskeyAuthenticationError
        )

        try:
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=expected_challenge_bytes,
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

    @staticmethod
    def _coerce_credential_payload(
        payload, error_cls: Type[PasskeyServiceError]
    ) -> dict:
        if isinstance(payload, dict):
            return payload

        if isinstance(payload, (bytes, bytearray)):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise error_cls("invalid_payload") from exc

        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except Exception as exc:
                raise error_cls("invalid_payload") from exc
            if isinstance(data, dict):
                return data

        raise error_cls("invalid_payload")

    @staticmethod
    def _build_registration_credential(
        payload: dict[str, Any], error_cls: Type[PasskeyServiceError]
    ) -> RegistrationCredential:
        try:
            response = payload["response"]
        except Exception as exc:
            raise error_cls("invalid_payload") from exc

        if not isinstance(response, dict):
            raise error_cls("invalid_payload")

        attachment = PasskeyService._parse_authenticator_attachment(
            payload.get("authenticatorAttachment"), error_cls
        )
        transports = PasskeyService._parse_transports(
            response.get("transports"), error_cls
        )

        try:
            return RegistrationCredential(
                id=PasskeyService._require_string(payload, "id", error_cls),
                raw_id=base64url_to_bytes(
                    PasskeyService._require_string(payload, "rawId", error_cls)
                ),
                response=AuthenticatorAttestationResponse(
                    client_data_json=base64url_to_bytes(
                        PasskeyService._require_string(
                            response, "clientDataJSON", error_cls
                        )
                    ),
                    attestation_object=base64url_to_bytes(
                        PasskeyService._require_string(
                            response, "attestationObject", error_cls
                        )
                    ),
                    transports=transports,
                ),
                authenticator_attachment=attachment,
            )
        except PasskeyServiceError:
            raise
        except Exception as exc:
            raise error_cls("invalid_payload") from exc

    @staticmethod
    def _build_authentication_credential(
        payload: dict[str, Any], error_cls: Type[PasskeyServiceError]
    ) -> AuthenticationCredential:
        try:
            response = payload["response"]
        except Exception as exc:
            raise error_cls("invalid_payload") from exc

        if not isinstance(response, dict):
            raise error_cls("invalid_payload")

        attachment = PasskeyService._parse_authenticator_attachment(
            payload.get("authenticatorAttachment"), error_cls
        )

        user_handle: bytes | None = None
        if response.get("userHandle") is not None:
            user_handle_value = response.get("userHandle")
            if not isinstance(user_handle_value, str):
                raise error_cls("invalid_payload")
            try:
                user_handle = base64url_to_bytes(user_handle_value)
            except Exception as exc:
                raise error_cls("invalid_payload") from exc

        try:
            return AuthenticationCredential(
                id=PasskeyService._require_string(payload, "id", error_cls),
                raw_id=base64url_to_bytes(
                    PasskeyService._require_string(payload, "rawId", error_cls)
                ),
                response=AuthenticatorAssertionResponse(
                    client_data_json=base64url_to_bytes(
                        PasskeyService._require_string(
                            response, "clientDataJSON", error_cls
                        )
                    ),
                    authenticator_data=base64url_to_bytes(
                        PasskeyService._require_string(
                            response, "authenticatorData", error_cls
                        )
                    ),
                    signature=base64url_to_bytes(
                        PasskeyService._require_string(
                            response, "signature", error_cls
                        )
                    ),
                    user_handle=user_handle,
                ),
                authenticator_attachment=attachment,
            )
        except PasskeyServiceError:
            raise
        except Exception as exc:
            raise error_cls("invalid_payload") from exc

    @staticmethod
    def _parse_authenticator_attachment(
        value: Any, error_cls: Type[PasskeyServiceError]
    ) -> AuthenticatorAttachment | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise error_cls("invalid_payload")
        try:
            return AuthenticatorAttachment(value)
        except ValueError as exc:
            raise error_cls("invalid_payload") from exc

    @staticmethod
    def _parse_transports(
        transports: Any, error_cls: Type[PasskeyServiceError]
    ) -> list[AuthenticatorTransport] | None:
        if transports is None:
            return None
        if isinstance(transports, (str, bytes)) or not isinstance(transports, Iterable):
            raise error_cls("invalid_payload")

        parsed: list[AuthenticatorTransport] = []
        for transport in transports:
            if not isinstance(transport, str) or not transport:
                raise error_cls("invalid_payload")
            try:
                parsed.append(AuthenticatorTransport(transport))
            except ValueError as exc:
                raise error_cls("invalid_payload") from exc
        return parsed

    @staticmethod
    def _require_string(
        payload: dict[str, Any], key: str, error_cls: Type[PasskeyServiceError]
    ) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise error_cls("invalid_payload")
        return value

    @staticmethod
    def _decode_expected_challenge(
        value, error_cls: Type[PasskeyServiceError]
    ) -> bytes:
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)

        if isinstance(value, str):
            try:
                return base64url_to_bytes(value)
            except Exception as exc:
                raise error_cls("invalid_challenge") from exc

        raise error_cls("invalid_challenge")
