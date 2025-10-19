from __future__ import annotations

import base64
import binascii
from http import HTTPStatus

from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from flask import g, jsonify, request
from flask_babel import gettext as _

from features.certs.application.dto import SignGroupPayloadInput
from features.certs.application.use_cases import SignGroupPayloadUseCase
from features.certs.domain.exceptions import (
    CertificateError,
    CertificateGroupNotFoundError,
    CertificateNotFoundError,
    CertificateValidationError,
)
from webapp.auth.api_key_auth import require_api_key_scopes

from . import bp
from .openapi import json_request_body


def _json_error(message: str, status: HTTPStatus):
    return jsonify({"error": message}), status


def _decode_signing_input(value: str, encoding: str) -> bytes:
    normalized = encoding.strip().lower() if isinstance(encoding, str) else ""
    if normalized == "plain":
        return value.encode("utf-8")

    if normalized not in {"base64", "base64url"}:
        raise CertificateValidationError(_("signingInputEncoding must be \"base64\" or \"base64url\"."))

    value = value.strip()
    try:
        if normalized == "base64url":
            padding_length = (-len(value)) % 4
            return base64.urlsafe_b64decode(value + ("=" * padding_length))
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CertificateValidationError(_("signingInput must be valid base64 data.")) from exc


@bp.route("/service_accounts/signatures", methods=["POST"])
@require_api_key_scopes(["certificate:sign"])
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Submit a payload for signing with the service account certificate.",
        schema={
            "type": "object",
            "properties": {
                "signingInput": {
                    "type": "string",
                    "description": "Payload to sign encoded in base64 or base64url.",
                },
                "signingInputEncoding": {
                    "type": "string",
                    "enum": ["base64", "base64url"],
                    "description": "Encoding used for the signingInput value.",
                },
                "kid": {
                    "type": "string",
                    "description": "Key identifier specifying which certificate to use.",
                },
                "hashAlgorithm": {
                    "type": "string",
                    "description": "Hash algorithm hint such as SHA256.",
                },
            },
            "required": ["signingInput", "kid"],
            "additionalProperties": False,
        },
        example={
            "signingInput": "ZXhhbXBsZV9kYXRh", "signingInputEncoding": "base64", "kid": "primary", "hashAlgorithm": "SHA256"
        },
    ),
)
def create_service_account_signature():
    account = getattr(g, "service_account", None)
    if account is None:
        return _json_error(_("Authentication required."), HTTPStatus.UNAUTHORIZED)

    if not account.certificate_group_code:
        return _json_error(
            _("The service account is not linked to a certificate group."),
            HTTPStatus.BAD_REQUEST,
        )

    payload = request.get_json(silent=True) or {}

    signing_input = payload.get("signingInput")
    if not isinstance(signing_input, str) or not signing_input.strip():
        return _json_error(_("signingInput must be a base64-encoded string."), HTTPStatus.BAD_REQUEST)

    encoding_value = payload.get("signingInputEncoding", "base64")
    if encoding_value is not None and not isinstance(encoding_value, str):
        return _json_error(_("signingInputEncoding must be \"base64\" or \"base64url\"."), HTTPStatus.BAD_REQUEST)

    kid_value = payload.get("kid")
    if not isinstance(kid_value, str) or not kid_value.strip():
        return _json_error(_("kid must be provided."), HTTPStatus.BAD_REQUEST)

    hash_algorithm_value = payload.get("hashAlgorithm")
    if hash_algorithm_value is not None and not isinstance(hash_algorithm_value, str):
        return _json_error(_("hashAlgorithm must be a string."), HTTPStatus.BAD_REQUEST)

    try:
        signing_input_bytes = _decode_signing_input(signing_input, encoding_value or "base64")
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)

    dto = SignGroupPayloadInput(
        group_code=account.certificate_group_code,
        payload=signing_input_bytes,
        kid=kid_value.strip(),
        hash_algorithm=(hash_algorithm_value.strip() if isinstance(hash_algorithm_value, str) else "SHA256"),
    )

    try:
        result = SignGroupPayloadUseCase().execute(dto, actor=account.name)
    except CertificateGroupNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)
    except CertificateNotFoundError as exc:
        return _json_error(str(exc), HTTPStatus.NOT_FOUND)
    except CertificateValidationError as exc:
        return _json_error(str(exc), HTTPStatus.BAD_REQUEST)
    except CertificateError as exc:
        return _json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    signature_bytes = result.signature
    if result.algorithm.startswith("ES"):
        component_size = int(result.algorithm[2:]) // 8
        r_value, s_value = decode_dss_signature(signature_bytes)
        signature_bytes = r_value.to_bytes(component_size, "big") + s_value.to_bytes(component_size, "big")

    signature_segment = base64.urlsafe_b64encode(signature_bytes).rstrip(b"=").decode("ascii")

    return jsonify(
        {
            "groupCode": account.certificate_group_code,
            "kid": result.kid,
            "algorithm": result.algorithm,
            "hashAlgorithm": result.hash_algorithm,
            "signature": signature_segment,
        }
    )
