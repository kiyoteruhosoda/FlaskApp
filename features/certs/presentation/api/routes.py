"""証明書APIのルーティング"""
from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime
from http import HTTPStatus
from typing import Any

from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID
from cryptography.hazmat.primitives import serialization
from flask import jsonify, request
from flask_babel import gettext as _

from flask_login import current_user

from shared.application.auth import resolve_actor_identifier

from features.certs.application.dto import (
    CertificateGroupInput,
    CertificateSearchFilters,
    GenerateCertificateMaterialInput,
    SignCertificateInput,
    SignGroupPayloadInput,
)
from features.certs.application.use_cases import (
    CreateCertificateGroupUseCase,
    GenerateCertificateMaterialUseCase,
    GetCertificateGroupUseCase,
    GetIssuedCertificateUseCase,
    IssueCertificateForGroupUseCase,
    ListCertificateGroupsUseCase,
    ListIssuedCertificatesUseCase,
    ListJwksUseCase,
    RevokeCertificateUseCase,
    SearchCertificatesUseCase,
    SignCertificateUseCase,
    SignGroupPayloadUseCase,
    UpdateCertificateGroupUseCase,
    DeleteCertificateGroupUseCase,
)
from features.certs.domain.exceptions import (
    CertificateError,
    CertificateGroupConflictError,
    CertificateGroupNotFoundError,
    CertificateNotFoundError,
    CertificateValidationError,
    KeyGenerationError,
)
from features.certs.domain.models import CertificateGroup, IssuedCertificate
from features.certs.domain.usage import UsageType

from . import certs_api_bp


_GROUP_CODE_PATTERN = re.compile(r"^[a-z0-9_-]+$")


def _json_error(message: str, status: HTTPStatus):
    return jsonify({"error": message}), status


def _require_admin():
    if not current_user.is_authenticated:
        return _json_error("Authentication required", HTTPStatus.UNAUTHORIZED)
    if not current_user.can("certificate:manage"):
        return _json_error("Forbidden", HTTPStatus.FORBIDDEN)
    return None


def _require_sign_permission():
    if not current_user.is_authenticated:
        return _json_error("Authentication required", HTTPStatus.UNAUTHORIZED)
    if not current_user.can("certificate:sign", "certificate:manage"):
        return _json_error("Forbidden", HTTPStatus.FORBIDDEN)
    return None


def _resolve_actor() -> str:
    if not current_user.is_authenticated:
        return "system"
    return resolve_actor_identifier()


def _normalize_group_code(
    value: str | None,
    *,
    required: bool = True,
):
    code = (value or "").strip()
    if not code:
        if required:
            return None, _json_error(_("Group code is required."), HTTPStatus.BAD_REQUEST)
        return None, None
    if not _GROUP_CODE_PATTERN.fullmatch(code):
        return (
            None,
            _json_error(
                _("Group code must contain only lowercase letters, numbers, hyphen, or underscore."),
                HTTPStatus.BAD_REQUEST,
            ),
        )
    return code, None


def _serialize_group(group: CertificateGroup) -> dict[str, Any]:
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


def _parse_group_payload(payload: dict[str, Any], *, group_code: str | None = None) -> CertificateGroupInput | tuple[dict, int]:
    raw_code = group_code if group_code is not None else payload.get("groupCode")
    if raw_code is not None and not isinstance(raw_code, str):
        return _json_error(_("Group code must be a string."), HTTPStatus.BAD_REQUEST)
    code, error = _normalize_group_code(raw_code, required=True)
    if error:
        return error

    display_name = payload.get("displayName")
    if display_name is not None and not isinstance(display_name, str):
        return _json_error(_("Display name must be a string."), HTTPStatus.BAD_REQUEST)

    try:
        usage_type = _resolve_usage_type(payload.get("usageType"))
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)

    key_type = (payload.get("keyType") or "RSA").strip()
    if not key_type:
        return _json_error(_("Key type is required."), HTTPStatus.BAD_REQUEST)
    key_curve = payload.get("keyCurve")
    if key_curve is not None and not isinstance(key_curve, str):
        return _json_error(_("Key curve must be a string."), HTTPStatus.BAD_REQUEST)
    key_curve = key_curve.strip() if isinstance(key_curve, str) and key_curve.strip() else None

    key_size = payload.get("keySize")
    if key_size is not None:
        try:
            key_size = int(key_size)
        except (TypeError, ValueError):
            return _json_error(_("Key size must be an integer."), HTTPStatus.BAD_REQUEST)

    auto_rotate = _to_bool(payload.get("autoRotate"), default=True)

    rotation_threshold_raw = payload.get("rotationThresholdDays", 30)
    try:
        rotation_threshold_days = int(rotation_threshold_raw)
    except (TypeError, ValueError):
        return _json_error(_("Rotation threshold days must be an integer."), HTTPStatus.BAD_REQUEST)
    if rotation_threshold_days <= 0:
        return _json_error(_("Rotation threshold days must be at least 1."), HTTPStatus.BAD_REQUEST)

    subject = payload.get("subject") or {}
    if not isinstance(subject, dict):
        return _json_error(_("Subject must be provided as an object."), HTTPStatus.BAD_REQUEST)

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


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_search_filters(args) -> CertificateSearchFilters | tuple[dict, int]:
    filters = CertificateSearchFilters()

    if "limit" in args:
        try:
            filters.limit = max(int(args.get("limit")), 0)
        except (TypeError, ValueError):
            return _json_error(_("Limit must be an integer."), HTTPStatus.BAD_REQUEST)
    if "offset" in args:
        try:
            filters.offset = max(int(args.get("offset")), 0)
        except (TypeError, ValueError):
            return _json_error(_("Offset must be an integer."), HTTPStatus.BAD_REQUEST)

    kid = (args.get("kid") or "").strip()
    filters.kid = kid or None

    raw_group_code = args.get("group_code") or args.get("groupCode")
    group_code, error = _normalize_group_code(raw_group_code, required=False)
    if error:
        return error
    filters.group_code = group_code

    usage = args.get("usage_type") or args.get("usageType")
    if usage:
        try:
            filters.usage_type = _resolve_usage_type(usage)
        except CertificateValidationError as exc:
            return _json_error(str(exc), HTTPStatus.BAD_REQUEST)

    subject_contains = (args.get("subject") or "").strip()
    filters.subject_contains = subject_contains or None

    issued_from = _parse_iso_datetime(args.get("issued_from") or args.get("issuedFrom"))
    if args.get("issued_from") or args.get("issuedFrom"):
        if issued_from is None:
            return _json_error(_("Issued-from must be in ISO 8601 format."), HTTPStatus.BAD_REQUEST)
        filters.issued_from = issued_from
    issued_to = _parse_iso_datetime(args.get("issued_to") or args.get("issuedTo"))
    if args.get("issued_to") or args.get("issuedTo"):
        if issued_to is None:
            return _json_error(_("Issued-to must be in ISO 8601 format."), HTTPStatus.BAD_REQUEST)
        filters.issued_to = issued_to

    expires_from = _parse_iso_datetime(args.get("expires_from") or args.get("expiresFrom"))
    if args.get("expires_from") or args.get("expiresFrom"):
        if expires_from is None:
            return _json_error(_("Expires-from must be in ISO 8601 format."), HTTPStatus.BAD_REQUEST)
        filters.expires_from = expires_from
    expires_to = _parse_iso_datetime(args.get("expires_to") or args.get("expiresTo"))
    if args.get("expires_to") or args.get("expiresTo"):
        if expires_to is None:
            return _json_error(_("Expires-to must be in ISO 8601 format."), HTTPStatus.BAD_REQUEST)
        filters.expires_to = expires_to

    revoked_param = args.get("revoked")
    if revoked_param is not None:
        revoked = _to_bool(revoked_param, default=False)
        if isinstance(revoked_param, str) and revoked_param.strip().lower() == "any":
            filters.revoked = None
        else:
            filters.revoked = revoked

    return filters


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


_EXTENDED_KEY_USAGE_NAME_MAP: dict[x509.ObjectIdentifier, str] = {}
for attr_name, api_name in [
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
    oid = getattr(ExtendedKeyUsageOID, attr_name, None)
    if oid is not None:
        _EXTENDED_KEY_USAGE_NAME_MAP[oid] = api_name


def _extract_extended_key_usage_values(certificate: x509.Certificate) -> list[str]:
    try:
        extension = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    except x509.ExtensionNotFound:
        return []

    names: list[str] = []
    for oid in extension.value:
        names.append(_EXTENDED_KEY_USAGE_NAME_MAP.get(oid, oid.dotted_string))
    return names


def _serialize_certificate(
    cert: IssuedCertificate,
    *,
    include_pem: bool = False,
    include_jwk: bool = False,
) -> dict:
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
        else:  # pragma: no cover - 古いcryptographyバージョンへのフォールバック
            not_before = certificate.not_valid_before
        if hasattr(certificate, "not_valid_after_utc"):
            not_after = certificate.not_valid_after_utc
        else:  # pragma: no cover - 古いcryptographyバージョンへのフォールバック
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


@certs_api_bp.route("/certs/groups", methods=["GET"])
def list_certificate_groups():
    guard = _require_admin()
    if guard:
        return guard

    groups = ListCertificateGroupsUseCase().execute()
    return jsonify({"groups": [_serialize_group(group) for group in groups]})


@certs_api_bp.route("/certs/groups", methods=["POST"])
def create_certificate_group():
    guard = _require_admin()
    if guard:
        return guard

    payload = request.get_json(silent=True) or {}
    parsed = _parse_group_payload(payload)
    if isinstance(parsed, tuple):
        return parsed

    try:
        group = CreateCertificateGroupUseCase().execute(parsed, actor=_resolve_actor())
    except CertificateGroupConflictError as exc:
        return _json_error(str(exc), HTTPStatus.CONFLICT)

    return jsonify({"group": _serialize_group(group)}), HTTPStatus.CREATED


@certs_api_bp.route("/certs/groups/<string:group_code>", methods=["PUT"])
def update_certificate_group(group_code: str):
    guard = _require_admin()
    if guard:
        return guard

    payload = request.get_json(silent=True) or {}
    parsed = _parse_group_payload(payload, group_code=group_code)
    if isinstance(parsed, tuple):
        return parsed

    try:
        group = UpdateCertificateGroupUseCase().execute(parsed, actor=_resolve_actor())
    except CertificateGroupNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)

    return jsonify({"group": _serialize_group(group)})


@certs_api_bp.route("/certs/groups/<string:group_code>", methods=["DELETE"])
def delete_certificate_group(group_code: str):
    guard = _require_admin()
    if guard:
        return guard

    group_code, error = _normalize_group_code(group_code, required=True)
    if error:
        return error

    try:
        DeleteCertificateGroupUseCase().execute(group_code, actor=_resolve_actor())
    except CertificateGroupNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)
    except CertificateGroupConflictError as exc:
        return _json_error(str(exc), HTTPStatus.CONFLICT)

    return jsonify({"status": "deleted", "groupCode": group_code})


@certs_api_bp.route("/certs/groups/<string:group_code>/certificates", methods=["GET"])
def list_group_certificates(group_code: str):
    guard = _require_admin()
    if guard:
        return guard

    group_code, error = _normalize_group_code(group_code, required=True)
    if error:
        return error

    try:
        group = GetCertificateGroupUseCase().execute(group_code)
    except CertificateGroupNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)

    certificates = ListIssuedCertificatesUseCase().execute(None, group_code=group_code)
    return jsonify(
        {
            "group": _serialize_group(group),
            "certificates": [_serialize_certificate(cert) for cert in certificates],
        }
    )


@certs_api_bp.route("/certs/groups/<string:group_code>/certificates", methods=["POST"])
def issue_certificate_for_group(group_code: str):
    guard = _require_admin()
    if guard:
        return guard

    group_code, error = _normalize_group_code(group_code, required=True)
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    subject_overrides = None
    if "subject" in payload:
        if not isinstance(payload.get("subject"), dict):
            return _json_error(_("Subject must be provided as an object."), HTTPStatus.BAD_REQUEST)
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
            return _json_error(_("Valid days must be an integer."), HTTPStatus.BAD_REQUEST)

    key_usage = None
    if "keyUsage" in payload:
        key_usage_value = payload.get("keyUsage")
        if not isinstance(key_usage_value, (list, tuple)):
            return _json_error(_("Key usage must be provided as an array."), HTTPStatus.BAD_REQUEST)
        key_usage = [str(item) for item in key_usage_value]

    try:
        result = IssueCertificateForGroupUseCase().execute(
            group_code,
            actor=_resolve_actor(),
            subject_overrides=subject_overrides,
            valid_days=valid_days,
            key_usage=key_usage,
        )
    except CertificateGroupNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)
    except KeyGenerationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)
    except CertificateError as exc:
        return _json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    return (
        jsonify(
            {
                "certificate": {
                    "kid": result.kid,
                    "certificatePem": result.certificate_pem,
                    "privateKeyPem": result.private_key_pem,
                    "jwk": result.jwk,
                    "usageType": result.usage_type.value,
                    "groupCode": result.group_code,
                }
            }
        ),
        HTTPStatus.CREATED,
    )


@certs_api_bp.route("/keys/<string:group_code>", methods=["GET"])
def get_latest_group_key(group_code: str):
    guard = _require_sign_permission()
    if guard:
        return guard

    group_code, error = _normalize_group_code(group_code, required=True)
    if error:
        return error

    try:
        result = ListJwksUseCase().execute(group_code, latest_only=True)
    except CertificateGroupNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)
    latest_keys: list[dict] = []
    for entry in result.get("keys", []):
        if not isinstance(entry, dict):
            continue
        if "key" in entry and isinstance(entry["key"], dict):
            jwk = dict(entry["key"])
        else:
            jwk = {k: v for k, v in entry.items() if k != "attributes"}
        latest_keys.append(jwk)
    return jsonify({"keys": latest_keys})


@certs_api_bp.route("/keys/<string:group_code>/<string:kid>/sign", methods=["POST"])
def sign_group_key(group_code: str, kid: str):
    guard = _require_sign_permission()
    if guard:
        return guard

    group_code, error = _normalize_group_code(group_code, required=True)
    if error:
        return error

    kid_value = kid.strip()
    if not kid_value:
        return _json_error(_("kid must be a non-empty string."), HTTPStatus.BAD_REQUEST)

    payload = request.get_json(silent=True) or {}
    raw_payload = payload.get("payload")
    if raw_payload is None:
        return _json_error(_("Payload is required."), HTTPStatus.BAD_REQUEST)
    if not isinstance(raw_payload, str):
        return _json_error(_("Payload must be provided as a base64-encoded string."), HTTPStatus.BAD_REQUEST)

    raw_payload_stripped = raw_payload.strip()
    if not raw_payload_stripped:
        return _json_error(_("Payload must be provided as a base64-encoded string."), HTTPStatus.BAD_REQUEST)

    encoding_value = payload.get("payloadEncoding", "base64")
    if not isinstance(encoding_value, str):
        return _json_error(_("payloadEncoding must be \"base64\" or \"base64url\"."), HTTPStatus.BAD_REQUEST)
    encoding_normalized = encoding_value.strip().lower() or "base64"
    if encoding_normalized not in {"base64", "base64url"}:
        return _json_error(_("payloadEncoding must be \"base64\" or \"base64url\"."), HTTPStatus.BAD_REQUEST)

    try:
        if encoding_normalized == "base64":
            payload_bytes = base64.b64decode(raw_payload_stripped, validate=True)
        else:
            padding_length = (-len(raw_payload_stripped)) % 4
            padded_payload = raw_payload_stripped + ("=" * padding_length)
            payload_bytes = base64.urlsafe_b64decode(padded_payload)
    except (binascii.Error, ValueError):
        return _json_error(_("Payload must be valid base64 or base64url data."), HTTPStatus.BAD_REQUEST)

    hash_algorithm_value = payload.get("hashAlgorithm")
    if hash_algorithm_value is not None and not isinstance(hash_algorithm_value, str):
        return _json_error(_("hashAlgorithm must be a string."), HTTPStatus.BAD_REQUEST)

    dto = SignGroupPayloadInput(
        group_code=group_code,
        payload=payload_bytes,
        kid=kid_value,
        hash_algorithm=(hash_algorithm_value.strip() if isinstance(hash_algorithm_value, str) else "SHA256"),
    )

    try:
        result = SignGroupPayloadUseCase().execute(dto, actor=_resolve_actor())
    except CertificateGroupNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)
    except CertificateNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)
    except CertificateError as exc:
        return _json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    signature_b64 = base64.b64encode(result.signature).decode("ascii")

    return jsonify(
        {
            "groupCode": group_code,
            "kid": result.kid,
            "signature": signature_b64,
            "hashAlgorithm": result.hash_algorithm,
            "algorithm": result.algorithm,
        }
    )


@certs_api_bp.route(
    "/certs/groups/<string:group_code>/certificates/<string:kid>/revoke",
    methods=["POST"],
)
def revoke_certificate_in_group(group_code: str, kid: str):
    guard = _require_admin()
    if guard:
        return guard

    group_code, error = _normalize_group_code(group_code, required=True)
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _json_error(_("Reason must be a string."), HTTPStatus.BAD_REQUEST)

    try:
        certificate = GetIssuedCertificateUseCase().execute(kid)
    except CertificateNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)

    if certificate.group is None or certificate.group.group_code != group_code:
        return _json_error(_("The certificate does not exist in the specified group."), HTTPStatus.NOT_FOUND)

    certificate = RevokeCertificateUseCase().execute(
        kid,
        reason or None,
        actor=_resolve_actor(),
    )

    return jsonify(
        {"certificate": _serialize_certificate(certificate, include_pem=True, include_jwk=True)}
    )


@certs_api_bp.route("/certs/generate", methods=["POST"])
def generate_certificate_material() -> tuple[dict, int]:
    guard = _require_admin()
    if guard:
        return guard

    payload = request.get_json(silent=True) or {}
    try:
        usage_type = _resolve_usage_type(payload.get("usageType"))
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)

    try:
        key_bits = int(payload.get("keyBits", 2048))
    except (TypeError, ValueError):
        return _json_error(_("Key bits must be an integer."), HTTPStatus.BAD_REQUEST)

    key_usage_values = payload.get("keyUsage", [])
    if not isinstance(key_usage_values, (list, tuple)):
        return _json_error(_("Key usage must be provided as an array of strings."), HTTPStatus.BAD_REQUEST)

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
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)

    material = result.material
    return (
        jsonify(
            {
                "privateKeyPem": material.private_key_pem,
                "publicKeyPem": material.public_key_pem,
                "csrPem": material.csr_pem,
                "thumbprint": material.thumbprint,
                "usageType": material.usage_type.value,
            }
        ),
        HTTPStatus.OK,
    )


@certs_api_bp.route("/certs/sign", methods=["POST"])
def sign_certificate() -> tuple[dict, int]:
    guard = _require_admin()
    if guard:
        return guard

    payload = request.get_json(silent=True) or {}
    try:
        usage_type = _resolve_usage_type(payload.get("usageType"))
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)

    try:
        days = int(payload.get("days", 365))
    except (TypeError, ValueError):
        return _json_error(_("Days must be an integer."), HTTPStatus.BAD_REQUEST)

    key_usage_values = payload.get("keyUsage", [])
    if not isinstance(key_usage_values, (list, tuple)):
        return _json_error(_("Key usage must be provided as an array of strings."), HTTPStatus.BAD_REQUEST)

    group_code_value = payload.get("groupCode")
    if group_code_value is not None and not isinstance(group_code_value, str):
        return _json_error(_("Group code must be a string."), HTTPStatus.BAD_REQUEST)
    group_code = None
    if group_code_value is not None:
        group_code, error = _normalize_group_code(group_code_value, required=True)
        if error:
            return error

    dto = SignCertificateInput(
        csr_pem=payload.get("csrPem", ""),
        usage_type=usage_type,
        days=days,
        is_ca=_to_bool(payload.get("isCa", False), default=False),
        key_usage=list(key_usage_values),
        group_code=group_code,
    )

    try:
        result = SignCertificateUseCase().execute(dto, actor=_resolve_actor())
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)
    except CertificateError as exc:
        return _json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    return (
        jsonify(
            {
                "certificatePem": result.certificate_pem,
                "kid": result.kid,
                "jwk": result.jwk,
                "usageType": result.usage_type.value,
                "groupCode": result.group_code,
            }
        ),
        HTTPStatus.OK,
    )


@certs_api_bp.route("/.well-known/jwks/<group_code>.json", methods=["GET"])
def jwks(group_code: str):
    group_code, error = _normalize_group_code(group_code, required=True)
    if error:
        return error

    try:
        result = ListJwksUseCase().execute(group_code)
    except CertificateGroupNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)
    return jsonify(result)


@certs_api_bp.route("/certs", methods=["GET"])
def list_certificates():
    guard = _require_admin()
    if guard:
        return guard

    usage_param = request.args.get("usage")
    usage_type: UsageType | None = None
    if usage_param:
        try:
            usage_type = UsageType.from_str(usage_param)
        except ValueError as exc:
            return _json_error(str(exc), HTTPStatus.BAD_REQUEST)

    group_code_value = request.args.get("group")
    group_code, error = _normalize_group_code(group_code_value, required=False)
    if error:
        return error

    certificates = ListIssuedCertificatesUseCase().execute(usage_type, group_code=group_code)
    return jsonify(
        {"certificates": [_serialize_certificate(cert) for cert in certificates]}
    )


@certs_api_bp.route("/certs/<string:kid>", methods=["GET"])
def get_certificate(kid: str):
    guard = _require_admin()
    if guard:
        return guard

    try:
        certificate = GetIssuedCertificateUseCase().execute(kid)
    except CertificateNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)

    return jsonify(
        {"certificate": _serialize_certificate(certificate, include_pem=True, include_jwk=True)}
    )


@certs_api_bp.route("/certs/<string:kid>/revoke", methods=["POST"])
def revoke_certificate(kid: str):
    guard = _require_admin()
    if guard:
        return guard

    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _json_error(_("Reason must be a string."), HTTPStatus.BAD_REQUEST)

    try:
        certificate = RevokeCertificateUseCase().execute(
            kid,
            reason or None,
            actor=_resolve_actor(),
        )
    except CertificateNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)

    return jsonify(
        {"certificate": _serialize_certificate(certificate, include_pem=True, include_jwk=True)}
    )


@certs_api_bp.route("/certs/search", methods=["GET"])
def search_certificates():
    guard = _require_admin()
    if guard:
        return guard

    filters = _build_search_filters(request.args)
    if isinstance(filters, tuple):
        return filters

    result = SearchCertificatesUseCase().execute(filters)
    return jsonify(
        {
            "total": result.total,
            "certificates": [_serialize_certificate(cert) for cert in result.certificates],
            "limit": filters.limit,
            "offset": filters.offset,
        }
    )


def _resolve_usage_type(value: str | None) -> UsageType:
    try:
        return UsageType.from_str(value)
    except ValueError as exc:
        raise CertificateValidationError(str(exc)) from exc


def _to_bool(value, default: bool) -> bool:
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
