from flask import jsonify
from flask_babel import gettext as _

from . import bp


@bp.get('/openapi.json')
def openapi_spec():
    """簡易OpenAPI仕様を返す"""
    spec = {
        "openapi": "3.0.3",
        "info": {"title": f"{_('AppName')} API", "version": "1.0.0"},
        "paths": {
            "/api/login": {
                "post": {
                    "summary": "JWTログイン",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/google/accounts": {
                "get": {
                    "summary": "Googleアカウント一覧",
                    "security": [{"cookieAuth": []}, {"bearerAuth": []}],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/auth/check": {
                "get": {
                    "summary": "JWTまたはCookieでの認証状態チェック",
                    "security": [{"cookieAuth": []}, {"bearerAuth": []}],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
                "cookieAuth": {"type": "apiKey", "in": "cookie", "name": "access_token"},
            }
        },
    }
    return jsonify(spec)
