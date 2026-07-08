"""サービスアカウント署名 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/service_account_signing.py`` を移植。
API キー認証（``certificate:sign`` スコープ）が必要。
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from http import HTTPStatus

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/service_accounts", tags=["service-account-signing"])


def _decode_signing_input(value: str, encoding: str) -> bytes:
    normalized = encoding.strip().lower() if isinstance(encoding, str) else ""
    if normalized == "plain":
        return value.encode("utf-8")
    if normalized not in {"base64", "base64url"}:
        raise ValueError('signingInputEncoding must be "plain", "base64" or "base64url".')
    value = value.strip()
    try:
        if normalized == "base64url":
            padding_length = (-len(value)) % 4
            return base64.urlsafe_b64decode(value + ("=" * padding_length))
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("signingInput must be valid base64 data.") from exc


def _extract_jwt_payload(signing_input: bytes) -> dict:
    try:
        signing_input_text = signing_input.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("signingInput must contain ASCII characters only.") from exc

    if "." not in signing_input_text:
        raise ValueError("signingInput must contain a header and payload separated by a '.' character.")

    _header_segment, payload_segment = signing_input_text.split(".", 1)
    if not _header_segment or not payload_segment:
        raise ValueError("signingInput must contain a header and payload separated by a '.' character.")

    padding_length = (-len(payload_segment)) % 4
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_segment + ("=" * padding_length))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("signingInput payload must be valid base64url data.") from exc

    try:
        payload_json = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("signingInput payload must be a valid JSON object.") from exc

    if not isinstance(payload_json, dict):
        raise ValueError("signingInput payload must be a valid JSON object.")

    return payload_json


async def _resolve_service_account(request: Request, db: Session = Depends(get_db)):
    """API キー認証でサービスアカウントを解決する。"""
    from presentation.web.auth.api_key_auth import _resolve_api_key_account

    auth_header = request.headers.get("Authorization", "")
    api_key = None
    if auth_header.lower().startswith("bearer "):
        api_key = auth_header[7:].strip()
    if not api_key:
        api_key = request.headers.get("X-Api-Key", "").strip()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required."},
        )

    try:
        account = _resolve_api_key_account(api_key, required_scopes=["certificate:sign"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required."},
        )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required."},
        )
    return account


@router.post("/signatures")
async def create_service_account_signature(
    body: dict,
    db: Session = Depends(get_db),
    account=Depends(_resolve_service_account),
):
    """サービスアカウント証明書でペイロードを署名する。"""
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from bounded_contexts.certs.application.dto import SignGroupPayloadInput
    from bounded_contexts.certs.application.services import default_certificate_services
    from bounded_contexts.certs.application.use_cases import SignGroupPayloadUseCase
    from bounded_contexts.certs.domain.exceptions import (
        CertificateError,
        CertificateGroupNotFoundError,
        CertificateNotFoundError,
        CertificateValidationError,
    )
    from bounded_contexts.certs.domain.usage import UsageType

    if not account.certificate_group_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "The service account is not linked to a certificate group."},
        )

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Request body must be a JSON object."},
        )

    signing_input = body.get("signingInput")
    if not isinstance(signing_input, str) or not signing_input.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "signingInput must be a non-empty string."},
        )

    encoding_value = body.get("signingInputEncoding", "base64")
    if encoding_value is not None and not isinstance(encoding_value, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": 'signingInputEncoding must be "plain", "base64" or "base64url".'},
        )

    kid_value = body.get("kid")
    if not isinstance(kid_value, str) or not kid_value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "kid must be provided."},
        )
    normalized_kid = kid_value.strip()

    try:
        certificate = default_certificate_services.issued_store.get(normalized_kid)
    except CertificateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "The signing request key is not permitted for this service account."},
        )

    if (
        certificate.group is None
        or certificate.group.group_code != account.certificate_group_code
        or certificate.usage_type != UsageType.CLIENT_SIGNING
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "The signing request key is not permitted for this service account."},
        )

    hash_algorithm_value = body.get("hashAlgorithm")
    if hash_algorithm_value is not None and not isinstance(hash_algorithm_value, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "hashAlgorithm must be a string."},
        )

    try:
        signing_input_bytes = _decode_signing_input(signing_input, encoding_value or "base64")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": str(exc)})

    try:
        payload_claims = _extract_jwt_payload(signing_input_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": str(exc)})

    expected_audiences = settings.service_account_signing_audiences
    if expected_audiences:
        aud_claim = payload_claims.get("aud")
        if isinstance(aud_claim, str):
            provided_audiences = [aud_claim]
        elif isinstance(aud_claim, list):
            provided_audiences = [v for v in aud_claim if isinstance(v, str)]
        else:
            provided_audiences = []

        if not provided_audiences or not any(aud in expected_audiences for aud in provided_audiences):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "The signing request audience is not allowed."},
            )

    scope_claim = payload_claims.get("scope")
    if not isinstance(scope_claim, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "The signing request must include a scope claim."},
        )

    requested_scopes = [s for s in scope_claim.split() if s]
    account_scopes = set(account.scopes)
    if not set(requested_scopes).issubset(account_scopes):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "The signing request scope is not permitted."},
        )

    dto = SignGroupPayloadInput(
        group_code=account.certificate_group_code,
        payload=signing_input_bytes,
        kid=normalized_kid,
        hash_algorithm=(hash_algorithm_value.strip() if isinstance(hash_algorithm_value, str) else "SHA256"),
    )

    try:
        result = SignGroupPayloadUseCase().execute(dto, actor=account.name)
    except CertificateGroupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": str(exc)})
    except CertificateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": str(exc)})
    except CertificateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": str(exc)})
    except CertificateError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"error": str(exc)})

    signature_bytes = result.signature
    if result.algorithm.startswith("ES"):
        component_size = int(result.algorithm[2:]) // 8
        r_value, s_value = decode_dss_signature(signature_bytes)
        signature_bytes = r_value.to_bytes(component_size, "big") + s_value.to_bytes(component_size, "big")

    signature_segment = base64.urlsafe_b64encode(signature_bytes).rstrip(b"=").decode("ascii")

    return {
        "groupCode": account.certificate_group_code,
        "kid": result.kid,
        "algorithm": result.algorithm,
        "hashAlgorithm": result.hash_algorithm,
        "signature": signature_segment,
    }
