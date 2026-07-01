"""管理 JSON API — ユーザー管理 (`/api/admin/users`, `/api/admin/roles`)."""
from __future__ import annotations

from flask import jsonify, request
from flask_login import current_user
from marshmallow import ValidationError as MarshmallowValidationError
from marshmallow.validate import Email as EmailValidator

from ..bootstrap.extensions import db
from shared.infrastructure.models.user import User, Role
from . import bp
from .routes import login_or_jwt_required, get_current_user

_email_validator = EmailValidator()


def _require_user_manage():
    """`user:manage` 権限を確認する。なければ 403 を返す。"""
    user = get_current_user()
    if user is None or not user.can("user:manage"):
        return jsonify({"error": "forbidden", "message": "user:manage permission required"}), 403
    return None


def _is_valid_email(email: str) -> bool:
    """ログイン時の ``LoginRequestSchema`` (``fields.Email``) と同じ基準で検証する。"""
    try:
        _email_validator(email)
        return True
    except MarshmallowValidationError:
        return False


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "isActive": user.is_active,
        "hasTOTP": bool(user.totp_secret),
        "createdAt": (
            user.created_at.isoformat().replace("+00:00", "Z") if user.created_at else None
        ),
        "roles": [{"id": r.id, "name": r.name} for r in (user.roles or [])],
    }


def _serialize_role(role: Role) -> dict:
    return {
        "id": role.id,
        "name": role.name,
        "permissions": [p.code for p in (role.permissions or [])],
    }


@bp.get("/admin/users")
@login_or_jwt_required
def api_admin_users_list():
    """ユーザー一覧を返す（`user:manage` 権限必須）。"""
    err = _require_user_manage()
    if err:
        return err

    q = (request.args.get("q") or "").strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(User.email.ilike(like), User.username.ilike(like))
        )
    users = query.order_by(User.id.asc()).all()
    return jsonify({"users": [_serialize_user(u) for u in users]})


@bp.get("/admin/users/<int:user_id>")
@login_or_jwt_required
def api_admin_user_detail(user_id: int):
    """ユーザー詳細を返す。"""
    err = _require_user_manage()
    if err:
        return err

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"user": _serialize_user(user)})


@bp.post("/admin/users")
@login_or_jwt_required
def api_admin_users_create():
    """ユーザーを作成する。"""
    err = _require_user_manage()
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    password = (payload.get("password") or "").strip()
    role_ids = payload.get("roleIds") or []

    if not email:
        return jsonify({"error": "email_required"}), 400
    if not _is_valid_email(email):
        return jsonify({"error": "invalid_email", "message": "Please provide a valid email address."}), 400
    if not password:
        return jsonify({"error": "password_required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email_exists", "message": "Email already in use."}), 409

    roles: list[Role] = []
    if role_ids:
        roles = Role.query.filter(Role.id.in_(role_ids)).all()
        if len(roles) != len(set(role_ids)):
            return jsonify({"error": "invalid_role"}), 400

    user = User(email=email, username=payload.get("username") or None)
    user.set_password(password)
    user.roles = roles
    db.session.add(user)
    db.session.commit()
    return jsonify({"user": _serialize_user(user), "created": True}), 201


@bp.put("/admin/users/<int:user_id>")
@login_or_jwt_required
def api_admin_user_update(user_id: int):
    """ユーザーのプロフィール（email / username / isActive）を更新する。"""
    err = _require_user_manage()
    if err:
        return err

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    changed = False

    if "email" in payload:
        new_email = (payload["email"] or "").strip()
        if not new_email:
            return jsonify({"error": "email_required"}), 400
        if not _is_valid_email(new_email):
            return jsonify({"error": "invalid_email", "message": "Please provide a valid email address."}), 400
        if new_email != user.email and User.query.filter_by(email=new_email).first():
            return jsonify({"error": "email_exists", "message": "Email already in use."}), 409
        user.email = new_email
        changed = True

    if "username" in payload:
        user.username = payload["username"] or None
        changed = True

    if "isActive" in payload:
        if user.id == current_user.id and not payload["isActive"]:
            return jsonify({"error": "cannot_deactivate_self"}), 400
        user.is_active = bool(payload["isActive"])
        changed = True

    if changed:
        db.session.commit()
    return jsonify({"user": _serialize_user(user), "updated": changed})


@bp.put("/admin/users/<int:user_id>/roles")
@login_or_jwt_required
def api_admin_user_roles(user_id: int):
    """ユーザーのロール割り当てを更新する。"""
    err = _require_user_manage()
    if err:
        return err

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    role_ids = payload.get("roleIds")
    if role_ids is None:
        return jsonify({"error": "roleIds_required"}), 400
    if not isinstance(role_ids, list) or len(role_ids) == 0:
        return jsonify({"error": "at_least_one_role_required"}), 400

    roles = Role.query.filter(Role.id.in_(role_ids)).all()
    if len(roles) != len(set(role_ids)):
        return jsonify({"error": "invalid_role"}), 400

    user.roles = roles
    db.session.commit()
    return jsonify({"user": _serialize_user(user), "updated": True})


@bp.post("/admin/users/<int:user_id>/reset-totp")
@login_or_jwt_required
def api_admin_user_reset_totp(user_id: int):
    """ユーザーの TOTP シークレットをリセットする。"""
    err = _require_user_manage()
    if err:
        return err

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "not_found"}), 404

    user.totp_secret = None
    db.session.commit()
    return jsonify({"result": "reset", "userId": user_id})


@bp.delete("/admin/users/<int:user_id>")
@login_or_jwt_required
def api_admin_user_delete(user_id: int):
    """ユーザーを削除する。"""
    err = _require_user_manage()
    if err:
        return err

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "not_found"}), 404

    caller = get_current_user()
    if caller and caller.id == user.id:
        return jsonify({"error": "cannot_delete_self"}), 400

    db.session.delete(user)
    db.session.commit()
    return jsonify({"result": "deleted", "userId": user_id})


@bp.get("/admin/roles")
@login_or_jwt_required
def api_admin_roles_list():
    """ロール一覧を返す（`user:manage` 権限必須）。"""
    err = _require_user_manage()
    if err:
        return err

    roles = Role.query.order_by(Role.id.asc()).all()
    return jsonify({"roles": [_serialize_role(r) for r in roles]})
