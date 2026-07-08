"""Passkey helpers extracted from presentation/web/auth/routes.py (FastAPI version)."""
from __future__ import annotations

import json
from typing import Any, Iterable

from shared.application.passkey_service import PasskeyService
from shared.infrastructure.passkey_repository import SqlAlchemyPasskeyRepository
from shared.kernel.database.db import db
from shared.kernel.settings.settings import settings
from webauthn.helpers import base64url_to_bytes

passkey_repo = SqlAlchemyPasskeyRepository(db.session)
passkey_service = PasskeyService(passkey_repo)

_DEFAULT_RP_ID_SENTINELS = {"localhost", "127.0.0.1"}
_DEFAULT_ORIGIN_SENTINELS = {
    "http://localhost",
    "http://localhost:5000",
    "https://localhost",
    "https://localhost:5000",
}


def _extract_passkey_credential_payload(
    payload: Any,
    *,
    meta_keys: Iterable[str] | None = None,
    required_keys: Iterable[str] | None = None,
) -> dict | None:
    """Return a credential payload extracted from *payload* when possible."""

    if not isinstance(payload, dict):
        return None

    nested = payload.get("credential")
    required = set(required_keys or ())
    if isinstance(nested, dict):
        if required and not required.issubset(nested):
            return None
        return nested

    meta = set(meta_keys or ())
    candidate = {key: value for key, value in payload.items() if key not in meta}
    if not candidate:
        return None

    if required and not required.issubset(candidate):
        return None

    return candidate


def _gather_passkey_payload_keys(
    payload: Any,
    *,
    meta_keys: Iterable[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Return lists of root, credential, and response keys for logging."""

    if not isinstance(payload, dict):
        return [], [], []

    root_keys = sorted(payload.keys())
    nested = payload.get("credential")
    meta = set(meta_keys or ())

    if isinstance(nested, dict):
        credential_payload: Any = nested
    else:
        credential_payload = {key: value for key, value in payload.items() if key not in meta}

    credential_keys: list[str] = []
    response_keys: list[str] = []

    if isinstance(credential_payload, dict):
        credential_keys = sorted(credential_payload.keys())
        response = credential_payload.get("response")
        if isinstance(response, dict):
            response_keys = sorted(response.keys())

    return root_keys, credential_keys, response_keys


def _extract_passkey_client_data_details(
    credential_payload: dict[str, Any],
) -> dict[str, Any]:
    """Decode clientDataJSON and return challenge/origin details."""

    details: dict[str, Any] = {
        "challenge": None,
        "origin": None,
        "raw": None,
        "error": None,
    }

    response_section = credential_payload.get("response")
    if not isinstance(response_section, dict):
        return details

    encoded_client_data = response_section.get("clientDataJSON")
    if not isinstance(encoded_client_data, str):
        return details

    try:
        decoded_bytes = base64url_to_bytes(encoded_client_data)
    except Exception as exc:
        details["error"] = f"decode_error: {exc}"
        return details

    try:
        decoded_text = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        details["error"] = f"utf8_error: {exc}"
        return details

    details["raw"] = decoded_text

    try:
        parsed = json.loads(decoded_text)
    except Exception as exc:
        details["error"] = f"json_error: {exc}"
        return details

    if isinstance(parsed, dict):
        details["challenge"] = parsed.get("challenge")
        details["origin"] = parsed.get("origin")

    return details


def _build_passkey_trace_payload(
    *,
    cause: str | None,
    expected_challenge: str | None,
    client_data_details: dict[str, Any],
    expected_rp_id: str | None,
    expected_origin: str | None,
) -> str | None:
    """Serialize trace details for structured logging."""

    raw_client_data = client_data_details.get("raw")
    preview = None
    if isinstance(raw_client_data, str):
        max_length = 512
        preview = raw_client_data if len(raw_client_data) <= max_length else f"{raw_client_data[:max_length]}…"

    payload = {
        "cause": cause,
        "expected_challenge": expected_challenge,
        "client_challenge": client_data_details.get("challenge"),
        "expected_rp_id": expected_rp_id,
        "expected_origin": expected_origin,
        "client_origin": client_data_details.get("origin"),
        "client_data_error": client_data_details.get("error"),
        "client_data_json_preview": preview,
    }

    sanitized = {key: value for key, value in payload.items() if value is not None}
    if not sanitized:
        return None

    return json.dumps(sanitized, ensure_ascii=False)


def _resolve_passkey_rp_id(host: str | None = None) -> str:
    """Determine the relying party ID."""
    candidate = settings.webauthn_rp_id
    rp_host = host.split(":", 1)[0] if host else None

    if not rp_host:
        return candidate

    if candidate in _DEFAULT_RP_ID_SENTINELS and rp_host not in _DEFAULT_RP_ID_SENTINELS:
        return rp_host

    return candidate


def _resolve_passkey_origin(host: str | None = None, scheme: str = "https") -> str:
    """Determine the expected origin for WebAuthn operations."""
    candidate = settings.webauthn_origin.rstrip("/")
    if not host:
        return candidate

    derived = f"{scheme}://{host}".rstrip("/")

    if candidate in _DEFAULT_ORIGIN_SENTINELS and derived not in _DEFAULT_ORIGIN_SENTINELS:
        return derived

    return candidate


__all__ = [
    "passkey_service",
    "passkey_repo",
    "_extract_passkey_credential_payload",
    "_gather_passkey_payload_keys",
    "_extract_passkey_client_data_details",
    "_build_passkey_trace_payload",
    "_resolve_passkey_rp_id",
    "_resolve_passkey_origin",
]
