"""管理 JSON API — ロール CRUD (`/api/admin/roles`)."""
from __future__ import annotations

from flask import jsonify, request

from ..bootstrap.extensions import db
from shared.infrastructure.models.user import Role, Permission
from . import bp
from .routes import login_or_jwt_required, get_current_user


def _require_user_manage():
    user = get_current_user()
    if user is None or not user.can("user:manage"):
        return jsonify({"error": "forbidden", "message": "user:manage permission required"}), 403
    return None


def _serialize_role(role: Role) -> dict:
    return {
        "id": role.id,
        "name": role.name,
        "permissions": [{"id": p.id, "code": p.code} for p in (role.permissions or [])],
        "userCount": len(role.users) if role.users is not None else 0,
    }


@bp.post("/admin/roles")
@login_or_jwt_required
def api_admin_roles_create():
    """ロールを作成する。"""
    err = _require_user_manage()
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name_required"}), 400
    if Role.query.filter_by(name=name).first():
        return jsonify({"error": "name_exists", "message": "Role name already in use."}), 409

    perm_ids = payload.get("permissionIds") or []
    perms: list[Permission] = []
    if perm_ids:
        perms = Permission.query.filter(Permission.id.in_(perm_ids)).all()

    role = Role(name=name)
    role.permissions = perms
    db.session.add(role)
    db.session.commit()
    return jsonify({"role": _serialize_role(role), "created": True}), 201


@bp.get("/admin/roles/<int:role_id>")
@login_or_jwt_required
def api_admin_role_detail(role_id: int):
    """ロール詳細を返す。"""
    err = _require_user_manage()
    if err:
        return err

    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"role": _serialize_role(role)})


@bp.put("/admin/roles/<int:role_id>")
@login_or_jwt_required
def api_admin_role_update(role_id: int):
    """ロール名と権限を更新する。"""
    err = _require_user_manage()
    if err:
        return err

    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    changed = False

    if "name" in payload:
        new_name = (payload["name"] or "").strip()
        if not new_name:
            return jsonify({"error": "name_required"}), 400
        if new_name != role.name and Role.query.filter_by(name=new_name).first():
            return jsonify({"error": "name_exists", "message": "Role name already in use."}), 409
        role.name = new_name
        changed = True

    if "permissionIds" in payload:
        perm_ids = payload["permissionIds"] or []
        perms = Permission.query.filter(Permission.id.in_(perm_ids)).all() if perm_ids else []
        role.permissions = perms
        changed = True

    if changed:
        db.session.commit()
    return jsonify({"role": _serialize_role(role), "updated": changed})


@bp.delete("/admin/roles/<int:role_id>")
@login_or_jwt_required
def api_admin_role_delete(role_id: int):
    """ロールを削除する。"""
    err = _require_user_manage()
    if err:
        return err

    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({"error": "not_found"}), 404

    db.session.delete(role)
    db.session.commit()
    return jsonify({"result": "deleted", "id": role_id})
