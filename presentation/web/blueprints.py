"""全 Blueprint / ルートモジュールの配線.

``create_app()`` に集中していた Blueprint 登録を切り出す。各 Blueprint の import は
循環 import を避けるため関数内で遅延的に行う。OpenAPI 仕様の後処理
（プレフィックス除去・成功レスポンス補完）は API Blueprint 登録との順序依存が
あるため、本関数内で適切な位置に配置する。
"""

from __future__ import annotations

from flask import Flask

from .extensions import api as smorest_api
from .openapi_spec import ensure_openapi_success_responses, strip_openapi_path_prefix


def register_blueprints(app: Flask, *, testing_mode: bool) -> None:
    """アプリへ全 Blueprint と付随する URL ルールを登録する。"""

    from .auth import bp as auth_bp
    from .auth.routes import picker as picker_view  # 最初にインポート
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.add_url_rule("/picker/<int:account_id>", view_func=picker_view, endpoint="picker")

    from .dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    from .admin.routes import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from bounded_contexts.photonest.presentation.photo_view import bp as photo_view_bp
    app.register_blueprint(photo_view_bp)

    from .api import bp as api_bp
    api_url_prefix = "/api"
    smorest_api.register_blueprint(api_bp, url_prefix=api_url_prefix)

    # CDN admin API
    from webapp.api.admin.cdn import bp as cdn_admin_bp
    smorest_api.register_blueprint(cdn_admin_bp)

    # Blob admin API
    from webapp.api.admin.blob import bp as blob_admin_bp
    smorest_api.register_blueprint(blob_admin_bp)

    strip_openapi_path_prefix(smorest_api.spec, api_url_prefix)

    from presentation.web.api import routes as api_routes

    app.add_url_rule(
        "/media/thumbs/<path:rel>",
        endpoint="media_thumb_fallback",
        view_func=api_routes.api_download_thumb_fallback,
        methods=["GET", "HEAD"],
    )
    app.add_url_rule(
        "/media/playback/<path:rel>",
        endpoint="media_playback_fallback",
        view_func=api_routes.api_download_playback_fallback,
        methods=["GET", "HEAD"],
    )
    app.add_url_rule(
        "/media/originals/<path:rel>",
        endpoint="media_original_fallback",
        view_func=api_routes.api_download_original_fallback,
        methods=["GET", "HEAD"],
    )
    ensure_openapi_success_responses(smorest_api.spec)

    # 認証なしの健康チェック用Blueprint
    from .health import health_bp
    app.register_blueprint(health_bp, url_prefix="/health")

    # デバッグ用Blueprint（開発環境のみ）
    if app.debug or testing_mode:
        from .debug_routes import debug_bp
        app.register_blueprint(debug_bp, url_prefix="/debug")

    from bounded_contexts.wiki.presentation.wiki import bp as wiki_bp
    app.register_blueprint(wiki_bp, url_prefix="/wiki")

    from bounded_contexts.totp.presentation import bp as totp_bp
    app.register_blueprint(totp_bp, url_prefix="/totp")

    from bounded_contexts.certs.presentation.ui import certs_ui_bp
    app.register_blueprint(certs_ui_bp, url_prefix="/certs")

    from bounded_contexts.certs.presentation.api import certs_api_bp
    app.register_blueprint(certs_api_bp, url_prefix="/api")

    # Local Import状態管理API
    from bounded_contexts.photonest.presentation.local_import_status_api import bp as local_import_status_bp
    app.register_blueprint(local_import_status_bp)
