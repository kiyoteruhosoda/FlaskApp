"""管理 JSON API — グループ CRUD (`/api/admin/groups`)."""
from __future__ import annotations

from flask import jsonify, request

from ..bootstrap.extensions import db
from shared.infrastructure.models.group import Group, GroupHierarchyError
from shared.infrastructure.models.user import User, Role
from . import bp
from .routes import login_or_jwt_required, get_current_user


def _require_user_manage():
    user = get_current_user()
    if user is None or not user.can("user:manage"):
        return jsonify({"error": "forbidden", "message": "user:manage permission required"}), 403
    return None


def _serialize_group(group: Group) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "parentId": group.parent_id,
        "parentName": group.parent.name if group.parent else None,
        "memberCount": len(group.users) if group.users is not None else 0,
        "childCount": len(group.children) if group.children is not None else 0,
        "roles": [{"id": r.id, "name": r.name} for r in (group.roles or [])],
    }


@bp.get("/admin/groups")
@login_or_jwt_required
def api_admin_groups_list():
    """グループ一覧を返す。"""
    err = _require_user_manage()
    if err:
        return err

    groups = Group.query.order_by(Group.id.asc()).all()
    return jsonify({"groups": [_serialize_group(g) for g in groups]})


@bp.post("/admin/groups")
@login_or_jwt_required
def api_admin_groups_create():
    """グループを作成する。"""
    err = _require_user_manage()
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name_required"}), 400
    if Group.query.filter_by(name=name).first():
        return jsonify({"error": "name_exists", "message": "Group name already in use."}), 409

    group = Group(name=name, description=payload.get("description") or None)

    parent_id = payload.get("parentId")
    if parent_id:
        parent = db.session.get(Group, int(parent_id))
        if not parent:
            return jsonify({"error": "parent_not_found"}), 404
        try:
            group.assign_parent(parent)
        except GroupHierarchyError as e:
            return jsonify({"error": "hierarchy_error", "message": str(e)}), 400

    db.session.add(group)
    db.session.commit()
    return jsonify({"group": _serialize_group(group), "created": True}), 201


@bp.get("/admin/groups/<int:group_id>")
@login_or_jwt_required
def api_admin_group_detail(group_id: int):
    """グループ詳細（メンバー一覧付き）を返す。"""
    err = _require_user_manage()
    if err:
        return err

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "not_found"}), 404

    data = _serialize_group(group)
    data["members"] = [{"id": u.id, "email": u.email, "username": u.username} for u in group.users]
    return jsonify({"group": data})


@bp.put("/admin/groups/<int:group_id>")
@login_or_jwt_required
def api_admin_group_update(group_id: int):
    """グループを更新する。"""
    err = _require_user_manage()
    if err:
        return err

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    changed = False

    if "name" in payload:
        new_name = (payload["name"] or "").strip()
        if not new_name:
            return jsonify({"error": "name_required"}), 400
        if new_name != group.name and Group.query.filter_by(name=new_name).first():
            return jsonify({"error": "name_exists", "message": "Group name already in use."}), 409
        group.name = new_name
        changed = True

    if "description" in payload:
        group.description = payload["description"] or None
        changed = True

    if "parentId" in payload:
        pid = payload["parentId"]
        if pid is None:
            group.parent = None
            changed = True
        else:
            parent = db.session.get(Group, int(pid))
            if not parent:
                return jsonify({"error": "parent_not_found"}), 404
            try:
                group.assign_parent(parent)
                changed = True
            except GroupHierarchyError as e:
                return jsonify({"error": "hierarchy_error", "message": str(e)}), 400

    if "memberIds" in payload:
        member_ids = payload["memberIds"] or []
        members = User.query.filter(User.id.in_(member_ids)).all() if member_ids else []
        group.users = members
        changed = True

    if changed:
        db.session.commit()
    return jsonify({"group": _serialize_group(group), "updated": changed})


@bp.delete("/admin/groups/<int:group_id>")
@login_or_jwt_required
def api_admin_group_delete(group_id: int):
    """グループを削除する。"""
    err = _require_user_manage()
    if err:
        return err

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "not_found"}), 404

    if group.children:
        return jsonify({"error": "has_children", "message": "Remove child groups first."}), 400

    db.session.delete(group)
    db.session.commit()
    return jsonify({"result": "deleted", "id": group_id})


@bp.get("/admin/groups/<int:group_id>/roles")
@login_or_jwt_required
def api_admin_group_roles_get(group_id: int):
    """グループに付与されたロール一覧を返す。"""
    err = _require_user_manage()
    if err:
        return err

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "not_found"}), 404

    return jsonify({
        "groupId": group.id,
        "roles": [{"id": r.id, "name": r.name} for r in (group.roles or [])],
    })


@bp.put("/admin/groups/<int:group_id>/roles")
@login_or_jwt_required
def api_admin_group_roles_update(group_id: int):
    """グループに付与するロールを一括更新する。

    Request body: ``{"roleIds": [1, 2, ...]}``
    """
    err = _require_user_manage()
    if err:
        return err

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    role_ids = payload.get("roleIds") or []
    if role_ids:
        roles = Role.query.filter(Role.id.in_(role_ids)).all()
        if len(roles) != len(set(role_ids)):
            return jsonify({"error": "role_not_found", "message": "One or more roles not found."}), 404
    else:
        roles = []

    group.roles = roles
    db.session.commit()
    return jsonify({
        "groupId": group.id,
        "roles": [{"id": r.id, "name": r.name} for r in group.roles],
        "updated": True,
    })
