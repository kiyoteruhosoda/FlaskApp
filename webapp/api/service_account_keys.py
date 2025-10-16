"""REST endpoints for managing service account API keys."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import jsonify, request
from flask_login import current_user, login_required

from . import bp
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


def _ensure_permission():
    if not current_user.is_authenticated:
        return False
    return current_user.can("service_account_api:manage")


@bp.route("/service_accounts/<int:account_id>/keys", methods=["GET"])
@login_required
def list_service_account_keys(account_id: int):
    if not _ensure_permission():
        return jsonify({"error": "forbidden"}), 403

    try:
        keys = ServiceAccountApiKeyService.list_keys(account_id)
    except ServiceAccountApiKeyValidationError as exc:
        return jsonify({"error": exc.message}), 400
    except ServiceAccountApiKeyNotFoundError:
        return jsonify({"error": "not_found"}), 404

    return jsonify({"items": [key.as_dict() for key in keys]})


@bp.route("/service_accounts/<int:account_id>/keys", methods=["POST"])
@login_required
def create_service_account_key(account_id: int):
    if not _ensure_permission():
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
            created_by=current_user.email,
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
@login_required
def revoke_service_account_key(account_id: int, key_id: int):
    if not _ensure_permission():
        return jsonify({"error": "forbidden"}), 403

    try:
        key = ServiceAccountApiKeyService.revoke_key(
            account_id, key_id, actor=current_user.email
        )
    except ServiceAccountApiKeyNotFoundError:
        return jsonify({"error": "not_found"}), 404
    except ServiceAccountApiKeyValidationError as exc:
        return jsonify({"error": exc.message}), 400

    return jsonify({"item": key.as_dict()})


@bp.route("/service_accounts/<int:account_id>/keys/logs", methods=["GET"])
@login_required
def list_service_account_key_logs(account_id: int):
    if not _ensure_permission():
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
