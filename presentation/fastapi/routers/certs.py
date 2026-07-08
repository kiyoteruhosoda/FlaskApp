"""証明書管理 FastAPI ルーター。

Flask版 ``bounded_contexts/certs/presentation/api/routes.py`` を移植。
app.py では ``/api`` プレフィックスで登録する。
"""
from __future__ import annotations

import base64
import binascii
import logging
import re
from datetime import datetime
from typing import Any, Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.i18n.translation import gettext as _
from presentation.fastapi.dependencies.auth import get_current_principal, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(tags=["certs"])

_GROUP_CODE_PATTERN = re.compile(r"^[a-z0-9_-]+$")


# ---------------------------------------------------------------------------
# 権限依存関数
# ---------------------------------------------------------------------------


async def _require_sign_permission(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    """certificate:sign または certificate:manage を持つ場合のみ許可する。"""
    if not (principal.can("certificate:sign") or principal.can("certificate:manage")):
        raise HTTPException(status_code=403, detail={"error": "Forbidden"})
    return principal


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------


def _normalize_group_code(value: str | None, *, required: bool = True) -> str:
    code = (value or "").strip()
    if not code:
        if required:
            raise HTTPException(status_code=400, detail={"error": _("Group code is required.")})
        return ""
    if not _GROUP_CODE_PATTERN.fullmatch(code):
        raise HTTPException(
            status_code=400,
            detail={"error": _("Group code must contain only lowercase letters, numbers, hyphen, or underscore.")},
        )
    return code


def _resolve_actor(principal: AuthenticatedPrincipal) -> str:
    return principal.identifier


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return default
    return bool(value)


def _resolve_usage_type(value: str | None):
    from bounded_contexts.certs.domain.usage import UsageType
    from bounded_contexts.certs.domain.exceptions import CertificateValidationError

    try:
        return UsageType.from_str(value)
    except ValueError as exc:
        raise CertificateValidationError(str(exc)) from exc


def _serialize_group(group) -> dict[str, Any]:
    return {
        "groupCode": group.group_code,
        "displayName": group.display_name,
        "usageType": group.usage_type.value,
        "keyType": group.key_type,
        "keyCurve": group.key_curve,
        "keySize": group.key_size,
        "autoRotate": group.rotation_policy.auto_rotate,
        "rotationThresholdDays": group.rotation_policy.rotation_threshold_days,
        "subject": group.subject_dict(),
        "createdAt": group.created_at.isoformat() if group.created_at else None,
        "updatedAt": group.updated_at.isoformat() if group.updated_at else None,
    }


_KEY_USAGE_SERIALIZATION_ORDER: list[tuple[str, str]] = [
    ("digitalSignature", "digital_signature"),
    ("contentCommitment", "content_commitment"),
    ("keyEncipherment", "key_encipherment"),
    ("dataEncipherment", "data_encipherment"),
    ("keyAgreement", "key_agreement"),
    ("keyCertSign", "key_cert_sign"),
    ("crlSign", "crl_sign"),
    ("encipherOnly", "encipher_only"),
    ("decipherOnly", "decipher_only"),
]

_EXTENDED_KEY_USAGE_NAME_MAP: dict[x509.ObjectIdentifier, str] = {}
for _attr_name, _api_name in [
    ("SERVER_AUTH", "serverAuth"),
    ("CLIENT_AUTH", "clientAuth"),
    ("CODE_SIGNING", "codeSigning"),
    ("EMAIL_PROTECTION", "emailProtection"),
    ("TIME_STAMPING", "timeStamping"),
    ("OCSP_SIGNING", "ocspSigning"),
    ("IPSEC_END_SYSTEM", "ipsecEndSystem"),
    ("IPSEC_TUNNEL", "ipsecTunnel"),
    ("IPSEC_USER", "ipsecUser"),
    ("ANY_EXTENDED_KEY_USAGE", "anyExtendedKeyUsage"),
]:
    _oid = getattr(ExtendedKeyUsageOID, _attr_name, None)
    if _oid is not None:
        _EXTENDED_KEY_USAGE_NAME_MAP[_oid] = _api_name


def _extract_key_usage_values(certificate: x509.Certificate) -> list[str]:
    try:
        extension = certificate.extensions.get_extension_for_class(x509.KeyUsage)
    except x509.ExtensionNotFound:
        return []

    key_usage = extension.value
    values: list[str] = []
    for api_name, attr in _KEY_USAGE_SERIALIZATION_ORDER:
        try:
            enabled = getattr(key_usage, attr)
        except ValueError:
            enabled = False
        if enabled:
            values.append(api_name)
    return values


def _extract_extended_key_usage_values(certificate: x509.Certificate) -> list[str]:
    try:
        extension = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    except x509.ExtensionNotFound:
        return []

    names: list[str] = []
    for oid in extension.value:
        names.append(_EXTENDED_KEY_USAGE_NAME_MAP.get(oid, oid.dotted_string))
    return names


def _serialize_certificate(cert, *, include_pem: bool = False, include_jwk: bool = False) -> dict:
    certificate = cert.certificate
    subject = ""
    issuer = ""
    not_before: datetime | None = None
    not_after: datetime | None = None
    key_usage_values: list[str] = []
    extended_key_usage_values: list[str] = []
    if certificate is not None:
        if hasattr(certificate, "not_valid_before_utc"):
            not_before = certificate.not_valid_before_utc
        else:
            not_before = certificate.not_valid_before
        if hasattr(certificate, "not_valid_after_utc"):
            not_after = certificate.not_valid_after_utc
        else:
            not_after = certificate.not_valid_after
        subject = certificate.subject.rfc4514_string()
        issuer = certificate.issuer.rfc4514_string()
        key_usage_values = _extract_key_usage_values(certificate)
        extended_key_usage_values = _extract_extended_key_usage_values(certificate)
    else:
        not_before = cert.issued_at
        not_after = cert.expires_at

    payload: dict[str, object] = {
        "kid": cert.kid,
        "usageType": cert.usage_type.value,
        "issuedAt": cert.issued_at.isoformat() if cert.issued_at else None,
        "expiresAt": cert.expires_at.isoformat()
        if cert.expires_at
        else (not_after.isoformat() if not_after else None),
        "revokedAt": cert.revoked_at.isoformat() if cert.revoked_at else None,
        "revocationReason": cert.revocation_reason,
        "subject": subject,
        "issuer": issuer,
        "notBefore": not_before.isoformat() if not_before else None,
        "notAfter": not_after.isoformat() if not_after else None,
        "groupId": cert.group_id,
        "groupCode": cert.group.group_code if cert.group else None,
        "autoRotatedFromKid": cert.auto_rotated_from_kid,
    }
    payload["keyUsage"] = key_usage_values
    payload["extendedKeyUsage"] = extended_key_usage_values
    if include_pem:
        payload["certificatePem"] = cert.certificate_pem or ""
    if include_jwk:
        payload["jwk"] = cert.jwk
    return payload


def _parse_group_payload(payload: dict[str, Any], *, group_code: str | None = None):
    from bounded_contexts.certs.application.dto import CertificateGroupInput
    from bounded_contexts.certs.domain.exceptions import CertificateValidationError

    raw_code = group_code if group_code is not None else payload.get("groupCode")
    if raw_code is not None and not isinstance(raw_code, str):
        raise HTTPException(status_code=400, detail={"error": _("Group code must be a string.")})
    code = _normalize_group_code(raw_code, required=True)

    display_name = payload.get("displayName")
    if display_name is not None and not isinstance(display_name, str):
        raise HTTPException(status_code=400, detail={"error": _("Display name must be a string.")})

    try:
        usage_type = _resolve_usage_type(payload.get("usageType"))
    except CertificateValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})

    key_type = (payload.get("keyType") or "RSA").strip()
    if not key_type:
        raise HTTPException(status_code=400, detail={"error": _("Key type is required.")})
    key_curve = payload.get("keyCurve")
    if key_curve is not None and not isinstance(key_curve, str):
        raise HTTPException(status_code=400, detail={"error": _("Key curve must be a string.")})
    key_curve = key_curve.strip() if isinstance(key_curve, str) and key_curve.strip() else None

    key_size = payload.get("keySize")
    if key_size is not None:
        try:
            key_size = int(key_size)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail={"error": _("Key size must be an integer.")})

    auto_rotate = _to_bool(payload.get("autoRotate"), default=True)

    rotation_threshold_raw = payload.get("rotationThresholdDays", 30)
    try:
        rotation_threshold_days = int(rotation_threshold_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error": _("Rotation threshold days must be an integer.")})
    if rotation_threshold_days <= 0:
        raise HTTPException(status_code=400, detail={"error": _("Rotation threshold days must be at least 1.")})

    subject = payload.get("subject") or {}
    if not isinstance(subject, dict):
        raise HTTPException(status_code=400, detail={"error": _("Subject must be provided as an object.")})

    normalized_subject: dict[str, str] = {}
    for key, value in subject.items():
        if value is None:
            continue
        if not isinstance(value, str):
            value = str(value)
        trimmed = value.strip()
        if trimmed:
            normalized_subject[str(key)] = trimmed

    return CertificateGroupInput(
        group_code=code,
        display_name=display_name.strip() if isinstance(display_name, str) else None,
        usage_type=usage_type,
        key_type=key_type,
        key_curve=key_curve,
        key_size=key_size,
        auto_rotate=auto_rotate,
        rotation_threshold_days=rotation_threshold_days,
        subject=normalized_subject,
    )


def _build_search_filters(args: dict):
    from bounded_contexts.certs.application.dto import CertificateSearchFilters
    from bounded_contexts.certs.domain.exceptions import CertificateValidationError

    filters = CertificateSearchFilters()

    if "limit" in args and args["limit"] is not None:
        try:
            filters.limit = max(int(args["limit"]), 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail={"error": _("Limit must be an integer.")})
    if "offset" in args and args["offset"] is not None:
        try:
            filters.offset = max(int(args["offset"]), 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail={"error": _("Offset must be an integer.")})

    kid = (args.get("kid") or "").strip()
    filters.kid = kid or None

    raw_group_code = args.get("group_code") or args.get("groupCode")
    if raw_group_code:
        filters.group_code = _normalize_group_code(raw_group_code, required=False) or None
    else:
        filters.group_code = None

    usage = args.get("usage_type") or args.get("usageType")
    if usage:
        try:
            filters.usage_type = _resolve_usage_type(usage)
        except CertificateValidationError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})

    subject_contains = (args.get("subject") or "").strip()
    filters.subject_contains = subject_contains or None

    issued_from = _parse_iso_datetime(args.get("issued_from") or args.get("issuedFrom"))
    if args.get("issued_from") or args.get("issuedFrom"):
        if issued_from is None:
            raise HTTPException(status_code=400, detail={"error": _("Issued-from must be in ISO 8601 format.")})
        filters.issued_from = issued_from
    issued_to = _parse_iso_datetime(args.get("issued_to") or args.get("issuedTo"))
    if args.get("issued_to") or args.get("issuedTo"):
        if issued_to is None:
            raise HTTPException(status_code=400, detail={"error": _("Issued-to must be in ISO 8601 format.")})
        filters.issued_to = issued_to

    expires_from = _parse_iso_datetime(args.get("expires_from") or args.get("expiresFrom"))
    if args.get("expires_from") or args.get("expiresFrom"):
        if expires_from is None:
            raise HTTPException(status_code=400, detail={"error": _("Expires-from must be in ISO 8601 format.")})
        filters.expires_from = expires_from
    expires_to = _parse_iso_datetime(args.get("expires_to") or args.get("expiresTo"))
    if args.get("expires_to") or args.get("expiresTo"):
        if expires_to is None:
            raise HTTPException(status_code=400, detail={"error": _("Expires-to must be in ISO 8601 format.")})
        filters.expires_to = expires_to

    revoked_param = args.get("revoked")
    if revoked_param is not None:
        if isinstance(revoked_param, str) and revoked_param.strip().lower() == "any":
            filters.revoked = None
        else:
            filters.revoked = _to_bool(revoked_param, default=False)

    return filters


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.get("/certs/groups")
async def list_certificate_groups(
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import ListCertificateGroupsUseCase

    groups = ListCertificateGroupsUseCase().execute()
    return {"groups": [_serialize_group(group) for group in groups]}


@router.post("/certs/groups", status_code=status.HTTP_201_CREATED)
async def create_certificate_group(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import CreateCertificateGroupUseCase
    from bounded_contexts.certs.domain.exceptions import CertificateGroupConflictError

    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    parsed = _parse_group_payload(payload)

    try:
        group = CreateCertificateGroupUseCase().execute(parsed, actor=_resolve_actor(principal))
    except CertificateGroupConflictError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})

    return {"group": _serialize_group(group)}


@router.put("/certs/groups/{group_code}")
async def update_certificate_group(
    group_code: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import UpdateCertificateGroupUseCase
    from bounded_contexts.certs.domain.exceptions import CertificateGroupNotFoundError

    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    parsed = _parse_group_payload(payload, group_code=group_code)

    try:
        group = UpdateCertificateGroupUseCase().execute(parsed, actor=_resolve_actor(principal))
    except CertificateGroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})

    return {"group": _serialize_group(group)}


@router.delete("/certs/groups/{group_code}")
async def delete_certificate_group(
    group_code: str,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import DeleteCertificateGroupUseCase
    from bounded_contexts.certs.domain.exceptions import (
        CertificateGroupConflictError,
        CertificateGroupNotFoundError,
    )

    code = _normalize_group_code(group_code, required=True)

    try:
        DeleteCertificateGroupUseCase().execute(code, actor=_resolve_actor(principal))
    except CertificateGroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    except CertificateGroupConflictError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})

    return {"status": "deleted", "groupCode": code}


@router.get("/certs/groups/{group_code}/certificates")
async def list_group_certificates(
    group_code: str,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import (
        GetCertificateGroupUseCase,
        ListIssuedCertificatesUseCase,
    )
    from bounded_contexts.certs.domain.exceptions import CertificateGroupNotFoundError

    code = _normalize_group_code(group_code, required=True)

    try:
        group = GetCertificateGroupUseCase().execute(code)
    except CertificateGroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})

    certificates = ListIssuedCertificatesUseCase().execute(None, group_code=code)
    return {
        "group": _serialize_group(group),
        "certificates": [_serialize_certificate(cert) for cert in certificates],
    }


@router.post("/certs/groups/{group_code}/certificates", status_code=status.HTTP_201_CREATED)
async def issue_certificate_for_group(
    group_code: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import IssueCertificateForGroupUseCase
    from bounded_contexts.certs.domain.exceptions import (
        CertificateError,
        CertificateGroupNotFoundError,
        CertificateValidationError,
        KeyGenerationError,
    )

    code = _normalize_group_code(group_code, required=True)
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}

    subject_overrides = None
    if "subject" in payload:
        if not isinstance(payload.get("subject"), dict):
            raise HTTPException(status_code=400, detail={"error": _("Subject must be provided as an object.")})
        subject_overrides = {
            str(key): str(value).strip()
            for key, value in payload["subject"].items()
            if value is not None and str(value).strip()
        }

    valid_days = None
    if "validDays" in payload:
        try:
            valid_days = int(payload.get("validDays"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail={"error": _("Valid days must be an integer.")})

    key_usage = None
    if "keyUsage" in payload:
        key_usage_value = payload.get("keyUsage")
        if not isinstance(key_usage_value, (list, tuple)):
            raise HTTPException(status_code=400, detail={"error": _("Key usage must be provided as an array.")})
        key_usage = [str(item) for item in key_usage_value]

    try:
        result = IssueCertificateForGroupUseCase().execute(
            code,
            actor=_resolve_actor(principal),
            subject_overrides=subject_overrides,
            valid_days=valid_days,
            key_usage=key_usage,
        )
    except CertificateGroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    except CertificateValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except KeyGenerationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except CertificateError as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)})

    return {
        "certificate": {
            "kid": result.kid,
            "certificatePem": result.certificate_pem,
            "privateKeyPem": result.private_key_pem,
            "jwk": result.jwk,
            "usageType": result.usage_type.value,
            "groupCode": result.group_code,
        }
    }


@router.post("/certs/groups/{group_code}/certificates/{kid}/revoke")
async def revoke_certificate_in_group(
    group_code: str,
    kid: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import (
        GetIssuedCertificateUseCase,
        RevokeCertificateUseCase,
    )
    from bounded_contexts.certs.domain.exceptions import CertificateNotFoundError

    code = _normalize_group_code(group_code, required=True)
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise HTTPException(status_code=400, detail={"error": _("Reason must be a string.")})

    try:
        certificate = GetIssuedCertificateUseCase().execute(kid)
    except CertificateNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})

    if certificate.group is None or certificate.group.group_code != code:
        raise HTTPException(status_code=404, detail={"error": _("The certificate does not exist in the specified group.")})

    certificate = RevokeCertificateUseCase().execute(
        kid,
        reason or None,
        actor=_resolve_actor(principal),
    )
    return {"certificate": _serialize_certificate(certificate, include_pem=True, include_jwk=True)}


@router.get("/keys/{group_code}")
async def get_latest_group_key(
    group_code: str,
    principal: AuthenticatedPrincipal = Depends(_require_sign_permission),
):
    from bounded_contexts.certs.application.use_cases import ListJwksUseCase
    from bounded_contexts.certs.domain.exceptions import CertificateGroupNotFoundError

    code = _normalize_group_code(group_code, required=True)

    try:
        result = ListJwksUseCase().execute(code, latest_only=True)
    except CertificateGroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})

    latest_keys: list[dict] = []
    for entry in result.get("keys", []):
        if not isinstance(entry, dict):
            continue
        if "key" in entry and isinstance(entry["key"], dict):
            jwk = dict(entry["key"])
        else:
            jwk = {k: v for k, v in entry.items() if k != "attributes"}
        latest_keys.append(jwk)
    return {"keys": latest_keys}


@router.post("/keys/{group_code}/{kid}/sign")
async def sign_group_key(
    group_code: str,
    kid: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(_require_sign_permission),
):
    from bounded_contexts.certs.application.dto import SignGroupPayloadInput
    from bounded_contexts.certs.application.use_cases import SignGroupPayloadUseCase
    from bounded_contexts.certs.domain.exceptions import (
        CertificateError,
        CertificateGroupNotFoundError,
        CertificateNotFoundError,
        CertificateValidationError,
    )

    code = _normalize_group_code(group_code, required=True)
    kid_value = kid.strip()
    if not kid_value:
        raise HTTPException(status_code=400, detail={"error": _("kid must be a non-empty string.")})

    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    raw_payload = payload.get("payload")
    if raw_payload is None:
        raise HTTPException(status_code=400, detail={"error": _("Payload is required.")})
    if not isinstance(raw_payload, str):
        raise HTTPException(status_code=400, detail={"error": _("Payload must be provided as a base64-encoded string.")})

    raw_payload_stripped = raw_payload.strip()
    if not raw_payload_stripped:
        raise HTTPException(status_code=400, detail={"error": _("Payload must be provided as a base64-encoded string.")})

    encoding_value = payload.get("payloadEncoding", "base64")
    if not isinstance(encoding_value, str):
        raise HTTPException(status_code=400, detail={"error": _('payloadEncoding must be "base64" or "base64url".')})
    encoding_normalized = encoding_value.strip().lower() or "base64"
    if encoding_normalized not in {"base64", "base64url"}:
        raise HTTPException(status_code=400, detail={"error": _('payloadEncoding must be "base64" or "base64url".')})

    try:
        if encoding_normalized == "base64":
            payload_bytes = base64.b64decode(raw_payload_stripped, validate=True)
        else:
            padding_length = (-len(raw_payload_stripped)) % 4
            padded_payload = raw_payload_stripped + ("=" * padding_length)
            payload_bytes = base64.urlsafe_b64decode(padded_payload)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail={"error": _("Payload must be valid base64 or base64url data.")})

    hash_algorithm_value = payload.get("hashAlgorithm")
    if hash_algorithm_value is not None and not isinstance(hash_algorithm_value, str):
        raise HTTPException(status_code=400, detail={"error": _("hashAlgorithm must be a string.")})

    dto = SignGroupPayloadInput(
        group_code=code,
        payload=payload_bytes,
        kid=kid_value,
        hash_algorithm=(hash_algorithm_value.strip() if isinstance(hash_algorithm_value, str) else "SHA256"),
    )

    try:
        result = SignGroupPayloadUseCase().execute(dto, actor=_resolve_actor(principal))
    except CertificateGroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    except CertificateNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    except CertificateValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except CertificateError as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)})

    signature_b64 = base64.b64encode(result.signature).decode("ascii")
    return {
        "groupCode": code,
        "kid": result.kid,
        "signature": signature_b64,
        "hashAlgorithm": result.hash_algorithm,
        "algorithm": result.algorithm,
    }


@router.post("/certs/generate")
async def generate_certificate_material(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.dto import GenerateCertificateMaterialInput
    from bounded_contexts.certs.application.use_cases import GenerateCertificateMaterialUseCase
    from bounded_contexts.certs.domain.exceptions import CertificateValidationError, KeyGenerationError

    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    try:
        usage_type = _resolve_usage_type(payload.get("usageType"))
    except CertificateValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})

    try:
        key_bits = int(payload.get("keyBits", 2048))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error": _("Key bits must be an integer.")})

    key_usage_values = payload.get("keyUsage", [])
    if not isinstance(key_usage_values, (list, tuple)):
        raise HTTPException(status_code=400, detail={"error": _("Key usage must be provided as an array of strings.")})

    dto = GenerateCertificateMaterialInput(
        subject=payload.get("subject"),
        key_type=payload.get("keyType", "RSA"),
        key_bits=key_bits,
        make_csr=_to_bool(payload.get("makeCsr", True), default=True),
        usage_type=usage_type,
        key_usage=list(key_usage_values),
    )

    try:
        result = GenerateCertificateMaterialUseCase().execute(dto)
    except KeyGenerationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except CertificateValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})

    material = result.material
    return {
        "privateKeyPem": material.private_key_pem,
        "publicKeyPem": material.public_key_pem,
        "csrPem": material.csr_pem,
        "thumbprint": material.thumbprint,
        "usageType": material.usage_type.value,
    }


@router.post("/certs/sign")
async def sign_certificate(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.dto import SignCertificateInput
    from bounded_contexts.certs.application.use_cases import SignCertificateUseCase
    from bounded_contexts.certs.domain.exceptions import CertificateError, CertificateValidationError

    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    try:
        usage_type = _resolve_usage_type(payload.get("usageType"))
    except CertificateValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})

    try:
        days = int(payload.get("days", 365))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error": _("Days must be an integer.")})

    key_usage_values = payload.get("keyUsage", [])
    if not isinstance(key_usage_values, (list, tuple)):
        raise HTTPException(status_code=400, detail={"error": _("Key usage must be provided as an array of strings.")})

    group_code_value = payload.get("groupCode")
    if group_code_value is not None and not isinstance(group_code_value, str):
        raise HTTPException(status_code=400, detail={"error": _("Group code must be a string.")})
    group_code = None
    if group_code_value is not None:
        group_code = _normalize_group_code(group_code_value, required=True)

    dto = SignCertificateInput(
        csr_pem=payload.get("csrPem", ""),
        usage_type=usage_type,
        days=days,
        is_ca=_to_bool(payload.get("isCa", False), default=False),
        key_usage=list(key_usage_values),
        group_code=group_code,
    )

    try:
        result = SignCertificateUseCase().execute(dto, actor=_resolve_actor(principal))
    except CertificateValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except CertificateError as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)})

    return {
        "certificatePem": result.certificate_pem,
        "kid": result.kid,
        "jwk": result.jwk,
        "usageType": result.usage_type.value,
        "groupCode": result.group_code,
    }


# NOTE: /certs/search は /certs/{kid} より先に登録する必要がある（パス競合回避）
@router.get("/certs/search")
async def search_certificates(
    limit: Optional[int] = Query(None),
    offset: Optional[int] = Query(None),
    kid: Optional[str] = Query(None),
    group_code: Optional[str] = Query(None),
    groupCode: Optional[str] = Query(None),
    usage_type: Optional[str] = Query(None),
    usageType: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    issued_from: Optional[str] = Query(None),
    issuedFrom: Optional[str] = Query(None),
    issued_to: Optional[str] = Query(None),
    issuedTo: Optional[str] = Query(None),
    expires_from: Optional[str] = Query(None),
    expiresFrom: Optional[str] = Query(None),
    expires_to: Optional[str] = Query(None),
    expiresTo: Optional[str] = Query(None),
    revoked: Optional[str] = Query(None),
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import SearchCertificatesUseCase

    args = {
        k: v for k, v in {
            "limit": limit,
            "offset": offset,
            "kid": kid,
            "group_code": group_code,
            "groupCode": groupCode,
            "usage_type": usage_type,
            "usageType": usageType,
            "subject": subject,
            "issued_from": issued_from,
            "issuedFrom": issuedFrom,
            "issued_to": issued_to,
            "issuedTo": issuedTo,
            "expires_from": expires_from,
            "expiresFrom": expiresFrom,
            "expires_to": expires_to,
            "expiresTo": expiresTo,
            "revoked": revoked,
        }.items()
        if v is not None
    }

    filters = _build_search_filters(args)
    result = SearchCertificatesUseCase().execute(filters)
    return {
        "total": result.total,
        "certificates": [_serialize_certificate(cert) for cert in result.certificates],
        "limit": filters.limit,
        "offset": filters.offset,
    }


@router.get("/.well-known/jwks/{group_code}.json")
async def jwks(group_code: str):
    from bounded_contexts.certs.application.use_cases import ListJwksUseCase
    from bounded_contexts.certs.domain.exceptions import CertificateGroupNotFoundError

    code = _normalize_group_code(group_code, required=True)

    try:
        result = ListJwksUseCase().execute(code)
    except CertificateGroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    return result


@router.get("/certs")
async def list_certificates(
    usage: Optional[str] = Query(None),
    group: Optional[str] = Query(None),
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import ListIssuedCertificatesUseCase
    from bounded_contexts.certs.domain.usage import UsageType

    usage_type = None
    if usage:
        try:
            usage_type = UsageType.from_str(usage)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})

    group_code = None
    if group:
        group_code = _normalize_group_code(group, required=False) or None

    certificates = ListIssuedCertificatesUseCase().execute(usage_type, group_code=group_code)
    return {"certificates": [_serialize_certificate(cert) for cert in certificates]}


@router.get("/certs/{kid}")
async def get_certificate(
    kid: str,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import GetIssuedCertificateUseCase
    from bounded_contexts.certs.domain.exceptions import CertificateNotFoundError

    try:
        certificate = GetIssuedCertificateUseCase().execute(kid)
    except CertificateNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})

    return {"certificate": _serialize_certificate(certificate, include_pem=True, include_jwk=True)}


@router.post("/certs/{kid}/revoke")
async def revoke_certificate(
    kid: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("certificate:manage")),
):
    from bounded_contexts.certs.application.use_cases import RevokeCertificateUseCase
    from bounded_contexts.certs.domain.exceptions import CertificateNotFoundError

    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise HTTPException(status_code=400, detail={"error": _("Reason must be a string.")})

    try:
        certificate = RevokeCertificateUseCase().execute(
            kid,
            reason or None,
            actor=_resolve_actor(principal),
        )
    except CertificateNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})

    return {"certificate": _serialize_certificate(certificate, include_pem=True, include_jwk=True)}


__all__ = ["router"]
