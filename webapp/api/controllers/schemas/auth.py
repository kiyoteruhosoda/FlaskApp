"""Authentication schemas for API endpoints."""

from marshmallow import Schema, fields, validate


class LoginRequestSchema(Schema):
    """ログインリクエストスキーマ."""
    username = fields.String(required=True, validate=validate.Length(min=1))
    password = fields.String(required=True, validate=validate.Length(min=1))
    totp_code = fields.String(allow_none=True, validate=validate.Length(equal=6))
    scope = fields.List(fields.String())


class LoginResponseSchema(Schema):
    """ログインレスポンススキーマ."""
    access_token = fields.String(required=True)
    refresh_token = fields.String(required=True)
    expires_in = fields.Integer(required=True)
    token_type = fields.String()
    user = fields.Nested("UserSchema", required=True)


class LogoutResponseSchema(Schema):
    """ログアウトレスポンススキーマ."""
    success = fields.Boolean(required=True)
    message = fields.String(required=True)


class RefreshRequestSchema(Schema):
    """トークンリフレッシュリクエストスキーマ."""
    refresh_token = fields.String(required=True)


class RefreshResponseSchema(Schema):
    """トークンリフレッシュレスポンススキーマ."""
    access_token = fields.String(required=True)
    refresh_token = fields.String(required=True)
    expires_in = fields.Integer(required=True)
    token_type = fields.String()


class ServiceAccountTokenRequestSchema(Schema):
    """サービスアカウントトークンリクエストスキーマ."""
    grant_type = fields.String(required=True)
    assertion = fields.String(required=True)


class ServiceAccountTokenResponseSchema(Schema):
    """サービスアカウントトークンレスポンススキーマ."""
    access_token = fields.String(required=True)
    token_type = fields.String()
    expires_in = fields.Integer(required=True)
    scope = fields.String()


class UserSchema(Schema):
    """ユーザー情報スキーマ."""
    id = fields.Integer(required=True)
    username = fields.String(required=True)
    display_name = fields.String()
    roles = fields.List(fields.String())