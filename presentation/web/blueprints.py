"""全 Blueprint / ルートモジュールの配線.

``create_app()`` に集中していた Blueprint 登録を切り出す。各 Blueprint の import は
循環 import を避けるため関数内で遅延的に行う。OpenAPI 仕様の後処理
（プレフィックス除去・成功レスポンス補完）は API Blueprint 登録との順序依存が
あるため、本関数内で適切な位置に配置する。
"""

from __future__ import annotations

from flask import Flask

from .bootstrap.extensions import api as smorest_api
from .openapi.spec import ensure_openapi_success_responses, strip_openapi_path_prefix


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
    from presentation.web.api.admin.cdn import bp as cdn_admin_bp
    smorest_api.register_blueprint(cdn_admin_bp)

    # Blob admin API
    from presentation.web.api.admin.blob import bp as blob_admin_bp
    smorest_api.register_blueprint(blob_admin_bp)

    strip_openapi_path_prefix(smorest_api.spec, api_url_prefix)

    # NOTE: /media/thumbs, /media/playback, /media/originals のフォールバック URL ルールは
    #       FastAPI（presentation/fastapi/routers/media.py）に移植済みのため削除（T11 Phase3）。
    #       FastAPI が先にリクエストを処理する Strangler Fig 構成のため Flask 側は不要。

    ensure_openapi_success_responses(smorest_api.spec)

    # 認証なしの健康チェック用Blueprint
    from .routes.health import health_bp, healthz
    app.register_blueprint(health_bp, url_prefix="/health")
    # /healthz はトップレベルパス（health_bp の url_prefix には乗らない）
    app.add_url_rule("/healthz", endpoint="healthz", view_func=healthz, methods=["GET"])

    # デバッグ用Blueprint（開発環境のみ）
    if app.debug or testing_mode:
        from .routes.debug_routes import debug_bp
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
