from flask import request, jsonify, session
from flask_login import login_user, login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from . import bp
from ..extensions import db
from ..models.user import User
from .totp import new_totp_secret, provisioning_uri, verify_totp

@bp.post("/register")
def register():
    email = request.json.get("email")
    password = request.json.get("password")
    if not email or not password:
        return {"message":"email/password required"}, 400

    if User.query.filter_by(email=email).first():
        return {"message":"email already exists"}, 409

    u = User(email=email, password_hash=generate_password_hash(password))
    db.session.add(u)
    db.session.commit()
    return {"message":"registered"}, 201

@bp.post("/login")
def login():
    email = request.json.get("email")
    password = request.json.get("password")
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return {"message":"invalid credentials"}, 401

    # TOTP有効ならワンタイムコードを別エンドポイントで検証
    session["pending_uid"] = user.id
    if user.is_totp_enabled:
        return {"require_totp": True}, 200

    login_user(user)
    return {"message":"logged in"}, 200

@bp.post("/login/totp")
def login_totp():
    uid = session.get("pending_uid")
    if not uid:
        return {"message":"no pending session"}, 400

    token = request.json.get("token")
    user = User.query.get(uid)
    if not user or not user.totp_secret:
        return {"message":"totp not set"}, 400

    if verify_totp(user.totp_secret, token):
        login_user(user)
        session.pop("pending_uid", None)
        return {"message":"logged in"}, 200
    return {"message":"invalid totp"}, 401

@bp.post("/totp/setup")
@login_required
def setup_totp():
    if current_user.is_totp_enabled and current_user.totp_secret:
        return {"message":"already enabled"}, 400

    secret = new_totp_secret()
    current_user.totp_secret = secret
    db.session.commit()

    # QRにするためのURIを返す（Google Authenticator等で読み取り）
    uri = provisioning_uri(current_user.email, secret, issuer="MyFlaskApp")
    return {"provisioning_uri": uri, "secret": secret}, 200

@bp.post("/totp/enable")
@login_required
def enable_totp():
    token = request.json.get("token")
    if not current_user.totp_secret:
        return {"message":"setup first"}, 400

    if verify_totp(current_user.totp_secret, token):
        current_user.is_totp_enabled = True
        db.session.commit()
        return {"message":"totp enabled"}, 200
    return {"message":"invalid token"}, 400

@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return {"message":"logged out"}, 200
