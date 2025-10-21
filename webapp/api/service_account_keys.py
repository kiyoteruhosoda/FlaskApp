"""REST endpoints for managing service account API keys."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import jsonify, request
from flask_login import current_user

from . import bp
from .openapi import json_request_body
from .routes import login_or_jwt_required
from webapp.services.service_account_api_key_service import (
    ServiceAccountApiKeyNotFoundError,
    ServiceAccountApiKeyService,
    ServiceAccountApiKeyValidationError,
)


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if raw in (None, ""):
        return None
    if not isinstance(raw, str):
        raise ValueError("expires_at must be a string in ISO 8601 format")

    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_actor_identifier() -> str:
    """現在の主体を表す文字列表現を取得する。"""

    subject_id = getattr(current_user, "subject_id", None)
    if isinstance(subject_id, str) and subject_id.strip():
        return subject_id.strip()

    if hasattr(current_user, "get_id"):
        identifier = current_user.get_id()
        if isinstance(identifier, str) and identifier.strip():
            return identifier.strip()

    display_name = getattr(current_user, "display_name", None)
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()

    return "unknown"


def _has_manage_permission() -> bool:
    if not current_user.is_authenticated:
        return False
    return current_user.can("api_key:manage")


def _has_read_permission() -> bool:
    if not current_user.is_authenticated:
        return False
    if _has_manage_permission():
        return True
    return current_user.can("api_key:read")


@bp.route("/service_accounts/<int:account_id>/keys", methods=["GET"])
@login_or_jwt_required
def list_service_account_keys(account_id: int):
    if not _has_read_permission():
        return jsonify({"error": "forbidden"}), 403

    try:
        keys = ServiceAccountApiKeyService.list_keys(account_id)
    except ServiceAccountApiKeyValidationError as exc:
        return jsonify({"error": exc.message}), 400
    except ServiceAccountApiKeyNotFoundError:
        return jsonify({"error": "not_found"}), 404

    return jsonify({"items": [key.as_dict() for key in keys]})


@bp.route("/service_accounts/<int:account_id>/keys", methods=["POST"])
@login_or_jwt_required
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Create a new API key for the specified service account.",
        required=False,
        schema={
            "type": "object",
            "properties": {
                "expires_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO 8601 timestamp for when the key should expire.",
                },
                "scopes": {
                    "type": "string",
                    "description": "Space separated list of permission scopes to assign to the key.",
                },
            },
            "additionalProperties": False,
        },
        example={"scopes": "media:view media:tag-manage", "expires_at": "2024-12-31T15:00:00Z"},
    ),
)
def create_service_account_key(account_id: int):
    if not _has_manage_permission():
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    expires_at_raw = payload.get("expires_at")
    try:
        expires_at = _parse_iso_datetime(expires_at_raw)
    except ValueError as exc:
        return jsonify({"error": str(exc), "field": "expires_at"}), 400

    try:
        record, api_key_value = ServiceAccountApiKeyService.create_key(
            account_id,
            scopes=payload.get("scopes", ""),
            expires_at=expires_at,
            created_by=_resolve_actor_identifier(),
        )
    except ServiceAccountApiKeyValidationError as exc:
        response = {"error": exc.message}
        if exc.field:
            response["field"] = exc.field
        return jsonify(response), 400
    except ServiceAccountApiKeyNotFoundError:
        return jsonify({"error": "not_found"}), 404

    result = record.as_dict()
    result["api_key"] = api_key_value
    return jsonify({"item": result}), 201


@bp.route(
    "/service_accounts/<int:account_id>/keys/<int:key_id>/revoke",
    methods=["POST"],
)
@login_or_jwt_required
def revoke_service_account_key(account_id: int, key_id: int):
    if not _has_manage_permission():
        return jsonify({"error": "forbidden"}), 403

    try:
        key = ServiceAccountApiKeyService.revoke_key(
            account_id, key_id, actor=_resolve_actor_identifier()
        )
    except ServiceAccountApiKeyNotFoundError:
        return jsonify({"error": "not_found"}), 404
    except ServiceAccountApiKeyValidationError as exc:
        return jsonify({"error": exc.message}), 400

    return jsonify({"item": key.as_dict()})


@bp.route("/service_accounts/<int:account_id>/keys/logs", methods=["GET"])
@login_or_jwt_required
def list_service_account_key_logs(account_id: int):
    if not _has_read_permission():
        return jsonify({"error": "forbidden"}), 403

    key_id = request.args.get("key_id", type=int)
    limit = request.args.get("limit", type=int)

    try:
        logs = ServiceAccountApiKeyService.list_logs(
            account_id, key_id=key_id, limit=limit
        )
    except ServiceAccountApiKeyValidationError as exc:
        return jsonify({"error": exc.message}), 400
    except ServiceAccountApiKeyNotFoundError:
        return jsonify({"error": "not_found"}), 404

    return jsonify({"items": [log.as_dict() for log in logs]})
