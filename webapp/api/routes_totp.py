from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Callable

import pyotp
from flask import jsonify, request

from features.totp.application.dto import (
    TOTPCreateInput,
    TOTPImportItem,
    TOTPImportPayload,
    TOTPUpdateInput,
)
from features.totp.application.use_cases import (
    TOTPCreateUseCase,
    TOTPDeleteUseCase,
    TOTPExportUseCase,
    TOTPImportUseCase,
    TOTPListUseCase,
    TOTPUpdateUseCase,
)
from features.totp.domain.exceptions import (
    TOTPConflictError,
    TOTPNotFoundError,
    TOTPValidationError,
)
from features.totp.domain.parser import parse_otpauth_uri
from features.totp.infrastructure.repositories import TOTPCredentialRepository

from . import bp
from .openapi import json_request_body
from .routes import get_current_user, login_or_jwt_required


_HASH_DIGESTS: dict[str, Callable[[], "hashlib._Hash"]] = {
    "sha1": hashlib.sha1,
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
}


def _ensure_totp_permission(user, perm_code: str):
    if user is None:
        return False
    try:
        can_method = user.can
    except AttributeError:
        return False
    return bool(can_method(perm_code))


def _resolve_digest(name: str | None) -> Callable[[], "hashlib._Hash"]:
    if not isinstance(name, str):
        return hashlib.sha1
    normalized = name.strip().lower()
    return _HASH_DIGESTS.get(normalized, hashlib.sha1)


def _serialize_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_totp_uri(entity):
    digest = _resolve_digest(entity.algorithm)
    totp = pyotp.TOTP(
        entity.secret,
        digits=entity.digits,
        interval=entity.period,
        digest=digest,
    )
    return totp.provisioning_uri(name=entity.account, issuer_name=entity.issuer)


def _generate_totp_preview(entity):
    digest = _resolve_digest(entity.algorithm)
    totp = pyotp.TOTP(
        entity.secret,
        digits=entity.digits,
        interval=entity.period,
        digest=digest,
    )
    otp = totp.now()
    remaining = entity.period - int(time.time()) % entity.period
    if remaining <= 0:
        remaining = entity.period
    return otp, remaining


def _serialize_totp_entity(entity, preview=None):
    otp = None
    remaining = None
    if preview is None:
        otp, remaining = _generate_totp_preview(entity)
    else:
        otp, remaining = preview
    return {
        "id": entity.id,
        "account": entity.account,
        "issuer": entity.issuer,
        "secret": entity.secret,
        "description": entity.description,
        "algorithm": entity.algorithm,
        "digits": entity.digits,
        "period": entity.period,
        "created_at": _serialize_datetime(entity.created_at),
        "updated_at": _serialize_datetime(entity.updated_at),
        "otp": otp,
        "remaining_seconds": remaining,
        "otpauth_uri": _build_totp_uri(entity),
    }


def _coerce_optional_int(value, field):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:  # noqa: PERF203
        raise TOTPValidationError(f"{field} は数値で指定してください", field=field) from exc


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _resolve_totp_payload(payload: dict):
    resolved: dict = {}
    otpauth_uri = (payload or {}).get("otpauth_uri")
    if otpauth_uri:
        parsed = parse_otpauth_uri(otpauth_uri)
        resolved.update(
            {
                "account": parsed.account,
                "issuer": parsed.issuer,
                "secret": parsed.secret,
                "description": parsed.description,
                "algorithm": parsed.algorithm,
                "digits": parsed.digits,
                "period": parsed.period,
            }
        )
    for key in ("account", "issuer", "secret", "description", "algorithm"):
        value = payload.get(key)
        if value not in (None, ""):
            resolved[key] = value
    digits_value = _coerce_optional_int(payload.get("digits"), "digits")
    if digits_value is not None:
        resolved["digits"] = digits_value
    period_value = _coerce_optional_int(payload.get("period"), "period")
    if period_value is not None:
        resolved["period"] = period_value
    return resolved


@bp.get("/totp")
@login_or_jwt_required
def api_totp_list():
    user = get_current_user()
    if not _ensure_totp_permission(user, "totp:view"):
        return jsonify({"error": "forbidden"}), 403

    use_case = TOTPListUseCase()
    pairs = use_case.execute(user_id=user.id)
    items = [
        _serialize_totp_entity(entity, (preview.otp, preview.remaining_seconds))
        for entity, preview in pairs
    ]
    return jsonify({"items": items})


@bp.post("/totp")
@login_or_jwt_required
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Create a new TOTP credential for the current tenant.",
        schema={
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "description": "Label identifying the account for the OTP secret.",
                },
                "issuer": {
                    "type": "string",
                    "description": "Issuer string shown in authenticator apps.",
                },
                "secret": {
                    "type": "string",
                    "description": "Base32 encoded shared secret.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional description visible to administrators.",
                },
                "digits": {
                    "type": "integer",
                    "description": "OTP code length.",
                    "default": 6,
                },
                "period": {
                    "type": "integer",
                    "description": "Time step in seconds for code rotation.",
                    "default": 30,
                },
                "algorithm": {
                    "type": "string",
                    "description": "Hash algorithm used for the OTP (e.g. SHA1).",
                    "default": "SHA1",
                },
                "otpauth_uri": {
                    "type": "string",
                    "description": "Full otpauth URI to parse all fields at once.",
                },
            },
            "required": ["account", "issuer", "secret"],
            "additionalProperties": False,
        },
        example={
            "account": "svc@example.com",
            "issuer": "nolumia",
            "secret": "JBSWY3DPEHPK3PXP",
            "digits": 6,
            "period": 30,
        },
    ),
)
def api_totp_create():
    user = get_current_user()
    if not _ensure_totp_permission(user, "totp:write"):
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    resolved = _resolve_totp_payload(payload)

    try:
        create_kwargs = {
            "account": resolved.get("account", ""),
            "issuer": resolved.get("issuer", ""),
            "secret": resolved.get("secret", ""),
            "description": resolved.get("description"),
            "algorithm": resolved.get("algorithm", "SHA1"),
            "digits": resolved.get("digits", 6),
            "period": resolved.get("period", 30),
        }
        input_dto = TOTPCreateInput(user_id=user.id, **create_kwargs)
        entity = TOTPCreateUseCase().execute(input_dto)
    except TOTPValidationError as exc:
        response = {"error": "validation_error", "message": str(exc)}
        if exc.field:
            response["field"] = exc.field
        return jsonify(response), 400
    except TOTPConflictError as exc:
        return jsonify({"error": "conflict", "message": str(exc)}), 409

    serialized = _serialize_totp_entity(entity)
    return jsonify({"totp": serialized, "item": serialized}), 201


@bp.put("/totp/<int:credential_id>")
@login_or_jwt_required
@bp.doc(
    methods=["PUT"],
    requestBody=json_request_body(
        "Update an existing TOTP credential.",
        schema={
            "type": "object",
            "properties": {
                "account": {"type": "string"},
                "issuer": {"type": "string"},
                "secret": {"type": "string"},
                "description": {"type": "string"},
                "digits": {"type": "integer"},
                "period": {"type": "integer"},
                "algorithm": {"type": "string"},
                "otpauth_uri": {"type": "string"},
                "disabled": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        example={"account": "svc@example.com", "description": "Primary account"},
    ),
)
def api_totp_update(credential_id: int):
    user = get_current_user()
    if not _ensure_totp_permission(user, "totp:write"):
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    resolved = _resolve_totp_payload(payload)
    disabled_value = payload.get("disabled")
    if disabled_value is not None:
        resolved["disabled"] = _coerce_bool(disabled_value)

    repository = TOTPCredentialRepository()
    existing = repository.find_by_id(credential_id, user_id=user.id)
    if not existing:
        return jsonify({"error": "not_found"}), 404

    resolved.pop("disabled", None)

    update_kwargs = {
        "id": credential_id,
        "user_id": user.id,
        "account": resolved.get("account", existing.account),
        "issuer": resolved.get("issuer", existing.issuer),
        "description": resolved.get("description", existing.description),
        "algorithm": resolved.get("algorithm", existing.algorithm),
        "digits": resolved.get("digits", existing.digits),
        "period": resolved.get("period", existing.period),
    }
    if "secret" in resolved:
        update_kwargs["secret"] = resolved["secret"]

    try:
        input_dto = TOTPUpdateInput(**update_kwargs)
        entity = TOTPUpdateUseCase().execute(input_dto)
    except TOTPValidationError as exc:
        response = {"error": "validation_error", "message": str(exc)}
        if exc.field:
            response["field"] = exc.field
        return jsonify(response), 400
    except TOTPNotFoundError:
        return jsonify({"error": "not_found"}), 404

    serialized = _serialize_totp_entity(entity)
    return jsonify({"totp": serialized, "item": serialized})


@bp.delete("/totp/<int:credential_id>")
@login_or_jwt_required
def api_totp_delete(credential_id: int):
    user = get_current_user()
    if not _ensure_totp_permission(user, "totp:write"):
        return jsonify({"error": "forbidden"}), 403

    try:
        TOTPDeleteUseCase().execute(credential_id, user_id=user.id)
        return jsonify({"result": "deleted"})
    except TOTPNotFoundError:
        return jsonify({"error": "not_found"}), 404


@bp.get("/totp/export")
@login_or_jwt_required
def api_totp_export():
    user = get_current_user()
    if not _ensure_totp_permission(user, "totp:view"):
        return jsonify({"error": "forbidden"}), 403

    exported = TOTPExportUseCase().execute(user_id=user.id)
    return jsonify(exported)


@bp.post("/totp/import")
@login_or_jwt_required
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Bulk import TOTP credentials from exported metadata.",
        schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "account": {"type": "string"},
                            "issuer": {"type": "string"},
                            "secret": {"type": "string"},
                            "description": {"type": "string"},
                            "algorithm": {"type": "string"},
                            "digits": {"type": "integer"},
                            "period": {"type": "integer"},
                            "created_at": {
                                "type": "string",
                                "format": "date-time",
                            },
                        },
                        "required": ["account", "issuer", "secret"],
                        "additionalProperties": False,
                    },
                    "description": "List of secrets to import.",
                },
                "force": {
                    "type": "boolean",
                    "description": "Overwrite existing entries when true.",
                },
            },
            "required": ["items"],
            "additionalProperties": False,
        },
        example={
            "items": [
                {
                    "account": "svc@example.com",
                    "issuer": "nolumia",
                    "secret": "JBSWY3DPEHPK3PXP",
                    "digits": 6,
                    "period": 30,
                }
            ],
            "force": False,
        },
    ),
)
def api_totp_import():
    user = get_current_user()
    if not _ensure_totp_permission(user, "totp:write"):
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    items_payload = payload.get("items") or []
    items: list[TOTPImportItem] = []
    try:
        for item in items_payload:
            digits = _coerce_optional_int(item.get("digits"), "digits")
            if digits is None:
                digits = 6
            period = _coerce_optional_int(item.get("period"), "period")
            if period is None:
                period = 30
            items.append(
                TOTPImportItem(
                    account=item.get("account", ""),
                    issuer=item.get("issuer", ""),
                    secret=item.get("secret", ""),
                    description=item.get("description"),
                    created_at=item.get("created_at"),
                    algorithm=item.get("algorithm", "SHA1"),
                    digits=digits,
                    period=period,
                )
            )
        force_flag = _coerce_bool(payload.get("force"))
        result = TOTPImportUseCase().execute(
            TOTPImportPayload(items=items, user_id=user.id, force=force_flag)
        )
    except TOTPValidationError as exc:
        response = {"error": "validation_error", "message": str(exc)}
        if exc.field:
            response["field"] = exc.field
        return jsonify(response), 400

    if result["conflicts"] and not force_flag:
        return jsonify(result), 409

    return jsonify(result)
