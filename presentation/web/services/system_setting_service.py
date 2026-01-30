"""Services for managing persisted system settings."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from flask_babel import gettext as _

from core.db import db
from core.models.system_setting import SystemSetting
from core.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)
from bounded_contexts.certs.application.services import default_certificate_services
from bounded_contexts.certs.application.use_cases import (
    GetCertificateGroupUseCase,
    GetIssuedCertificateUseCase,
    ListIssuedCertificatesUseCase,
)
from bounded_contexts.certs.domain.exceptions import (
    CertificateGroupNotFoundError,
    CertificateNotFoundError,
    CertificatePrivateKeyNotFoundError,
)
from bounded_contexts.certs.domain.usage import UsageType


class SystemSettingError(RuntimeError):
    """Base exception for system setting operations."""


class AccessTokenSigningValidationError(SystemSettingError):
    """Raised when updating the access token signing configuration fails."""


@dataclass(slots=True)
class AccessTokenSigningSetting:
    """Structured representation of the access token signing configuration."""

    mode: str
    kid: str | None = None
    group_code: str | None = None

    @property
    def is_builtin(self) -> bool:
        return self.mode == "builtin"

    @property
    def is_server_signing(self) -> bool:
        return self.mode == "server_signing"

    @property
    def has_group(self) -> bool:
        return bool(self.group_code and self.group_code.strip())


class SystemSettingService:
    """Read and update persistent system settings."""

    _ACCESS_TOKEN_SIGNING_KEY = "access_token_signing"
    _APPLICATION_CONFIG_KEY = "app.config"
    _CORS_CONFIG_KEY = "app.cors"
    _DEFAULT_ACCESS_TOKEN_SIGNING = AccessTokenSigningSetting(mode="builtin")

    @classmethod
    def get_access_token_signing_setting(cls) -> AccessTokenSigningSetting:
        record = cls._get_setting_record(cls._ACCESS_TOKEN_SIGNING_KEY)
        if record is None:
            return cls._DEFAULT_ACCESS_TOKEN_SIGNING

        payload = record.setting_json or {}

        mode = str(payload.get("mode") or "builtin").strip()
        if mode != "server_signing":
            return cls._DEFAULT_ACCESS_TOKEN_SIGNING

        kid = payload.get("kid")
        group_code = payload.get("groupCode")
        normalized_kid = kid.strip() if isinstance(kid, str) and kid.strip() else None
        normalized_group_code = (
            group_code.strip() if isinstance(group_code, str) and group_code.strip() else None
        )

        if normalized_group_code is None and normalized_kid is not None:
            certificate = cls._load_server_signing_certificate(normalized_kid)
            normalized_group_code = certificate.group.group_code

        if normalized_group_code is None:
            raise AccessTokenSigningValidationError(
                _("The access token signing configuration is missing a certificate group."),
            )

        return AccessTokenSigningSetting(
            mode="server_signing",
            kid=normalized_kid,
            group_code=normalized_group_code,
        )

    @classmethod
    def update_access_token_signing_setting(
        cls,
        mode: str,
        *,
        group_code: str | None = None,
    ) -> AccessTokenSigningSetting:
        normalized_mode = (mode or "").strip()
        if normalized_mode == "builtin":
            value = {"mode": "builtin"}
            return cls._persist_access_token_signing(value, AccessTokenSigningSetting(mode="builtin"))

        if normalized_mode != "server_signing":
            raise AccessTokenSigningValidationError(_("Unsupported signing mode was specified."))

        if not group_code or not group_code.strip():
            raise AccessTokenSigningValidationError(_("Please select a certificate group for signing."))

        certificate = cls._select_latest_server_signing_certificate(group_code.strip())

        value = {
            "mode": "server_signing",
            "kid": certificate.kid,
            "groupCode": certificate.group.group_code if certificate.group else None,
        }
        setting = AccessTokenSigningSetting(
            mode="server_signing",
            kid=certificate.kid,
            group_code=certificate.group.group_code if certificate.group else None,
        )
        return cls._persist_access_token_signing(value, setting)

    @classmethod
    def resolve_active_server_signing_certificate(
        cls, setting: AccessTokenSigningSetting
    ):
        """Locate the active certificate referenced by the current signing configuration."""

        if setting.group_code:
            return cls._select_latest_server_signing_certificate(setting.group_code)

        if setting.kid:
            return cls._load_server_signing_certificate(setting.kid)

        raise AccessTokenSigningValidationError(
            _("No certificate group has been configured for server signing."),
        )

    @classmethod
    def _load_server_signing_certificate(cls, kid: str):
        try:
            certificate = GetIssuedCertificateUseCase().execute(kid)
        except CertificateNotFoundError as exc:
            raise AccessTokenSigningValidationError(_("The selected certificate could not be found.")) from exc

        if certificate.usage_type != UsageType.SERVER_SIGNING:
            raise AccessTokenSigningValidationError(
                _("The certificate is not issued for server signing usage."),
            )

        now = datetime.now(timezone.utc)
        revoked_at = cls._to_utc(certificate.revoked_at)
        if revoked_at is not None and revoked_at <= now:
            raise AccessTokenSigningValidationError(_("The certificate has been revoked."))
        expires_at = cls._to_utc(certificate.expires_at)
        if expires_at is not None and expires_at <= now:
            raise AccessTokenSigningValidationError(_("The certificate has expired."))
        if certificate.group is None:
            raise AccessTokenSigningValidationError(_("The certificate is not associated with a group."))

        try:
            default_certificate_services.private_key_store.get(certificate.kid)
        except CertificatePrivateKeyNotFoundError as exc:
            raise AccessTokenSigningValidationError(
                _("The private key for the selected certificate is missing."),
            ) from exc

        return certificate

    @classmethod
    def _select_latest_server_signing_certificate(cls, group_code: str):
        try:
            group = GetCertificateGroupUseCase().execute(group_code)
        except CertificateGroupNotFoundError as exc:
            raise AccessTokenSigningValidationError(
                _("The selected certificate group could not be found."),
            ) from exc

        if group.usage_type != UsageType.SERVER_SIGNING:
            raise AccessTokenSigningValidationError(
                _("The certificate group is not configured for server signing usage."),
            )

        certificates = ListIssuedCertificatesUseCase().execute(
            UsageType.SERVER_SIGNING,
            group_code=group.group_code,
        )
        now = datetime.now(timezone.utc)

        for certificate in certificates:
            revoked_at = cls._to_utc(certificate.revoked_at)
            if revoked_at is not None and revoked_at <= now:
                continue
            expires_at = cls._to_utc(certificate.expires_at)
            if expires_at is not None and expires_at <= now:
                continue
            if certificate.group is None:
                continue
            try:
                default_certificate_services.private_key_store.get(certificate.kid)
            except CertificatePrivateKeyNotFoundError:
                continue
            return certificate

        raise AccessTokenSigningValidationError(
            _("No active certificates are available in the selected group."),
        )

    @classmethod
    def _persist_access_token_signing(
        cls,
        value: dict,
        setting: AccessTokenSigningSetting,
    ) -> AccessTokenSigningSetting:
        record = cls._get_setting_record(cls._ACCESS_TOKEN_SIGNING_KEY)
        if record is None:
            record = SystemSetting(
                setting_key=cls._ACCESS_TOKEN_SIGNING_KEY,
                setting_json=value,
                description="Access token signing configuration.",
            )
        else:
            record.setting_json = value
        db.session.add(record)
        db.session.commit()
        return setting

    @classmethod
    def load_application_config(cls) -> Dict[str, Any]:
        record_values = cls.load_application_config_payload()
        return {**DEFAULT_APPLICATION_SETTINGS, **record_values}

    @classmethod
    def load_application_config_payload(cls) -> Dict[str, Any]:
        record = cls._get_setting_record(cls._APPLICATION_CONFIG_KEY)
        if record is None or not isinstance(record.setting_json, dict):
            return {}
        return dict(record.setting_json)

    @classmethod
    def load_cors_config(cls) -> Dict[str, Any]:
        record_values = cls.load_cors_config_payload()
        merged = dict(DEFAULT_CORS_SETTINGS)
        merged.update(record_values)
        return merged

    @classmethod
    def load_cors_config_payload(cls) -> Dict[str, Any]:
        record = cls._get_setting_record(cls._CORS_CONFIG_KEY)
        if record is None or not isinstance(record.setting_json, dict):
            return {}
        return dict(record.setting_json)

    @classmethod
    def upsert_application_config(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(DEFAULT_APPLICATION_SETTINGS)
        payload.update(values)
        return cls._upsert_setting(
            cls._APPLICATION_CONFIG_KEY,
            payload,
            description="Application configuration values.",
        )

    @classmethod
    def update_application_settings(
        cls,
        values: Dict[str, Any],
        *,
        remove_keys: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        current_payload = cls.load_application_config_payload()
        changed = False

        for key, value in values.items():
            if current_payload.get(key) != value:
                current_payload[key] = value
                changed = True

        if remove_keys:
            for key in remove_keys:
                if key in current_payload:
                    current_payload.pop(key)
                    changed = True

        if not changed:
            return current_payload

        return cls._upsert_setting(
            cls._APPLICATION_CONFIG_KEY,
            current_payload,
            description="Application configuration values.",
        )

    @classmethod
    def upsert_cors_config(cls, allowed_origins: Iterable[str]) -> Dict[str, Any]:
        payload = {"allowedOrigins": list(allowed_origins)}
        return cls._upsert_setting(
            cls._CORS_CONFIG_KEY,
            payload,
            description="CORS configuration.",
        )

    @classmethod
    def update_cors_settings(
        cls,
        values: Dict[str, Any],
        *,
        remove_keys: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        current_payload = cls.load_cors_config_payload()
        changed = False

        for key, value in values.items():
            if current_payload.get(key) != value:
                current_payload[key] = value
                changed = True

        if remove_keys:
            for key in remove_keys:
                if key in current_payload:
                    current_payload.pop(key)
                    changed = True

        if not changed:
            return current_payload

        return cls._upsert_setting(
            cls._CORS_CONFIG_KEY,
            current_payload,
            description="CORS configuration.",
        )

    @classmethod
    def _upsert_setting(
        cls, key: str, payload: Dict[str, Any], *, description: str | None = None
    ) -> Dict[str, Any]:
        record = cls._get_setting_record(key)
        if record is None:
            record = SystemSetting(
                setting_key=key,
                setting_json=payload,
                description=description,
            )
        else:
            record.setting_json = payload
            if description and not record.description:
                record.description = description
        db.session.add(record)
        db.session.commit()
        return payload

    @staticmethod
    def _get_setting_record(key: str) -> SystemSetting | None:
        return SystemSetting.query.filter_by(setting_key=key).one_or_none()

    @staticmethod
    def _to_utc(value):
        if value is None:
            return None
        if getattr(value, "tzinfo", None) is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


__all__ = [
    "SystemSettingError",
    "AccessTokenSigningValidationError",
    "AccessTokenSigningSetting",
    "SystemSettingService",
]
