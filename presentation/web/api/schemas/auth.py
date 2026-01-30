"""Marshmallow schemas for authentication endpoints."""

from __future__ import annotations

from typing import Any

from marshmallow import Schema, ValidationError, fields, validate


class ScopeField(fields.Field):
    """Scope field that accepts either a string or a list of strings."""

    def __init__(self, *args, **kwargs):
        metadata = kwargs.setdefault("metadata", {})
        metadata.setdefault(
            "oneOf",
            [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
            ],
        )
        super().__init__(*args, **kwargs)

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs) -> list[str]:  # type: ignore[override]
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [item for item in value.split() if item]
        if isinstance(value, (list, tuple, set)):
            normalized: list[str] = []
            for item in value:
                if isinstance(item, str):
                    token = item.strip()
                    if token:
                        normalized.append(token)
                else:
                    raise ValidationError("Scope entries must be strings.")
            return normalized
        raise ValidationError("Invalid scope format. Use a space separated string or list of strings.")

    @property
    def _jsonschema_type_mapping(self) -> dict[str, Any]:  # pragma: no cover - schema metadata
        return {
            "oneOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
            ]
        }


class FlexibleIntegerField(fields.Field):
    """Integer field that silently ignores invalid values (to match legacy behaviour)."""

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs) -> int | None:  # type: ignore[override]
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class LoginRequestSchema(Schema):
    email = fields.Email(required=True, metadata={"description": "ユーザーのメールアドレス"})
    password = fields.String(
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "ユーザーのパスワード"},
    )
    token = fields.String(
        load_default=None,
        metadata={"description": "TOTPを利用する場合のワンタイムパスワード"},
    )
    scope = ScopeField(
        load_default=list,
        metadata={"description": "要求するスコープ。スペース区切りまたは配列で指定可能。"},
    )
    active_role_id = FlexibleIntegerField(
        load_default=None,
        data_key="active_role_id",
        metadata={"description": "ログイン後に有効化するロールID"},
    )
    next_url = fields.String(
        load_default=None,
        data_key="next",
        metadata={"description": "ログイン後にリダイレクトするURL"},
    )


class LoginResponseSchema(Schema):
    access_token = fields.String(required=True)
    refresh_token = fields.String(required=True)
    token_type = fields.String(required=True, metadata={"description": "アクセストークンの種別"})
    requires_role_selection = fields.Boolean(required=True)
    redirect_url = fields.String(required=True)
    scope = fields.String(required=True)
    available_scopes = fields.List(fields.String(), required=True)


class RefreshRequestSchema(Schema):
    refresh_token = fields.String(
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "有効なリフレッシュトークン"},
        data_key="refresh_token",
    )


class RefreshResponseSchema(Schema):
    access_token = fields.String(required=True)
    refresh_token = fields.String(required=True)
    token_type = fields.String(required=True, metadata={"description": "アクセストークンの種別"})
    scope = fields.String(required=True)


class LogoutResponseSchema(Schema):
    result = fields.String(required=True)


class ServiceAccountTokenRequestSchema(Schema):
    grant_type = fields.String(
        required=True,
        data_key="grant_type",
        metadata={"description": "OAuth 2.0 grant type. Only JWT bearer is supported."},
    )
    assertion = fields.String(
        required=True,
        metadata={"description": "Base64URL encoded client assertion (JWS compact)."},
    )


class ServiceAccountTokenResponseSchema(Schema):
    access_token = fields.String(required=True)
    token_type = fields.String(required=True)
    expires_in = fields.Integer(required=True)
    scope = fields.String(required=True)
