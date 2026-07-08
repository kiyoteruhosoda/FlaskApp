from .blueprint import AuthEnforcedBlueprint

bp = AuthEnforcedBlueprint("api", __name__, description="nolumia API")

# NOTE: 以下のモジュールは FastAPI（presentation/fastapi/routers/）に移植済みのため
#       Flask Blueprint からの登録を除外した（T11 Phase3 後続）。
#       FastAPI が /api/* を先に処理する Strangler Fig 構成のため、
#       Flask 側に重複登録しても到達しない。cdn/blob admin API のみ Flask 側に残す。

# CDN・Blob admin API（FastAPI 未移植のため Flask 側で引き続き処理）
# これらは blueprints.py で smorest_api に直接登録される。

from .picker_session import bp as picker_session_bp

bp.register_blueprint(picker_session_bp)
