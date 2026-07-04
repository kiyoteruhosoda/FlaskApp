"""管理 JSON API — 権限 CRUD (`/api/admin/permissions`)."""
from __future__ import annotations

from flask import jsonify, request

from ..bootstrap.extensions import db
from shared.infrastructure.models.user import Permission
from . import bp
from .routes import login_or_jwt_required, get_current_user


def _require_permission_manage():
    # 権限マスタの閲覧・編集はユビキタス言語どおり permission:manage で認可する。
    # （ロール編集画面での権限一覧取得にも使われる）
    user = get_current_user()
    if user is None or not user.can("permission:manage"):
        return jsonify({"error": "forbidden", "message": "permission:manage permission required"}), 403
    return None


def _serialize_permission(perm: Permission) -> dict:
    return {
        "id": perm.id,
        "code": perm.code,
        "detail": perm.detail,
        "roleCount": len(perm.roles) if perm.roles is not None else 0,
    }


@bp.get("/admin/permissions")
@login_or_jwt_required
def api_admin_permissions_list():
    """権限一覧を返す。"""
    err = _require_permission_manage()
    if err:
        return err

    q = (request.args.get("q") or "").strip()
    query = Permission.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Permission.code.ilike(like), Permission.detail.ilike(like))
        )
    perms = query.order_by(Permission.code.asc()).all()
    return jsonify({"permissions": [_serialize_permission(p) for p in perms]})


@bp.post("/admin/permissions")
@login_or_jwt_required
def api_admin_permissions_create():
    """権限を作成する。"""
    err = _require_permission_manage()
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"error": "code_required"}), 400
    if Permission.query.filter_by(code=code).first():
        return jsonify({"error": "code_exists", "message": "Permission code already in use."}), 409

    perm = Permission(code=code, detail=payload.get("detail") or None)
    db.session.add(perm)
    db.session.commit()
    return jsonify({"permission": _serialize_permission(perm), "created": True}), 201


@bp.get("/admin/permissions/<int:perm_id>")
@login_or_jwt_required
def api_admin_permission_detail(perm_id: int):
    """権限詳細を返す。"""
    err = _require_permission_manage()
    if err:
        return err

    perm = db.session.get(Permission, perm_id)
    if not perm:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"permission": _serialize_permission(perm)})


@bp.put("/admin/permissions/<int:perm_id>")
@login_or_jwt_required
def api_admin_permission_update(perm_id: int):
    """権限を更新する。"""
    err = _require_permission_manage()
    if err:
        return err

    perm = db.session.get(Permission, perm_id)
    if not perm:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    changed = False

    if "code" in payload:
        new_code = (payload["code"] or "").strip()
        if not new_code:
            return jsonify({"error": "code_required"}), 400
        if new_code != perm.code and Permission.query.filter_by(code=new_code).first():
            return jsonify({"error": "code_exists", "message": "Permission code already in use."}), 409
        perm.code = new_code
        changed = True

    if "detail" in payload:
        perm.detail = payload["detail"] or None
        changed = True

    if changed:
        db.session.commit()
    return jsonify({"permission": _serialize_permission(perm), "updated": changed})


@bp.delete("/admin/permissions/<int:perm_id>")
@login_or_jwt_required
def api_admin_permission_delete(perm_id: int):
    """権限を削除する。"""
    err = _require_permission_manage()
    if err:
        return err

    perm = db.session.get(Permission, perm_id)
    if not perm:
        return jsonify({"error": "not_found"}), 404

    db.session.delete(perm)
    db.session.commit()
    return jsonify({"result": "deleted", "id": perm_id})
