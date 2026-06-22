"""管理 JSON API — サービスアカウント CRUD (`/api/admin/service-accounts`)."""
from __future__ import annotations

from flask import jsonify, request

from ..bootstrap.extensions import db
from core.models.service_account import ServiceAccount
from . import bp
from .routes import login_or_jwt_required, get_current_user


def _require_system_settings():
    user = get_current_user()
    if user is None or not user.can("admin:system-settings"):
        return jsonify({"error": "forbidden", "message": "admin:system-settings permission required"}), 403
    return None


def _serialize_sa(sa: ServiceAccount) -> dict:
    return {
        "id": sa.service_account_id,
        "name": sa.name,
        "description": sa.description,
        "scopes": sa.scopes,
        "isActive": sa.active_flg,
        "createdAt": sa.reg_dttm.isoformat().replace("+00:00", "Z") if sa.reg_dttm else None,
        "updatedAt": sa.mod_dttm.isoformat().replace("+00:00", "Z") if sa.mod_dttm else None,
    }


@bp.get("/admin/service-accounts")
@login_or_jwt_required
def api_admin_service_accounts_list():
    """サービスアカウント一覧を返す。"""
    err = _require_system_settings()
    if err:
        return err

    q = (request.args.get("q") or "").strip()
    query = ServiceAccount.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(ServiceAccount.name.ilike(like), ServiceAccount.description.ilike(like))
        )
    sas = query.order_by(ServiceAccount.service_account_id.asc()).all()
    return jsonify({"serviceAccounts": [_serialize_sa(sa) for sa in sas]})


@bp.post("/admin/service-accounts")
@login_or_jwt_required
def api_admin_service_accounts_create():
    """サービスアカウントを作成する。"""
    err = _require_system_settings()
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name_required"}), 400
    if ServiceAccount.query.filter_by(name=name).first():
        return jsonify({"error": "name_exists", "message": "Service account name already in use."}), 409

    sa = ServiceAccount(
        name=name,
        description=payload.get("description") or None,
        active_flg=bool(payload.get("isActive", True)),
    )
    scopes = payload.get("scopes") or []
    sa.set_scopes(scopes)

    db.session.add(sa)
    db.session.commit()
    return jsonify({"serviceAccount": _serialize_sa(sa), "created": True}), 201


@bp.get("/admin/service-accounts/<int:sa_id>")
@login_or_jwt_required
def api_admin_service_account_detail(sa_id: int):
    """サービスアカウント詳細を返す。"""
    err = _require_system_settings()
    if err:
        return err

    sa = db.session.get(ServiceAccount, sa_id)
    if not sa:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"serviceAccount": _serialize_sa(sa)})


@bp.put("/admin/service-accounts/<int:sa_id>")
@login_or_jwt_required
def api_admin_service_account_update(sa_id: int):
    """サービスアカウントを更新する。"""
    err = _require_system_settings()
    if err:
        return err

    sa = db.session.get(ServiceAccount, sa_id)
    if not sa:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    changed = False

    if "name" in payload:
        new_name = (payload["name"] or "").strip()
        if not new_name:
            return jsonify({"error": "name_required"}), 400
        if new_name != sa.name and ServiceAccount.query.filter_by(name=new_name).first():
            return jsonify({"error": "name_exists", "message": "Service account name already in use."}), 409
        sa.name = new_name
        changed = True

    if "description" in payload:
        sa.description = payload["description"] or None
        changed = True

    if "scopes" in payload:
        sa.set_scopes(payload["scopes"] or [])
        changed = True

    if "isActive" in payload:
        sa.active_flg = bool(payload["isActive"])
        changed = True

    if changed:
        db.session.commit()
    return jsonify({"serviceAccount": _serialize_sa(sa), "updated": changed})


@bp.delete("/admin/service-accounts/<int:sa_id>")
@login_or_jwt_required
def api_admin_service_account_delete(sa_id: int):
    """サービスアカウントを削除する。"""
    err = _require_system_settings()
    if err:
        return err

    sa = db.session.get(ServiceAccount, sa_id)
    if not sa:
        return jsonify({"error": "not_found"}), 404

    db.session.delete(sa)
    db.session.commit()
    return jsonify({"result": "deleted", "id": sa_id})
