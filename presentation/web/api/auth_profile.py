"""認証プロフィール JSON API — 自分のプロフィール更新・2FA 設定・新規登録・パスワードリセット"""
from __future__ import annotations

from flask import jsonify, request

from ..bootstrap.extensions import db
from shared.infrastructure.models.user import User, Role
from . import bp
from .routes import login_or_jwt_required, get_current_user
from .health import skip_auth
from ..auth.totp import new_totp_secret, provisioning_uri, verify_totp, qr_code_data_uri
from ..services.token_service import TokenService
from ..services.password_reset_service import PasswordResetService


def _orm_user(user) -> User | None:
    """Returns the SQLAlchemy User ORM object if available, else None."""
    return user if isinstance(user, User) else None


@bp.put("/auth/profile")
@login_or_jwt_required
def api_auth_profile_update():
    """現在のユーザーのプロフィール（email / username / password）を更新する。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "authentication_required"}), 401

    payload = request.get_json(silent=True) or {}
    changed = False

    if "email" in payload:
        new_email = (payload["email"] or "").strip()
        if not new_email:
            return jsonify({"error": "email_required"}), 400
        if new_email != user.email and User.query.filter_by(email=new_email).first():
            return jsonify({"error": "email_exists", "message": "Email already in use."}), 409
        user.email = new_email
        changed = True

    if "username" in payload:
        user.username = payload["username"] or None
        changed = True

    if "password" in payload:
        new_password = (payload["password"] or "").strip()
        if new_password:
            if len(new_password) < 8:
                return jsonify({"error": "password_too_short", "message": "Password must be at least 8 characters."}), 400
            user.set_password(new_password)
            changed = True

    if changed:
        db.session.commit()

    return jsonify({
        "updated": changed,
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        },
    })


@bp.get("/auth/2fa/status")
@login_or_jwt_required
def api_auth_2fa_status():
    """現在のユーザーの 2FA 有効状態を返す。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "authentication_required"}), 401
    return jsonify({"enabled": bool(user.totp_secret)})


@bp.post("/auth/2fa/setup")
@login_or_jwt_required
def api_auth_2fa_setup():
    """新しい TOTP シークレットを生成して返す（確定は /api/auth/2fa/confirm で行う）。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "authentication_required"}), 401

    if user.totp_secret:
        return jsonify({"error": "already_enabled"}), 409

    secret = new_totp_secret()
    uri = provisioning_uri(user.email, secret)
    qr_data = qr_code_data_uri(uri)

    return jsonify({
        "secret": secret,
        "otpauth_uri": uri,
        "qr_data_uri": qr_data,
    })


@bp.post("/auth/2fa/confirm")
@login_or_jwt_required
def api_auth_2fa_confirm():
    """TOTP コードを検証してシークレットを保存する（2FA を有効化）。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "authentication_required"}), 401

    if user.totp_secret:
        return jsonify({"error": "already_enabled"}), 409

    payload = request.get_json(silent=True) or {}
    secret = (payload.get("secret") or "").strip()
    code = (payload.get("code") or "").strip()

    if not secret:
        return jsonify({"error": "secret_required"}), 400
    if not code:
        return jsonify({"error": "code_required"}), 400

    if not verify_totp(secret, code):
        return jsonify({"error": "invalid_code"}), 400

    user.totp_secret = secret
    db.session.commit()
    return jsonify({"enabled": True})


@bp.delete("/auth/2fa")
@login_or_jwt_required
def api_auth_2fa_disable():
    """2FA を無効化する（TOTP シークレットを削除）。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "authentication_required"}), 401

    user.totp_secret = None
    db.session.commit()
    return jsonify({"enabled": False})


@bp.post("/auth/register")
@skip_auth
def api_auth_register():
    """新しいユーザーを登録して JWT トークンを発行する。"""
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    password = (payload.get("password") or "").strip()

    if not email:
        return jsonify({"error": "email_required"}), 400
    if not password:
        return jsonify({"error": "password_required"}), 400
    if len(password) < 8:
        return jsonify({"error": "password_too_short", "message": "Password must be at least 8 characters."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email_exists", "message": "Email already in use."}), 409

    user = User(
        email=email,
        username=payload.get("username") or None,
        is_active=True,
    )
    user.set_password(password)

    guest_role = Role.query.filter_by(name="guest").first()
    if guest_role:
        user.roles = [guest_role]

    db.session.add(user)
    db.session.commit()

    granted_scope = sorted(user.all_permissions)
    access_token, refresh_token = TokenService.generate_token_pair(user, granted_scope)

    return jsonify({
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        },
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
    }), 201


@bp.post("/auth/password/forgot")
@skip_auth
def api_auth_password_forgot():
    """パスワードリセットメールを送信する（メールが存在しなくても成功を返す）。"""
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    if not email:
        return jsonify({"error": "email_required"}), 400
    ok, err = PasswordResetService.create_reset_request(email)
    if not ok:
        return jsonify({"error": "mail_disabled", "message": err}), 503
    return jsonify({"sent": True})


@bp.post("/auth/password/reset")
@skip_auth
def api_auth_password_reset():
    """トークンを検証して新しいパスワードを設定する。"""
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    password = payload.get("password") or ""
    if not token:
        return jsonify({"error": "token_required"}), 400
    if not password or len(password) < 8:
        return jsonify({"error": "password_too_short"}), 400
    ok = PasswordResetService.reset_password(token, password)
    if not ok:
        return jsonify({"error": "invalid_token"}), 400
    return jsonify({"reset": True})


@bp.post("/auth/password/force-change")
@login_or_jwt_required
def api_auth_password_force_change():
    """初回ログイン時の強制パスワード変更。must_change_password フラグをリセットする。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "authentication_required"}), 401

    payload = request.get_json(silent=True) or {}
    new_password = (payload.get("password") or "").strip()
    if not new_password:
        return jsonify({"error": "password_required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "password_too_short", "message": "Password must be at least 8 characters."}), 400

    current_password = (payload.get("current_password") or "").strip()
    if current_password and not user.check_password(current_password):
        return jsonify({"error": "invalid_current_password"}), 400

    user.set_password(new_password)
    user.must_change_password = False

    db.session.commit()

    return jsonify({"changed": True})
