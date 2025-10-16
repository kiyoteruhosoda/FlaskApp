"""証明書APIのルーティング"""
from __future__ import annotations

from http import HTTPStatus
from typing import Any

from cryptography.hazmat.primitives import serialization
from flask import jsonify, request

from datetime import datetime

from flask_login import current_user

from features.certs.application.dto import (
    CertificateGroupInput,
    CertificateSearchFilters,
    GenerateCertificateMaterialInput,
    SignCertificateInput,
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


def _json_error(message: str, status: HTTPStatus):
    return jsonify({"error": message}), status


def _require_admin():
    if not current_user.is_authenticated:
        return _json_error("Authentication required", HTTPStatus.UNAUTHORIZED)
    if not current_user.can("certificate:manage"):
        return _json_error("Forbidden", HTTPStatus.FORBIDDEN)
    return None


def _resolve_actor() -> str:
    if current_user.is_authenticated:
        return current_user.email or current_user.display_name or "unknown"
    return "system"


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
    code = (group_code or payload.get("groupCode") or "").strip()
    if not code:
        return _json_error("groupCodeは必須です", HTTPStatus.BAD_REQUEST)

    display_name = payload.get("displayName")
    if display_name is not None and not isinstance(display_name, str):
        return _json_error("displayNameは文字列で指定してください", HTTPStatus.BAD_REQUEST)

    try:
        usage_type = _resolve_usage_type(payload.get("usageType"))
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)

    key_type = (payload.get("keyType") or "RSA").strip()
    if not key_type:
        return _json_error("keyTypeは必須です", HTTPStatus.BAD_REQUEST)
    key_curve = payload.get("keyCurve")
    if key_curve is not None and not isinstance(key_curve, str):
        return _json_error("keyCurveは文字列で指定してください", HTTPStatus.BAD_REQUEST)
    key_curve = key_curve.strip() if isinstance(key_curve, str) and key_curve.strip() else None

    key_size = payload.get("keySize")
    if key_size is not None:
        try:
            key_size = int(key_size)
        except (TypeError, ValueError):
            return _json_error("keySizeは整数で指定してください", HTTPStatus.BAD_REQUEST)

    auto_rotate = _to_bool(payload.get("autoRotate"), default=True)

    rotation_threshold_raw = payload.get("rotationThresholdDays", 30)
    try:
        rotation_threshold_days = int(rotation_threshold_raw)
    except (TypeError, ValueError):
        return _json_error("rotationThresholdDaysは整数で指定してください", HTTPStatus.BAD_REQUEST)
    if rotation_threshold_days <= 0:
        return _json_error("rotationThresholdDaysは1以上で指定してください", HTTPStatus.BAD_REQUEST)

    subject = payload.get("subject") or {}
    if not isinstance(subject, dict):
        return _json_error("subjectはオブジェクトで指定してください", HTTPStatus.BAD_REQUEST)

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
            return _json_error("limitは整数で指定してください", HTTPStatus.BAD_REQUEST)
    if "offset" in args:
        try:
            filters.offset = max(int(args.get("offset")), 0)
        except (TypeError, ValueError):
            return _json_error("offsetは整数で指定してください", HTTPStatus.BAD_REQUEST)

    kid = (args.get("kid") or "").strip()
    filters.kid = kid or None

    group_code = (args.get("group_code") or args.get("groupCode") or "").strip()
    filters.group_code = group_code or None

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
            return _json_error("issuedFromはISO8601形式で指定してください", HTTPStatus.BAD_REQUEST)
        filters.issued_from = issued_from
    issued_to = _parse_iso_datetime(args.get("issued_to") or args.get("issuedTo"))
    if args.get("issued_to") or args.get("issuedTo"):
        if issued_to is None:
            return _json_error("issuedToはISO8601形式で指定してください", HTTPStatus.BAD_REQUEST)
        filters.issued_to = issued_to

    expires_from = _parse_iso_datetime(args.get("expires_from") or args.get("expiresFrom"))
    if args.get("expires_from") or args.get("expiresFrom"):
        if expires_from is None:
            return _json_error("expiresFromはISO8601形式で指定してください", HTTPStatus.BAD_REQUEST)
        filters.expires_from = expires_from
    expires_to = _parse_iso_datetime(args.get("expires_to") or args.get("expiresTo"))
    if args.get("expires_to") or args.get("expiresTo"):
        if expires_to is None:
            return _json_error("expiresToはISO8601形式で指定してください", HTTPStatus.BAD_REQUEST)
        filters.expires_to = expires_to

    revoked_param = args.get("revoked")
    if revoked_param is not None:
        revoked = _to_bool(revoked_param, default=False)
        if isinstance(revoked_param, str) and revoked_param.strip().lower() == "any":
            filters.revoked = None
        else:
            filters.revoked = revoked

    return filters


def _serialize_certificate(
    cert: IssuedCertificate,
    *,
    include_pem: bool = False,
    include_jwk: bool = False,
) -> dict:
    certificate = cert.certificate
    if hasattr(certificate, "not_valid_before_utc"):
        not_before = certificate.not_valid_before_utc
    else:  # pragma: no cover - 古いcryptographyバージョンへのフォールバック
        not_before = certificate.not_valid_before
    if hasattr(certificate, "not_valid_after_utc"):
        not_after = certificate.not_valid_after_utc
    else:  # pragma: no cover - 古いcryptographyバージョンへのフォールバック
        not_after = certificate.not_valid_after
    payload: dict[str, object] = {
        "kid": cert.kid,
        "usageType": cert.usage_type.value,
        "issuedAt": cert.issued_at.isoformat() if cert.issued_at else None,
        "expiresAt": cert.expires_at.isoformat() if cert.expires_at else not_after.isoformat(),
        "revokedAt": cert.revoked_at.isoformat() if cert.revoked_at else None,
        "revocationReason": cert.revocation_reason,
        "subject": certificate.subject.rfc4514_string(),
        "issuer": certificate.issuer.rfc4514_string(),
        "notBefore": not_before.isoformat(),
        "notAfter": not_after.isoformat(),
        "groupId": cert.group_id,
        "groupCode": cert.group.group_code if cert.group else None,
        "autoRotatedFromKid": cert.auto_rotated_from_kid,
    }
    if include_pem:
        payload["certificatePem"] = certificate.public_bytes(
            serialization.Encoding.PEM
        ).decode("utf-8")
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

    payload = request.get_json(silent=True) or {}
    subject_overrides = None
    if "subject" in payload:
        if not isinstance(payload.get("subject"), dict):
            return _json_error("subjectはオブジェクトで指定してください", HTTPStatus.BAD_REQUEST)
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
            return _json_error("validDaysは整数で指定してください", HTTPStatus.BAD_REQUEST)
        if valid_days <= 0:
            return _json_error("validDaysは1以上で指定してください", HTTPStatus.BAD_REQUEST)

    key_usage = None
    if "keyUsage" in payload:
        key_usage_value = payload.get("keyUsage")
        if not isinstance(key_usage_value, (list, tuple)):
            return _json_error("keyUsageは配列で指定してください", HTTPStatus.BAD_REQUEST)
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


@certs_api_bp.route(
    "/certs/groups/<string:group_code>/certificates/<string:kid>/revoke",
    methods=["POST"],
)
def revoke_certificate_in_group(group_code: str, kid: str):
    guard = _require_admin()
    if guard:
        return guard

    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _json_error("reasonは文字列で指定してください", HTTPStatus.BAD_REQUEST)

    try:
        certificate = GetIssuedCertificateUseCase().execute(kid)
    except CertificateNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)

    if certificate.group is None or certificate.group.group_code != group_code:
        return _json_error("指定したグループに証明書が存在しません", HTTPStatus.NOT_FOUND)

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
        return _json_error("keyBitsは整数で指定してください", HTTPStatus.BAD_REQUEST)

    key_usage_values = payload.get("keyUsage", [])
    if not isinstance(key_usage_values, (list, tuple)):
        return _json_error("keyUsageは文字列配列で指定してください", HTTPStatus.BAD_REQUEST)

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
        return _json_error("daysは整数で指定してください", HTTPStatus.BAD_REQUEST)

    key_usage_values = payload.get("keyUsage", [])
    if not isinstance(key_usage_values, (list, tuple)):
        return _json_error("keyUsageは文字列配列で指定してください", HTTPStatus.BAD_REQUEST)

    group_code = payload.get("groupCode")
    if group_code is not None and not isinstance(group_code, str):
        return _json_error("groupCodeは文字列で指定してください", HTTPStatus.BAD_REQUEST)

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
    if not group_code:
        return _json_error("groupCodeは必須です", HTTPStatus.BAD_REQUEST)

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

    group_code = request.args.get("group")
    if group_code is not None and not group_code:
        return _json_error("groupパラメータが不正です", HTTPStatus.BAD_REQUEST)

    certificates = ListIssuedCertificatesUseCase().execute(usage_type, group_code=group_code or None)
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
        return _json_error("reasonは文字列で指定してください", HTTPStatus.BAD_REQUEST)

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
