"""
バージョン情報API
"""
from flask import jsonify
from . import bp
from .health import skip_auth
from core.version import get_version_info, get_version_string

@bp.route('/version', methods=['GET'])
@skip_auth
def version():
    """バージョン情報を返す"""
    try:
        version_info = get_version_info()
        return jsonify({
            "ok": True,
            "version": get_version_string(),
            "details": version_info
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "version": "unknown"
        }), 500
