"""証明書APIのルーティング"""
from __future__ import annotations

from http import HTTPStatus

from flask import jsonify, request

from features.certs.application.dto import (
    GenerateCertificateMaterialInput,
    SignCertificateInput,
)
from features.certs.application.use_cases import (
    GenerateCertificateMaterialUseCase,
    ListJwksUseCase,
    SignCertificateUseCase,
)
from features.certs.domain.exceptions import (
    CertificateError,
    CertificateValidationError,
    KeyGenerationError,
)
from features.certs.domain.usage import UsageType

from . import certs_api_bp


def _json_error(message: str, status: HTTPStatus):
    return jsonify({"error": message}), status


@certs_api_bp.route("/certs/generate", methods=["POST"])
def generate_certificate_material() -> tuple[dict, int]:
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

    dto = SignCertificateInput(
        csr_pem=payload.get("csrPem", ""),
        usage_type=usage_type,
        days=days,
        is_ca=_to_bool(payload.get("isCa", False), default=False),
        key_usage=list(key_usage_values),
    )

    try:
        result = SignCertificateUseCase().execute(dto)
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
            }
        ),
        HTTPStatus.OK,
    )


@certs_api_bp.route("/.well-known/jwks/<usage>.json", methods=["GET"])
def jwks(usage: str):
    try:
        usage_type = UsageType.from_str(_normalize_usage_path(usage))
    except ValueError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)

    result = ListJwksUseCase().execute(usage_type)
    return jsonify(result)


def _resolve_usage_type(value: str | None) -> UsageType:
    try:
        return UsageType.from_str(value)
    except ValueError as exc:
        raise CertificateValidationError(str(exc)) from exc


def _normalize_usage_path(value: str) -> str:
    mapping = {
        "server": UsageType.SERVER_SIGNING.value,
        "server.json": UsageType.SERVER_SIGNING.value,
        "client": UsageType.CLIENT_SIGNING.value,
        "client.json": UsageType.CLIENT_SIGNING.value,
        "encryption": UsageType.ENCRYPTION.value,
        "encryption.json": UsageType.ENCRYPTION.value,
    }
    return mapping.get(value, value)


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
