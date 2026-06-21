"""OpenAPI / Swagger UI のアプリ設定とランタイム登録.

``create_app()`` に散在していた OpenAPI 関連のセットアップを集約する。責務は次の2つ:

- ``apply_openapi_config_defaults``: ``smorest_api.init_app`` の前に必要な
  ``API_*`` / ``OPENAPI_*`` 既定値を ``app.config`` に設定する。
- ``register_openapi_runtime``: ``init_app`` 後にセキュリティスキームを登録し、
  リクエストごとに ``servers`` URL を現在のホストへ追従させるフックを登録する。
"""

from __future__ import annotations

from flask import Flask

from core.settings import settings
from webapp.auth.api_key_auth import API_KEY_SECURITY_SCHEME_NAME

from .extensions import api as smorest_api
from .openapi_spec import calculate_openapi_server_urls, normalize_openapi_prefix


def apply_openapi_config_defaults(app: Flask) -> None:
    """smorest 初期化前に OpenAPI / Swagger UI の既定設定を適用する。"""

    app.config.setdefault("API_TITLE", "nolumia API")
    app.config.setdefault("API_VERSION", "1.0.0")
    app.config.setdefault("OPENAPI_VERSION", "3.0.3")
    app.config.setdefault("OPENAPI_URL_PREFIX", "/api")
    app.config.setdefault("OPENAPI_JSON_PATH", "openapi.json")
    app.config.setdefault("OPENAPI_SWAGGER_UI_PATH", "docs")
    app.config.setdefault("OPENAPI_OVERVIEW_PATH", "overview")
    app.config.setdefault("OPENAPI_OVERVIEW_TITLE", "API一覧")
    app.config.setdefault(
        "OPENAPI_SWAGGER_UI_URL",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
    )
    api_spec_options = app.config.setdefault("API_SPEC_OPTIONS", {})
    info_options = api_spec_options.setdefault("info", {})
    info_options.setdefault(
        "description",
        "Nolumia API provides authentication, media management, and Google Photos integration endpoints.",
    )
    swagger_ui_config = app.config.setdefault("OPENAPI_SWAGGER_UI_CONFIG", {})
    swagger_ui_config.setdefault("persistAuthorization", True)


def register_openapi_runtime(app: Flask) -> None:
    """セキュリティスキームと servers URL 追従フックを登録する。"""

    with app.app_context():
        smorest_api.spec.components.security_scheme(
            "JWTBearerAuth",
            {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Standard JWT bearer authentication. Send `Authorization: Bearer <token>`.",
            },
        )
        smorest_api.spec.components.security_scheme(
            API_KEY_SECURITY_SCHEME_NAME,
            {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": (
                    "Send the service account API key using the Authorization "
                    "header with the `ApiKey <token>` format."
                ),
            },
        )
        smorest_api.spec.options.setdefault("security", [{"JWTBearerAuth": []}])

        configured_servers = (settings.api_spec_options or {}).get("servers")

    @app.before_request
    def _refresh_openapi_server_urls():
        if configured_servers:
            return
        spec = getattr(smorest_api, "spec", None)
        if spec is None:
            return
        prefix = normalize_openapi_prefix(settings.openapi_url_prefix)
        server_urls = calculate_openapi_server_urls(prefix)
        spec.options["servers"] = [{"url": url} for url in server_urls]
