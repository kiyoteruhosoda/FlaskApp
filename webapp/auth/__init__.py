from flask import Blueprint


SERVICE_LOGIN_SESSION_KEY = "service_login_expected"


bp = Blueprint("auth", __name__, template_folder="templates")


__all__ = ["bp", "SERVICE_LOGIN_SESSION_KEY"]
